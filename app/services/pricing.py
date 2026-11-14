"""Server-side price rule (the server is the source of truth; the client's figure is ignored).
Base session price covers 6 guests; +6% of base per extra guest; times an event-type factor; rounded to Rs 50."""
from decimal import Decimal
from math import floor

SERVICE_FACTORS = {
    "Family dinner": 1.0, "Weekly meals": 0.9, "Birthday party": 1.15,
    "Festival / Pooja": 1.1, "Corporate event": 1.3, "Wedding / Reception": 1.5,
}
INCLUDED_GUESTS = 6


def estimate_price(base: Decimal | float, guests: int, service_type: str) -> int:
    base = float(base or 0)
    extra = round(base * 0.06 * max(0, guests - INCLUDED_GUESTS))
    total = (base + extra) * SERVICE_FACTORS.get(service_type, 1.0)
    return int(floor(total / 50 + 0.5) * 50)
