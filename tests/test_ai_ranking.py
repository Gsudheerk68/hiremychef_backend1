from datetime import date, datetime, timedelta, timezone
import pytest
from app.ai import service
from app.ai.ranking import recommend
from app.core.config import get_settings
from app.models import Booking, BookingStatus, ChefProfile, ChefUnavailableDate, User, UserRole
from app.services.pricing import estimate_price

TODAY = date(2026, 11, 14)
SUNDAY = date(2026, 11, 15)
# name, city, cuisines, price, rating, years, bio, verified
CHEFS = [
    ("Ravi Kumar", "Nellore", ["South Indian", "Andhra"], 1500, 4.9, 12, "Andhra meals and pulusu for family dinners.", True),
    ("Sunitha Reddy", "Nellore", ["Seafood", "Andhra"], 1800, 4.7, 10, "Nellore chepala pulusu and prawn fry.", True),
    ("Pradeep", "Nellore", ["BBQ", "Party Catering"], 2000, 4.5, 11, "Live BBQ counters for parties.", True),
    ("Anil Rao", "Nellore", ["Vegetarian"], 2500, 4.4, 6, "Pure vegetarian pooja meals.", True),
    ("Fancy Chef", "Nellore", ["Continental"], 3500, 4.8, 15, "Fine dining continental dinners.", True),
    ("Imran Sheikh", "Hyderabad", ["Biryani", "Mughlai"], 4200, 4.9, 16, "Dum biryani and haleem for weddings.", True),
    ("Ayesha Khan", "Hyderabad", ["Biryani", "Mughlai"], 3500, 4.8, 9, "Hyderabadi biryani and kebabs.", True),
    ("Lakshmi Devi", "Vijayawada", ["Vegetarian", "South Indian"], 1800, 4.9, 20, "Satvik vegetarian feasts for festivals.", True),
    ("Gopal Krishna", "Vijayawada", ["Vegetarian", "Andhra"], 3800, 4.8, 22, "Vegetarian wedding catering.", True),
    ("Hidden Biryani", "Hyderabad", ["Biryani"], 1000, 5.0, 30, "The best biryani in the world.", False),   # not verified
]


@pytest.fixture()
def db(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_index_path", str(tmp_path / "chefs.joblib"))
    service.reset_index()
    with client.Session() as session:
        for i, (name, city, cuisines, price, rating, years, bio, verified) in enumerate(CHEFS, 1):
            session.add(User(email=f"c{i}@x.com", full_name=name, hashed_password="x", role=UserRole.chef, chef_profile=ChefProfile(
                city=city, cuisines=cuisines, price_per_session=price, rating_avg=rating, review_count=50, years_experience=years,
                bio=bio, is_verified=verified)))
        session.commit()
        yield session
    service.reset_index()


def names(result):
    return [r.metadata["name"] for r in result.results]


def chef_id(db, name):
    return db.query(ChefProfile).join(User).filter(User.full_name == name).one().id


def test_city_is_a_hard_filter(db):
    r = recommend(db, "andhra chef in Nellore", today=TODAY)
    assert r.parsed.city == "Nellore" and r.relaxed == []
    assert {x.metadata["city"] for x in r.results} == {"Nellore"}
    assert names(r)[0] in ("Ravi Kumar", "Sunitha Reddy")   # Andhra cuisine matches rank first


def test_budget_is_a_hard_filter_using_the_estimated_price(db):
    r = recommend(db, "chef in Nellore under 2600", limit=10, today=TODAY)
    assert r.relaxed == [] and "Fancy Chef" not in names(r) and len(r.results) == 4
    assert all(x.estimated_price <= 2600 for x in r.results)


def test_estimate_uses_guests_and_event_type(db):
    r = recommend(db, "wedding for 10 guests in Nellore", today=TODAY)
    ravi = next(x for x in r.results if x.metadata["name"] == "Ravi Kumar")
    assert ravi.estimated_price == estimate_price(1500, 10, "Wedding / Reception")


def test_cuisine_match_drives_ranking(db):
    r = recommend(db, "biryani chef", today=TODAY)
    assert names(r)[:2] == ["Imran Sheikh", "Ayesha Khan"]


def test_unverified_chefs_are_never_recommended(db):
    assert "Hidden Biryani" not in names(recommend(db, "best biryani in the world in Hyderabad", limit=10, today=TODAY))


def test_availability_is_relaxed_first_and_reported(db):
    ids = [chef_id(db, n) for n in ("Sunitha Reddy", "Pradeep", "Anil Rao", "Fancy Chef")]
    for cid in ids:
        db.add(ChefUnavailableDate(chef_id=cid, date=SUNDAY))
    db.commit()
    r = recommend(db, "chef in Nellore on Sunday", limit=10, today=TODAY)
    assert r.relaxed == ["availability"] and len(r.results) == 5
    assert any("Sun 15 Nov" in n for n in r.notes)
    busy = next(x for x in r.results if x.metadata["name"] == "Pradeep")
    assert "Not available on Sun 15 Nov" in busy.reasons
    free = next(x for x in r.results if x.metadata["name"] == "Ravi Kumar")
    assert all("Not available" not in reason for reason in free.reasons)


def test_availability_filter_applies_when_enough_chefs_are_free(db):
    cid = chef_id(db, "Ravi Kumar")
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    db.add(Booking(customer_id=db.query(User).first().id, chef_id=cid, service_type="Family dinner", event_date=now, event_day=SUNDAY,
                   guests=4, location="X", status=BookingStatus.accepted))
    db.commit()
    r = recommend(db, "chef in Nellore on Sunday", limit=10, today=TODAY)
    assert r.relaxed == [] and "Ravi Kumar" not in names(r) and len(r.results) == 4


def test_city_is_relaxed_last(db):
    r = recommend(db, "vegetarian chef in Vijayawada under 3000", limit=10, today=TODAY)
    assert r.relaxed[0] == "budget" and r.relaxed[-1] == "city" and len(r.results) >= 3
    assert any("Vijayawada" in n for n in r.notes)
    outside = next(x for x in r.results if x.metadata["city"] != "Vijayawada")
    assert any("you asked for Vijayawada" in reason for reason in outside.reasons)


def test_unrelated_text_returns_nothing(db):
    r = recommend(db, "quantum physics laboratory", today=TODAY)
    assert r.results == [] and r.parsed.city is None


def test_scores_sorted_bounded_and_limited(db):
    r = recommend(db, "south indian andhra vegetarian food", limit=3, today=TODAY)
    assert len(r.results) == 3
    scores = [x.score for x in r.results]
    assert scores == sorted(scores, reverse=True) and all(0 <= x.match_percent <= 100 for x in r.results)


def test_reasons_come_from_real_data(db):
    top = recommend(db, "south indian chef for 10 people in Nellore budget 5000 on Sunday", today=TODAY).results[0]
    text = " | ".join(top.reasons)
    assert top.metadata["name"] == "Ravi Kumar"
    assert "Specialises in South Indian cuisine" in text and "Based in Nellore" in text
    assert "Rated 4.9 from 50 reviews" in text and "12 years of experience" in text and "within your budget" in text and "Free on Sun 15 Nov" in text


def test_empty_database_is_safe(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_index_path", str(tmp_path / "empty.joblib"))
    service.reset_index()
    with client.Session() as session:
        assert recommend(session, "biryani in Hyderabad", today=TODAY).results == []
    service.reset_index()
