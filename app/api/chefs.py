from datetime import date, timedelta
from math import ceil
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, String, cast, delete, exists, func, or_, select
from sqlalchemy.orm import Session, contains_eager
from app.api.deps import get_optional_user, require_roles
from app.db.session import get_db
from app.models import Booking, BookingStatus, ChefProfile, ChefUnavailableDate, User, UserRole
from app.schemas.chef import AvailabilityOut, ChefOut, ChefPage, ChefUpdate, DatesIn

router = APIRouter(prefix="/chefs", tags=["chefs"])
SORTS = {
    "rating": (ChefProfile.rating_avg.desc(), ChefProfile.review_count.desc(), ChefProfile.id),
    "price_asc": (ChefProfile.price_per_session.asc(), ChefProfile.id),
    "price_desc": (ChefProfile.price_per_session.desc(), ChefProfile.id),
    "experience": (ChefProfile.years_experience.desc(), ChefProfile.id),
    "newest": (ChefProfile.id.desc(),),
}


def to_out(p: ChefProfile) -> ChefOut:
    return ChefOut(id=p.id, name=p.user.full_name, city=p.city, years=p.years_experience,
                   cuisines=p.cuisines or [], certifications=p.certifications or [],
                   rating=round(p.rating_avg or 0, 1), reviews=p.review_count, price=float(p.price_per_session or 0),
                   available=p.is_available, verified=p.is_verified, photo=p.photo_url, bio=p.bio)


def _public_conditions():
    # Only admin-approved chefs with active accounts appear in public lists.
    return [ChefProfile.is_verified.is_(True), User.is_active.is_(True)]


def _unavailable_on(d: date):
    blocked = exists().where(ChefUnavailableDate.chef_id == ChefProfile.id, ChefUnavailableDate.date == d)
    booked = exists().where(Booking.chef_id == ChefProfile.id, Booking.status == BookingStatus.accepted,
                            func.date(Booking.event_date, type_=Date) == d)
    return or_(blocked, booked)


@router.get("", response_model=ChefPage)
def list_chefs(
    q: str | None = Query(None, max_length=80, description="Search name, city, cuisine or bio"),
    city: str | None = None, cuisine: str | None = None,
    min_price: float | None = Query(None, ge=0), max_price: float | None = Query(None, ge=0),
    min_rating: float | None = Query(None, ge=0, le=5), min_experience: int | None = Query(None, ge=0),
    available_on: date | None = None, available_now: bool | None = None,
    sort: Literal["rating", "price_asc", "price_desc", "experience", "newest"] = "rating",
    page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    conds = _public_conditions()
    cuisines_text = cast(ChefProfile.cuisines, String)
    if q:
        like = f"%{q}%"
        conds.append(or_(User.full_name.ilike(like), ChefProfile.city.ilike(like), ChefProfile.bio.ilike(like), cuisines_text.ilike(like)))
    if city: conds.append(ChefProfile.city.ilike(city))
    if cuisine: conds.append(cuisines_text.ilike(f"%{cuisine}%"))
    if min_price is not None: conds.append(ChefProfile.price_per_session >= min_price)
    if max_price is not None: conds.append(ChefProfile.price_per_session <= max_price)
    if min_rating is not None: conds.append(ChefProfile.rating_avg >= min_rating)
    if min_experience is not None: conds.append(ChefProfile.years_experience >= min_experience)
    if available_now is not None: conds.append(ChefProfile.is_available.is_(available_now))
    if available_on: conds.append(~_unavailable_on(available_on))

    total = db.scalar(select(func.count(ChefProfile.id)).join(User, ChefProfile.user_id == User.id).where(*conds)) or 0
    rows = db.scalars(select(ChefProfile).join(User, ChefProfile.user_id == User.id).options(contains_eager(ChefProfile.user))
                      .where(*conds).order_by(*SORTS[sort]).limit(page_size).offset((page - 1) * page_size)).all()
    return ChefPage(items=[to_out(r) for r in rows], total=total, page=page, page_size=page_size, pages=ceil(total / page_size))


@router.get("/recommended", response_model=list[ChefOut])
def recommended(limit: int = Query(4, ge=1, le=12), db: Session = Depends(get_db)):
    """Phase 3: top-rated verified chefs. Phase 6 replaces this with the ML recommender."""
    rows = db.scalars(select(ChefProfile).join(User, ChefProfile.user_id == User.id).options(contains_eager(ChefProfile.user))
                      .where(*_public_conditions()).order_by(*SORTS["rating"]).limit(limit)).all()
    return [to_out(r) for r in rows]


def _my_profile(user: User) -> ChefProfile:
    if not user.chef_profile:
        raise HTTPException(404, "Chef profile not found")
    return user.chef_profile


@router.get("/me", response_model=ChefOut)
def my_profile(user: User = Depends(require_roles(UserRole.chef))):
    return to_out(_my_profile(user))


@router.put("/me", response_model=ChefOut)
def update_my_profile(body: ChefUpdate, user: User = Depends(require_roles(UserRole.chef)), db: Session = Depends(get_db)):
    profile = _my_profile(user)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key in ("bio", "city", "photo_url"):  # these may be cleared with null
            setattr(profile, key, value)
    db.commit()
    return to_out(profile)  # is_verified cannot be changed here: it is not part of ChefUpdate


@router.post("/me/availability/block", status_code=204)
def block_dates(body: DatesIn, user: User = Depends(require_roles(UserRole.chef)), db: Session = Depends(get_db)):
    profile = _my_profile(user)
    existing = set(db.scalars(select(ChefUnavailableDate.date).where(ChefUnavailableDate.chef_id == profile.id)))
    for d in set(body.dates) - existing:
        db.add(ChefUnavailableDate(chef_id=profile.id, date=d))
    db.commit()


@router.post("/me/availability/unblock", status_code=204)
def unblock_dates(body: DatesIn, user: User = Depends(require_roles(UserRole.chef)), db: Session = Depends(get_db)):
    profile = _my_profile(user)
    db.execute(delete(ChefUnavailableDate).where(ChefUnavailableDate.chef_id == profile.id, ChefUnavailableDate.date.in_(body.dates)))
    db.commit()


def _visible_profile(db: Session, chef_id: int, viewer: User | None) -> ChefProfile:
    p = db.get(ChefProfile, chef_id)
    if not p:
        raise HTTPException(404, "Chef not found")
    owner_or_admin = viewer and (viewer.id == p.user_id or viewer.role == UserRole.admin)
    if not (p.is_verified and p.user.is_active) and not owner_or_admin:
        raise HTTPException(404, "Chef not found")  # unapproved chefs are hidden from the public
    return p


@router.get("/{chef_id}", response_model=ChefOut)
def chef_detail(chef_id: int, db: Session = Depends(get_db), viewer: User | None = Depends(get_optional_user)):
    return to_out(_visible_profile(db, chef_id, viewer))


@router.get("/{chef_id}/availability", response_model=AvailabilityOut)
def chef_availability(chef_id: int, start: date | None = None, end: date | None = None,
                      db: Session = Depends(get_db), viewer: User | None = Depends(get_optional_user)):
    p = _visible_profile(db, chef_id, viewer)
    start = start or date.today()
    end = end or start + timedelta(days=90)
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Date range must be between 0 and 366 days")
    blocked = db.scalars(select(ChefUnavailableDate.date).where(ChefUnavailableDate.chef_id == p.id,
                         ChefUnavailableDate.date.between(start, end)).order_by(ChefUnavailableDate.date)).all()
    booked = db.scalars(select(func.date(Booking.event_date, type_=Date)).where(Booking.chef_id == p.id,
                        Booking.status == BookingStatus.accepted,
                        func.date(Booking.event_date, type_=Date).between(start, end)).distinct()).all()
    return AvailabilityOut(start=start, end=end, blocked=list(blocked), booked=sorted(booked))
