from datetime import date
import pytest
from app.ai.parser import parse_query

TODAY = date(2026, 11, 14)  # a Saturday
CITIES = {"Nellore", "Hyderabad", "Vijayawada", "Guntur", "Bengaluru", "Visakhapatnam", "Chennai", "Mumbai", "Kochi"}
CUISINES = {"South Indian", "Andhra", "Vegetarian", "Biryani", "Hyderabadi", "Mughlai", "Seafood", "Kerala", "Italian", "Continental",
            "Desserts", "BBQ", "Vegan", "Tamil", "Punjabi", "North Indian", "Healthy", "Party Catering"}


def parse(q):
    return parse_query(q, CITIES, CUISINES, TODAY)


def test_full_example_from_the_project_brief():
    p = parse("I need a South Indian chef for a family dinner for 10 people in Nellore this Sunday. My budget is ₹5,000.")
    assert p.to_dict() == {"city": "Nellore", "cuisines": ["South Indian"], "budget": 5000.0, "guests": 10,
                           "event_type": "Family dinner", "date": "2026-11-15"}


@pytest.mark.parametrize("query, expected", [
    ("vegetarian cook for a pooja in Vijayawada", {"cuisines": ["Vegetarian"], "event_type": "Festival / Pooja", "city": "Vijayawada"}),
    ("best biryani chef in Hyderabad under 4000", {"cuisines": ["Biryani"], "city": "Hyderabad", "budget": 4000.0}),
    ("wedding catering for 150 guests in Guntur, budget 2 lakh", {"event_type": "Wedding / Reception", "guests": 150, "budget": 200000.0, "city": "Guntur"}),
    ("birthday party in Vizag for 25 people with BBQ, ₹8000", {"city": "Visakhapatnam", "event_type": "Birthday party", "guests": 25, "cuisines": ["BBQ"], "budget": 8000.0}),
    ("chef under 3k", {"budget": 3000.0, "guests": None}),
    ("Chef for 12 people tomorrow", {"guests": 12, "date": "2026-11-15"}),
    ("need a chef on 25 December", {"date": "2026-12-25"}),
    ("chef on 25th of december 2026", {"date": "2026-12-25"}),
    ("chef on december 5", {"date": "2026-12-05"}),
    ("chef on 2026-12-31", {"date": "2026-12-31"}),
    ("chef on 05/12/2026", {"date": "2026-12-05"}),
    ("seafood fish curry in Kochi next Saturday", {"cuisines": ["Seafood"], "city": "Kochi", "date": "2026-11-21"}),
    ("weekly meal prep healthy vegan food", {"event_type": "Weekly meals", "cuisines": ["Healthy", "Vegan"]}),
    ("party of 8, rs 500 per head", {"guests": 8, "budget": 4000.0, "event_type": "Birthday party"}),
    ("something good", {"city": None, "cuisines": [], "budget": None, "guests": None, "event_type": None, "date": None}),
    ("chef in Hyderabadi style", {"city": None, "cuisines": ["Hyderabadi"]}),
    ("up to 10 people budget 6000", {"guests": 10, "budget": 6000.0}),
    ("around 20 guests", {"guests": 20, "budget": None}),
    ("dinner for 4 under ₹2,500", {"guests": 4, "budget": 2500.0, "event_type": "Family dinner"}),
    ("corporate lunch for 40 people in bangalore", {"event_type": "Corporate event", "guests": 40, "city": "Bengaluru"}),
    ("chef this weekend", {"date": "2026-11-14"}),
    ("cook on friday", {"date": "2026-11-20"}),
    ("chef today", {"date": "2026-11-14"}),
    ("chef day after tomorrow", {"date": "2026-11-16"}),
    ("chef in Nellore", {"city": "Nellore", "cuisines": []}),
    ("pasta and desserts for an anniversary", {"cuisines": ["Italian", "Desserts"], "event_type": "Birthday party"}),
    ("tamil pongal feast in chennai for 30", {"cuisines": ["Tamil"], "event_type": "Festival / Pooja", "city": "Chennai", "guests": 30}),
])
def test_parse_examples(query, expected):
    got = parse(query).to_dict()
    for key, value in expected.items():
        assert got[key] == value, f"{query!r}: {key} -> {got[key]!r}, expected {value!r}"


def test_past_date_is_ignored_with_a_warning():
    p = parse("chef on 2026-01-05")
    assert p.date is None and p.warnings


def test_per_head_budget_needs_guests():
    p = parse("chef for rs 500 per head")
    assert p.budget is None and p.warnings


def test_invalid_date_and_empty_input_are_safe():
    assert parse("chef on 31 february").date is None
    assert parse("").to_dict() == {"city": None, "cuisines": [], "budget": None, "guests": None, "event_type": None, "date": None}
    assert parse(None).raw == ""


def test_synonyms_only_map_to_cuisines_that_exist():
    assert parse_query("great pasta", CITIES, {"Mughlai"}, TODAY).cuisines == []   # no Italian chefs in this vocabulary
    assert parse_query("great pasta", CITIES, {"Italian"}, TODAY).cuisines == ["Italian"]
