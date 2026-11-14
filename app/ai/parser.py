"""Rule-based query understanding (no LLM, no network). Turns free text into structured requirements:
city, cuisines, budget, guests, event type and date. Dates use India's calendar."""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
          "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
          "november": 11, "nov": 11, "december": 12, "dec": 12}
CITY_ALIASES = {"vizag": "Visakhapatnam", "vishakapatnam": "Visakhapatnam", "visakhapatnam": "Visakhapatnam", "bangalore": "Bengaluru",
                "bombay": "Mumbai", "madras": "Chennai", "hyd": "Hyderabad", "tirupathi": "Tirupati", "cochin": "Kochi", "new delhi": "Delhi"}
CUISINE_SYNONYMS = {
    "veg": "Vegetarian", "pure veg": "Vegetarian", "satvik": "Vegetarian", "sattvic": "Vegetarian", "jain": "Vegetarian",
    "healthy": "Healthy", "millet": "Healthy", "keto": "Healthy", "low oil": "Healthy",
    "biriyani": "Biryani", "dum biryani": "Biryani", "idli": "South Indian", "dosa": "South Indian", "sambar": "South Indian",
    "south-indian": "South Indian", "telugu": "Andhra", "gongura": "Andhra", "pulusu": "Andhra", "haleem": "Hyderabadi",
    "kebab": "Mughlai", "kebabs": "Mughlai", "tandoori": "BBQ", "barbecue": "BBQ", "grill": "BBQ", "grilled": "BBQ",
    "pasta": "Italian", "pizza": "Italian", "fish": "Seafood", "prawn": "Seafood", "prawns": "Seafood", "crab": "Seafood",
    "chettinad": "Tamil", "dessert": "Desserts", "cake": "Desserts", "cakes": "Desserts", "sweets": "Desserts",
}
# First match wins, so more specific event types come first.
EVENT_PATTERNS = [
    ("Wedding / Reception", r"wedding|reception|engagement|marriage|sangeet|mehendi|mehndi|baby shower|bridal"),
    ("Corporate event", r"corporate|office|company|conference|team lunch|team dinner|business|seminar|meeting"),
    ("Festival / Pooja", r"pooja|puja|festival|diwali|deepavali|ugadi|sankranti|pongal|ganesh|navratri|dussehra|housewarming|house warming|griha pravesh|vratham|vratam|satyanarayana|ramzan|eid|christmas|onam"),
    ("Birthday party", r"birthday|bday|anniversary|party|kitty|get-?together|cocktail|celebration|farewell"),
    ("Weekly meals", r"weekly|daily|meal prep|monthly|regular|everyday|every day|home cook"),
    ("Family dinner", r"family dinner|family lunch|family meal|dinner|lunch|brunch|family"),
]
_NUM = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_UNIT = r"(?:\s*(k|thousand|lakhs?|lacs?|l)\b)?"
_CUR = r"(?:₹|rs\.?|inr|rupees)"
_PEOPLE = r"^\s*(?:people|persons?|guests?|members?|pax|ppl|adults?|kids?|children|plates?|heads?)\b"
_PER_HEAD = r"^\s*(?:/|per|a|each)\s*(?:head|person|plate|guest|pax)\b"
BUDGET_PATTERNS = [
    rf"{_CUR}\s*{_NUM}{_UNIT}",
    rf"{_NUM}{_UNIT}\s*(?:rs\.?|rupees|inr)\b",
    rf"\b(?:under|below|within|upto|up to|max(?:imum)?|less than|budget(?:\s+is|\s+of|\s+around)?|around|about|approx(?:imately)?)\s*[:\-]?\s*(?:{_CUR}\s*)?{_NUM}{_UNIT}",
    r"\b(\d+(?:\.\d+)?)\s*(k)\b",
]
GUEST_PATTERNS = [
    r"\b(\d{1,3})\s*\+?\s*-?\s*(?:people|persons?|guests?|members?|pax|ppl|adults?|plates?|heads?)\b",
    r"\b(?:party|group|family|gathering|team|batch)\s+of\s+(\d{1,3})\b",
    r"\bfor\s+(?:around\s+|about\s+|nearly\s+|approx\s+)?(\d{1,3})\b(?!\s*(?:k\b|rs|₹|rupees|days?|hours?|hrs?|weeks?|months?|lakh|,\d|\d))",
]


@dataclass
class ParsedQuery:
    raw: str
    city: str | None = None
    cuisines: list[str] = field(default_factory=list)
    budget: float | None = None
    guests: int | None = None
    event_type: str | None = None
    date: "date | None" = None  # string annotation: the field name hides the `date` type inside this class
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"city": self.city, "cuisines": self.cuisines, "budget": self.budget, "guests": self.guests,
                "event_type": self.event_type, "date": self.date.isoformat() if self.date else None}


def _blank(text: str, span: tuple[int, int]) -> str:
    return text[:span[0]] + " " * (span[1] - span[0]) + text[span[1]:]


def _month_day(day: int, month: int, year: int | None, today: date):
    try:
        if year:
            return date(year, month, day)
        d = date(today.year, month, day)
        return d if d >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _parse_date(text: str, today: date):
    """Returns (date | None, text with the date words blanked out)."""
    monday = today - timedelta(days=today.weekday())
    wd = "|".join(WEEKDAYS)
    mon = "|".join(sorted(MONTHS, key=len, reverse=True))
    rules = [
        (r"\bday after tomorrow\b", lambda m: today + timedelta(days=2)),
        (r"\btomorrow\b", lambda m: today + timedelta(days=1)),
        (r"\b(?:today|tonight)\b", lambda m: today),
        (r"\bnext weekend\b", lambda m: monday + timedelta(days=12)),
        (r"\b(?:this )?weekend\b", lambda m: today + timedelta(days=(5 - today.weekday()) % 7)),
        (r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
        (r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({mon})\b(?:\s*,?\s*(\d{{4}}))?", lambda m: _month_day(int(m[1]), MONTHS[m[2]], int(m[3]) if m[3] else None, today)),
        (rf"\b({mon})\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?\b(?:\s*,?\s*(\d{{4}}))?", lambda m: _month_day(int(m[2]), MONTHS[m[1]], int(m[3]) if m[3] else None, today)),
        (rf"\bnext\s+({wd})\b", lambda m: monday + timedelta(days=7 + WEEKDAYS[m[1]])),
        (rf"\b(?:(?:this|coming|on)\s+)?({wd})\b", lambda m: today + timedelta(days=(WEEKDAYS[m[1]] - today.weekday()) % 7)),
    ]
    for pattern, build in rules:
        m = re.search(pattern, text)
        if m:
            try:
                value = build(m)
            except ValueError:  # e.g. 31 February
                value = None
            return value, _blank(text, m.span())
    return None, text


def _after_ok(text: str, end: int) -> bool:
    return not re.match(_PEOPLE, text[end:])


def _parse_budget(text: str):
    """Returns (amount, per_head, text with the budget words blanked out)."""
    for pattern in BUDGET_PATTERNS:
        for m in re.finditer(pattern, text):
            if not _after_ok(text, m.end()):  # "around 20 guests" is a guest count, not money
                continue
            value = float(m.group(1).replace(",", ""))
            unit = (m.group(2) or "").lower()
            if unit in ("k", "thousand"):
                value *= 1000
            elif unit.startswith(("l",)):
                value *= 100000
            per_head = bool(re.match(_PER_HEAD, text[m.end():]))
            low, high = (50, 20000) if per_head else (200, 10_000_000)
            if low <= value <= high:
                end = m.end() + (re.match(_PER_HEAD, text[m.end():]).end() if per_head else 0)
                return value, per_head, _blank(text, (m.start(), end))
    return None, False, text


def _parse_guests(text: str) -> int | None:
    for pattern in GUEST_PATTERNS:
        m = re.search(pattern, text)
        if m and 1 <= int(m.group(1)) <= 500:
            return int(m.group(1))
    return None


def _parse_city(text: str, known_cities) -> str | None:
    lookup = {c.lower(): c for c in known_cities if c}
    for alias, target in CITY_ALIASES.items():
        if target.lower() in lookup:
            lookup.setdefault(alias, lookup[target.lower()])
    best = None
    for name, canonical in lookup.items():
        m = re.search(rf"\b{re.escape(name)}\b", text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), canonical)
    return best[1] if best else None


def _parse_cuisines(text: str, known_cuisines, city: str | None) -> list[str]:
    lookup = {c.lower(): c for c in known_cuisines if c}
    terms = {name: canonical for name, canonical in lookup.items()}
    for syn, target in CUISINE_SYNONYMS.items():
        if target.lower() in lookup:
            terms.setdefault(syn, lookup[target.lower()])
    found: dict[str, int] = {}
    for term, canonical in terms.items():
        if city and canonical.lower() == city.lower():
            continue  # "Nellore" in the query is the city, not a cuisine
        m = re.search(rf"\b{re.escape(term)}\b", text)
        if m and (canonical not in found or m.start() < found[canonical]):
            found[canonical] = m.start()
    return [c for c, _ in sorted(found.items(), key=lambda kv: kv[1])]


def _parse_event(text: str) -> str | None:
    for name, pattern in EVENT_PATTERNS:
        if re.search(rf"\b(?:{pattern})\b", text):
            return name
    return None


def parse_query(query: str, known_cities, known_cuisines, today: date) -> ParsedQuery:
    text = " " + (query or "").lower().replace("\u20b9", "₹") + " "
    p = ParsedQuery(raw=query or "")
    p.date, rest = _parse_date(text, today)
    if p.date and p.date < today:
        p.warnings.append("That date has already passed, so I ignored it.")
        p.date = None
    budget, per_head, rest = _parse_budget(rest)
    p.guests = _parse_guests(rest)
    if budget is not None:
        if per_head and not p.guests:
            p.warnings.append("I need the number of guests to use a per-person budget.")
        else:
            p.budget = budget * p.guests if per_head else budget
    p.city = _parse_city(text, known_cities)
    p.cuisines = _parse_cuisines(text, known_cuisines, p.city)
    p.event_type = _parse_event(text)
    return p
