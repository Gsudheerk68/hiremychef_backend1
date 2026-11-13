from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import ChefProfile, User, UserRole
from app.schemas.auth import UserOut
from app.schemas.chef import ChefOut
from app.api.chefs import to_out

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
