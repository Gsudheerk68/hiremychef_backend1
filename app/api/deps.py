from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User, UserRole

bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    unauth = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if not creds:
        raise unauth
    user_id = decode_token(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise unauth
    return user


def require_roles(*roles: UserRole):
    """Dependency factory: only the listed roles may call the endpoint."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return user
    return checker


def get_optional_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User | None:
    """For public endpoints that behave slightly differently for a logged-in owner or admin."""
    if not creds:
        return None
    user_id = decode_token(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None
