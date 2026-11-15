import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.google_auth import GoogleAuthError, verify_google_credential
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models import ChefProfile, User, UserRole
from app.schemas.auth import (ForgotPasswordRequest, GoogleLoginOut, GoogleLoginRequest, LoginRequest,
                              RegisterRequest, ResetPasswordRequest, TokenOut, UserOut)

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("auth")


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=body.email, full_name=body.full_name, phone=body.phone,
                hashed_password=hash_password(body.password), role=UserRole(body.role))
    if body.role == "chef":
        # Chef profiles start unverified; an admin must approve them before they are listed.
        user.chef_profile = ChefProfile(city=body.city, cuisines=body.cuisines,
                                        years_experience=body.years_experience, is_verified=False)
    db.add(user)
    db.commit()
    return TokenOut(token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Same message for unknown email and wrong password: do not reveal which accounts exist.
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    return TokenOut(token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/google", response_model=GoogleLoginOut)
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Sign in or sign up with a Google ID token. Returns the same app token as /login."""
    try:
        g = verify_google_credential(body.credential)
    except GoogleAuthError as e:
        raise HTTPException(e.status_code, str(e))

    user = db.scalar(select(User).where(User.google_sub == g["sub"]))
    if not user:
        user = db.scalar(select(User).where(User.email == g["email"]))
        if user and user.google_sub and user.google_sub != g["sub"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "This email is linked to a different Google account")

    if user:
        if user.role == UserRole.admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins must sign in with email and password")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
        if not user.google_sub:  # first Google sign-in on an existing account: Google verified the email, so link it
            user.google_sub = g["sub"]
            db.commit()
        return GoogleLoginOut(token=create_token(user.id), user=UserOut.model_validate(user))

    # brand-new person: we need to know whether they are a customer or a chef
    if body.role is None:
        return GoogleLoginOut(needs_role=True, email=g["email"], name=g["name"])

    user = User(email=g["email"], full_name=g["name"][:120], phone=body.phone, hashed_password=None,
                google_sub=g["sub"], role=UserRole(body.role))
    if body.role == "chef":
        user.chef_profile = ChefProfile(city=body.city, cuisines=body.cuisines,
                                        years_experience=body.years_experience, is_verified=False)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two requests raced to create the same account
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not create the account. Please try again.")
    return GoogleLoginOut(token=create_token(user.id), user=UserOut.model_validate(user), is_new=True)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user:
        token = create_token(user.id, purpose="reset")
        # Phase 2: no email service yet. In development the token is logged; production will email a link.
        if get_settings().environment == "development":
            log.warning("Password reset token for %s: %s", user.email, token)
    return {"message": "If that email is registered, a reset link has been sent"}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    user_id = decode_token(body.token, purpose="reset")
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated"}
