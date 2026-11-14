from app.ai.documents import ChefDoc, build_documents, chef_to_text
from app.ai.index import ChefIndex, fingerprint
from app.ai import service
from app.models import Booking, BookingStatus, ChefProfile, Review, User
from datetime import datetime, timezone
from tests.test_chefs import make_chef


def doc(i, name, city, cuisines, bio):
    return ChefDoc(i, chef_to_text(name, city, cuisines, [], bio, []), {"chef_id": i, "name": name, "city": city, "cuisines": cuisines})


DOCS = [
    doc(1, "Ravi Kumar", "Nellore", ["Andhra", "South Indian"], "Spicy Andhra meals and pulusu for family functions."),
    doc(2, "Imran Sheikh", "Hyderabad", ["Hyderabadi", "Biryani"], "Dum biryani and haleem for weddings and large parties."),
    doc(3, "Lakshmi Devi", "Vijayawada", ["Vegetarian"], "Pure vegetarian satvik food for pooja and festivals."),
    doc(4, "Marco Rossi", "Bengaluru", ["Italian", "Continental"], "Fine dining pasta and desserts for anniversaries."),
]


def test_chef_to_text_contains_all_fields():
    t = chef_to_text("Ravi", "Nellore", ["Andhra"], ["FSSAI"], "Loves pulusu.", ["Great food"])
    for word in ("Ravi", "Nellore", "Andhra", "FSSAI", "pulusu", "Great food"):
        assert word in t
    assert chef_to_text("Ravi", None, [], [], None, []) == "Chef Ravi."


def test_search_ranks_relevant_chef_first():
    idx = ChefIndex().fit(DOCS)
    assert idx.size == 4
    top = lambda q: idx.search(q, top_k=3)[0].chef_id
    assert top("andhra spicy meals") == 1
    assert top("best biryani for a wedding") == 2
    assert top("vegetarian food for a pooja") == 3
    assert top("italian pasta dinner") == 4
    assert top("chef in Hyderabad") == 2


def test_search_edge_cases():
    idx = ChefIndex().fit(DOCS)
    assert idx.search("") == [] and idx.search("   ") == []
    assert idx.search("quantum physics laboratory") == []   # no overlap with any chef
    assert idx.search("the a of") == []                      # only stop words
    assert len(idx.search("food", top_k=2)) <= 2
    assert ChefIndex().fit([]).search("biryani") == []       # empty index is safe


def test_candidate_filter_restricts_results():
    idx = ChefIndex().fit(DOCS)
    hits = idx.search("biryani andhra vegetarian", top_k=5, candidate_ids={1, 3})
    assert {h.chef_id for h in hits} <= {1, 3} and hits


def test_scores_are_sorted_and_bounded():
    hits = ChefIndex().fit(DOCS).search("andhra biryani vegetarian pasta food", top_k=4)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "idx" / "chefs.joblib")
    idx = ChefIndex().fit(DOCS)
    idx.save(path)
    loaded = ChefIndex.load(path)
    assert loaded.fingerprint == idx.fingerprint and loaded.size == 4
    assert loaded.search("dum biryani") == idx.search("dum biryani")
    assert ChefIndex.load(str(tmp_path / "missing.joblib")) is None
    (tmp_path / "bad.joblib").write_bytes(b"not a real index")
    assert ChefIndex.load(str(tmp_path / "bad.joblib")) is None


def test_fingerprint_changes_when_a_document_changes():
    changed = [*DOCS[:3], doc(4, "Marco Rossi", "Bengaluru", ["Italian"], "Now also does biryani.")]
    assert fingerprint(DOCS) == fingerprint(list(reversed(DOCS))) and fingerprint(DOCS) != fingerprint(changed)


def test_documents_only_include_verified_active_chefs_with_reviews(client):
    ok, _ = make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    hidden, _ = make_chef(client, "Hidden Chef", "Nellore", ["Andhra"], verify=False)
    off, _ = make_chef(client, "Banned Chef", "Nellore", ["Andhra"])
    with client.Session() as db:
        cust = db.query(User).filter_by(email="admin@x.com").one()
        db.query(User).filter(User.full_name == "Banned Chef").one().is_active = False
        now = datetime.now(timezone.utc)
        b = Booking(customer_id=cust.id, chef_id=ok, service_type="Family dinner", event_date=now, event_day=now.date(), guests=4,
                    location="X", status=BookingStatus.completed)
        db.add(b); db.flush()
        db.add(Review(booking_id=b.id, customer_id=cust.id, chef_id=ok, rating=5, comment="Amazing pulusu"))
        db.commit()
        docs = build_documents(db)
    assert [d.chef_id for d in docs] == [ok] and "Amazing pulusu" in docs[0].text
    assert docs[0].metadata["name"] == "Ravi Kumar" and docs[0].metadata["city"] == "Nellore"


def test_service_builds_saves_and_refreshes(client, tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "ai_index_path", str(tmp_path / "chefs.joblib"))
    service.reset_index()
    make_chef(client, "Ravi Kumar", "Nellore", ["Andhra"])
    with client.Session() as db:
        assert service.search_chefs(db, "andhra")[0].chef_id
        assert (tmp_path / "chefs.joblib").exists()
        before = service.get_index(db).fingerprint
        db.query(ChefProfile).one().bio = "Now famous for biryani"
        db.commit()
        assert service.search_chefs(db, "biryani") == []                 # still the cached index inside the freshness window
        assert service.get_index(db, force_check=True).fingerprint != before   # forced check notices the change
        assert service.search_chefs(db, "biryani")
    service.reset_index()
