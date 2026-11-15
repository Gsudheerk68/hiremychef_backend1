from types import SimpleNamespace

from app.ai import ml_ranker
from app.ai.ranking import _to_unit


def test_event_names_cover_parser_events():
    from app.ai.parser import EVENT_PATTERNS
    for name, _ in EVENT_PATTERNS:
        assert ml_ranker.PARSER_TO_TRAIN[name] in ml_ranker.TRAIN_EVENTS


def test_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("ML_RANKER_ENABLED", "0")
    parsed = SimpleNamespace(budget=None, guests=None, event_type=None, city=None, cuisines=[])
    assert ml_ranker.score_candidates(None, "x", parsed, {1}, lambda c: 1000) is None


def test_to_unit_is_monotonic_and_bounded():
    assert 0 < _to_unit(-5) < _to_unit(0) < _to_unit(5) < 1
def test_explain_hides_factors_the_user_did_not_ask_about():
    feats = ["tfidf_sim", "embed_sim", "cuisine_match", "city_match", "budget_fit",
             "price_ratio", "rating", "reviews_log", "years", "guests", "event_idx"]
    row = [0.5, 0.2, 0.4, -0.3, 0.1, 0.1, 0.2, 0.0, 0.05, 0.9, 0.9, 0.0]  # last value = base score
    out = ml_ranker._explain(row, feats, has_cuisine=True, has_city=False, has_budget=False)
    labels = [f["label"] for f in out]
    assert "Based in your city" not in labels and "Not based in your city" not in labels
    assert out[0]["direction"] == "up"
