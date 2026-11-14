from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.api.chefs import _visible_profile
from app.api.deps import get_optional_user, require_roles
from app.db.session import get_db
from app.models import Booking, BookingStatus, ChefProfile, Review, User, UserRole
from app.schemas.booking import ReviewCreate, ReviewOut

router = APIRouter(tags=["reviews"])


def to_out(r: Review) -> ReviewOut:
    return ReviewOut(id=r.id, customer_name=r.customer.full_name, rating=r.rating, comment=r.comment, created_at=r.created_at)


@router.get("/chefs/{chef_id}/reviews", response_model=list[ReviewOut])
def chef_reviews(chef_id: int, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
                 viewer: User | None = Depends(get_optional_user)):
    chef = _visible_profile(db, chef_id, viewer)
    rows = db.scalars(select(Review).options(selectinload(Review.customer)).where(Review.chef_id == chef.id)
                      .order_by(Review.created_at.desc(), Review.id.desc()).limit(limit))
    return [to_out(r) for r in rows]


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(body: ReviewCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.customer))):
    booking = db.get(Booking, body.booking_id)
    if not booking or booking.customer_id != user.id:
        raise HTTPException(404, "Booking not found")
    if booking.status != BookingStatus.completed:
        raise HTTPException(409, "Only completed bookings can be reviewed")
    if booking.review is not None:
        raise HTTPException(409, "You already reviewed this booking")
    chef = db.get(ChefProfile, booking.chef_id)
    review = Review(booking_id=booking.id, customer_id=user.id, chef_id=chef.id, rating=body.rating, comment=body.comment)
    # Running average, so ratings that were already on the profile (e.g. demo data) are kept.
    chef.rating_avg = ((chef.rating_avg or 0) * chef.review_count + body.rating) / (chef.review_count + 1)
    chef.review_count += 1
    db.add(review)
    db.commit()
    return to_out(review)
