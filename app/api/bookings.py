from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_current_user, require_roles
from app.core.timeutils import to_local_naive, to_utc
from app.db.session import get_db
from app.models import Booking, BookingStatus, ChefProfile, ChefUnavailableDate, User, UserRole
from app.schemas.booking import BookingCreate, BookingOut, EstimateIn, EstimateOut
from app.services.pricing import estimate_price

router = APIRouter(prefix="/bookings", tags=["bookings"])
LOAD = (selectinload(Booking.chef).selectinload(ChefProfile.user), selectinload(Booking.customer), selectinload(Booking.review))


def to_out(b: Booking) -> BookingOut:
    return BookingOut(id=b.id, customer_id=b.customer_id, customer_name=b.customer.full_name, chef_id=b.chef_id,
                      chef_name=b.chef.user.full_name, chef_photo=b.chef.photo_url, service_type=b.service_type,
                      event_date=to_local_naive(b.event_date), guests=b.guests, cuisine=b.cuisine, location=b.location,
                      notes=b.notes, estimated_price=float(b.estimated_price), status=b.status.value,
                      created_at=b.created_at, reviewed=b.review is not None)


def _public_chef(db: Session, chef_id: int) -> ChefProfile:
    chef = db.get(ChefProfile, chef_id)
    if not chef or not chef.is_verified or not chef.user.is_active:
        raise HTTPException(404, "Chef not found")
    return chef


def _day_conflict(db: Session, chef_id: int, day, exclude_id: int | None = None) -> str | None:
    blocked = db.scalar(select(exists().where(ChefUnavailableDate.chef_id == chef_id, ChefUnavailableDate.date == day)))
    if blocked:
        return "blocked"
    q = select(exists().where(Booking.chef_id == chef_id, Booking.event_day == day, Booking.status == BookingStatus.accepted,
                              *( [Booking.id != exclude_id] if exclude_id else [] )))
    return "booked" if db.scalar(q) else None


@router.post("/estimate", response_model=EstimateOut)
def estimate(body: EstimateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chef = _public_chef(db, body.chef_id)
    return EstimateOut(estimated_price=estimate_price(chef.price_per_session, body.guests, body.service_type))


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(body: BookingCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.customer))):
    chef = _public_chef(db, body.chef_id)
    event_utc = to_utc(body.event_date)
    day = to_local_naive(event_utc).date()
    if _day_conflict(db, chef.id, day):
        raise HTTPException(409, "The chef is not available on that date")
    booking = Booking(customer_id=user.id, chef_id=chef.id, service_type=body.service_type, event_date=event_utc, event_day=day,
                      guests=body.guests, cuisine=body.cuisine, location=body.location, notes=body.notes,
                      estimated_price=estimate_price(chef.price_per_session, body.guests, body.service_type))
    db.add(booking)
    db.commit()
    return to_out(db.scalars(select(Booking).options(*LOAD).where(Booking.id == booking.id)).one())


@router.get("", response_model=list[BookingOut])
def my_bookings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Filtered by the token: customers see their own, chefs see bookings for their profile, admins see all."""
    stmt = select(Booking).options(*LOAD).order_by(Booking.event_date.desc(), Booking.id.desc())
    if user.role == UserRole.customer:
        stmt = stmt.where(Booking.customer_id == user.id)
    elif user.role == UserRole.chef:
        if not user.chef_profile:
            return []
        stmt = stmt.where(Booking.chef_id == user.chef_profile.id)
    return [to_out(b) for b in db.scalars(stmt)]


# action -> (allowed current statuses, new status, who may do it)
RULES = {
    "accept": ({BookingStatus.pending}, BookingStatus.accepted, {"chef"}),
    "reject": ({BookingStatus.pending}, BookingStatus.rejected, {"chef"}),
    "complete": ({BookingStatus.accepted}, BookingStatus.completed, {"chef"}),
    "cancel": ({BookingStatus.pending, BookingStatus.accepted}, BookingStatus.cancelled, {"chef", "customer"}),
}


@router.post("/{booking_id}/{action}", response_model=BookingOut)
def change_status(booking_id: int, action: Literal["accept", "reject", "cancel", "complete"],
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    booking = db.scalars(select(Booking).options(*LOAD).where(Booking.id == booking_id)).first()
    is_chef = bool(booking and booking.chef.user_id == user.id)
    is_customer = bool(booking and booking.customer_id == user.id)
    is_admin = user.role == UserRole.admin
    if not booking or not (is_chef or is_customer or is_admin):
        raise HTTPException(404, "Booking not found")  # do not reveal other people's bookings
    allowed_from, new_status, who = RULES[action]
    if not (is_admin or ("chef" in who and is_chef) or ("customer" in who and is_customer)):
        raise HTTPException(403, "You are not allowed to do this")
    if action == "accept":  # serialise accepts per chef so two requests cannot both take the same day
        db.execute(select(ChefProfile.id).where(ChefProfile.id == booking.chef_id).with_for_update())
        db.refresh(booking)
    if booking.status not in allowed_from:
        raise HTTPException(409, f"A {booking.status.value.lower()} booking cannot be {new_status.value.lower()}")
    if action == "accept":
        conflict = _day_conflict(db, booking.chef_id, booking.event_day, exclude_id=booking.id)
        if conflict:
            raise HTTPException(409, "You already have an accepted booking on that date" if conflict == "booked" else "You blocked that date in your calendar")
    booking.status = new_status
    db.commit()
    return to_out(booking)
