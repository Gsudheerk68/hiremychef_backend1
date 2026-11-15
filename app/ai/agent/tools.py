"""Tools the chatbot can call: chef search, details, availability, price estimate, and booking."""
from datetime import date, datetime

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.parser import EVENT_PATTERNS
from app.ai.ranking import recommend, unavailable_chef_ids
from app.api.bookings import create_booking as _create_booking_route
from app.core.timeutils import now_local
from app.db.session import SessionLocal
from app.models import User, UserRole
from app.models.chef import ChefProfile
from app.schemas.booking import BookingCreate
from app.services.pricing import estimate_price

EVENT_TYPES = [name for name, _ in EVENT_PATTERNS]


def _chef_dict(c: ChefProfile) -> dict:
    return {
        "chef_id": c.id,
        "name": getattr(c.user, "full_name", None) or "Chef",
        "city": c.city,
        "cuisines": [str(x) for x in (c.cuisines or [])],
        "years_experience": c.years_experience or 0,
        "rating": float(c.rating_avg or 0),
        "review_count": c.review_count or 0,
        "base_price": float(c.price_per_session or 0),
        "bio": c.bio,
        "certifications": [str(x) for x in (c.certifications or [])],
        "photo": c.photo_url,
    }


def _verified_chef(db, chef_id: int) -> ChefProfile | None:
    return db.scalars(
        select(ChefProfile)
        .options(selectinload(ChefProfile.user))
        .where(ChefProfile.id == chef_id, ChefProfile.is_verified.is_(True))
    ).first()


@tool
def search_chefs(request: str) -> dict:
    """Find and rank chefs for a customer's request. Pass the customer's needs as one plain
    sentence including any cuisine, city, budget in rupees, number of guests, event type and
    date, e.g. 'South Indian chef for a family dinner for 10 people in Nellore, budget 5000'.
    Returns up to 5 verified chefs with reasons and estimated prices."""
    with SessionLocal() as db:
        res = recommend(db, request, limit=5)
        ids = [r.chef_id for r in res.results]
        chefs = {c.id: c for c in db.scalars(
            select(ChefProfile).options(selectinload(ChefProfile.user)).where(ChefProfile.id.in_(ids))
        ).all()} if ids else {}
        return {
            "understood": res.parsed.to_dict(),
            "notes": [n for n in res.notes if n],
            "ranked_by": res.scorer,
            "chefs": [
                {**_chef_dict(chefs[r.chef_id]), "estimated_price": r.estimated_price,
                 "match_percent": r.match_percent, "reasons": r.reasons, "factors": r.factors}
                for r in res.results if r.chef_id in chefs
            ],
        }


@tool
def get_chef_details(chef_id: int) -> dict:
    """Get the full profile of one verified chef by id (bio, certifications, rating, price)."""
    with SessionLocal() as db:
        chef = _verified_chef(db, chef_id)
        return _chef_dict(chef) if chef else {"error": f"No verified chef with id {chef_id}."}


@tool
def check_chef_availability(chef_id: int, event_date: str) -> dict:
    """Check whether a chef is free on a date. event_date must be YYYY-MM-DD."""
    try:
        day = date.fromisoformat(event_date)
    except ValueError:
        return {"error": "event_date must look like 2026-12-25."}
    if day < now_local().date():
        return {"error": "That date has already passed."}
    with SessionLocal() as db:
        if not _verified_chef(db, chef_id):
            return {"error": f"No verified chef with id {chef_id}."}
        return {"chef_id": chef_id, "date": event_date, "available": chef_id not in unavailable_chef_ids(db, day)}


@tool
def estimate_booking_price(chef_id: int, guests: int, event_type: str) -> dict:
    """Estimate the price in rupees for a chef, guest count and event type.
    event_type must be exactly one of: Family dinner, Weekly meals, Birthday party,
    Festival / Pooja, Corporate event, Wedding / Reception."""
    if event_type not in EVENT_TYPES:
        return {"error": f"event_type must be one of {EVENT_TYPES}"}
    if not 1 <= guests <= 500:
        return {"error": "guests must be between 1 and 500."}
    with SessionLocal() as db:
        chef = _verified_chef(db, chef_id)
        if not chef:
            return {"error": f"No verified chef with id {chef_id}."}
        return {"chef_id": chef_id, "guests": guests, "event_type": event_type,
                "estimated_price": estimate_price(float(chef.price_per_session or 0), guests, event_type)}


@tool
def create_booking(
    chef_id: int,
    event_datetime: str,
    guests: int,
    event_type: str,
    location: str,
    config: RunnableConfig,
    cuisine: str = "",
    notes: str = "",
) -> dict:
    """Request a booking with a chef for the logged-in customer. Only call this after the customer
    has given you ALL of: the chef, the date AND time (event_datetime as local India time like
    2026-12-25T19:00:00), the number of guests, the event type and the event location/address.
    event_type must be exactly one of: Family dinner, Weekly meals, Birthday party,
    Festival / Pooja, Corporate event, Wedding / Reception.
    The customer is asked to confirm before anything is created."""
    user_id = ((config or {}).get("configurable") or {}).get("user_id")  # set by the server, never by the model
    if not user_id:
        return {"error": "The customer must be logged in to book."}
    try:
        when = datetime.fromisoformat(event_datetime).replace(tzinfo=None)
    except ValueError:
        return {"error": "event_datetime must look like 2026-12-25T19:00:00."}
    if when <= now_local().replace(tzinfo=None):
        return {"error": "That date and time has already passed."}
    if event_type not in EVENT_TYPES:
        return {"error": f"event_type must be one of {EVENT_TYPES}"}
    if not 1 <= guests <= 500:
        return {"error": "guests must be between 1 and 500."}
    if not location.strip():
        return {"error": "A location is required."}

    # 1) read-only checks, then show the customer a summary
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.is_active or user.role != UserRole.customer:
            return {"error": "Only logged-in customers can book chefs."}
        chef = _verified_chef(db, chef_id)
        if not chef:
            return {"error": f"No verified chef with id {chef_id}."}
        if chef.id in unavailable_chef_ids(db, when.date()):
            return {"error": f"{chef.user.full_name} is not available on {when:%d %b %Y}."}
        chef_name = chef.user.full_name
        price = int(estimate_price(chef.price_per_session, guests, event_type))

    # 2) the graph pauses here; nothing below runs unless the customer says yes
    decision = interrupt({
        "type": "confirm_booking",
        "chef_id": chef_id,
        "chef_name": chef_name,
        "when": when.strftime("%a %d %b %Y, %I:%M %p"),
        "guests": guests,
        "event_type": event_type,
        "location": location.strip(),
        "estimated_price": price,
    })
    if decision is not True:
        return {"status": "cancelled", "message": "The customer chose not to book. Nothing was created."}

    # 3) create it through the same code the website uses
    with SessionLocal() as db:
        user = db.get(User, user_id)
        try:
            body = BookingCreate(
                chef_id=chef_id, service_type=event_type, event_date=when, guests=guests,
                cuisine=cuisine or None, location=location.strip(), notes=notes or None,
            )
            out = _create_booking_route(body=body, db=db, user=user)
        except ValidationError as e:
            return {"error": "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())}
        except HTTPException as e:
            return {"error": str(e.detail)}
        return {
            "status": "requested",
            "booking_id": out.id,
            "chef_name": out.chef_name,
            "estimated_price": out.estimated_price,
            "booking_status": out.status,
            "message": "Booking request sent. It stays Pending until the chef accepts it.",
        }


READ_TOOLS = [search_chefs, get_chef_details, check_chef_availability, estimate_booking_price]
BOOKING_TOOLS = [create_booking]
ALL_TOOLS = READ_TOOLS + BOOKING_TOOLS
