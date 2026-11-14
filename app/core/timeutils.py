"""All events happen in India, which has no daylight saving, so one fixed offset (UTC+05:30) is enough.
Booking times are sent without an offset (local wall-clock, e.g. 2026-12-25T19:00:00), stored as UTC instants,
and the local calendar day is saved separately in `event_day` so availability never shifts by a day."""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_local() -> datetime:
    return datetime.now(IST)


def to_utc(dt: datetime) -> datetime:
    """Naive input is read as India time; aware input is converted."""
    return (dt.replace(tzinfo=IST) if dt.tzinfo is None else dt).astimezone(timezone.utc)


def to_local_naive(dt: datetime) -> datetime:
    """For API output: UTC instant -> India wall-clock without offset. Naive values (SQLite) are treated as UTC."""
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone(IST).replace(tzinfo=None)
