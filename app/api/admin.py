from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import Booking, ChefProfile, User, UserRole
from app.schemas.auth import UserOut
from app.schemas.chef import ChefOut
from app.api.chefs import to_out
from app.api.bookings import LOAD as BOOKING_LOAD, to_out as booking_out
from app.schemas.booking import BookingOut

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(UserRole.admin))])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    """Admin-only. Demonstrates server-side role enforcement; more admin tools arrive in Phase 5."""
    return db.scalars(select(User).order_by(User.id)).all()


@router.get("/chefs", response_model=list[ChefOut])
def list_chefs_for_review(verified: bool | None = None, db: Session = Depends(get_db)):
    """Admin: filter by verified=false to see chefs waiting for approval."""
    stmt = select(ChefProfile).order_by(ChefProfile.id)
    if verified is not None:
        stmt = stmt.where(ChefProfile.is_verified.is_(verified))
    return [to_out(p) for p in db.scalars(stmt)]


def _set_verified(db: Session, chef_id: int, value: bool) -> ChefOut:
    p = db.get(ChefProfile, chef_id)
    if not p:
        raise HTTPException(404, "Chef not found")
    p.is_verified = value
    db.commit()
    return to_out(p)


@router.post("/chefs/{chef_id}/verify", response_model=ChefOut)
def verify_chef(chef_id: int, db: Session = Depends(get_db)):
    return _set_verified(db, chef_id, True)


@router.post("/chefs/{chef_id}/unverify", response_model=ChefOut)
def unverify_chef(chef_id: int, db: Session = Depends(get_db)):
    return _set_verified(db, chef_id, False)


@router.get("/bookings", response_model=list[BookingOut])
def all_bookings(db: Session = Depends(get_db)):
    return [booking_out(b) for b in db.scalars(select(Booking).options(*BOOKING_LOAD).order_by(Booking.event_date.desc()))]
