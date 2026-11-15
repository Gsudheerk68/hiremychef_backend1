from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:  # Google-only account: no password login
        return False
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False



def create_token(subject: int, purpose: str = "access", minutes: int | None = None) -> str:
    s = get_settings()
    minutes = minutes or (s.access_token_expire_minutes if purpose == "access" else s.reset_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "purpose": purpose, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def decode_token(token: str, purpose: str = "access") -> int | None:
    """Return the user id if the token is valid, unexpired and made for this purpose."""
    s = get_settings()
    try:
        data = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if data.get("purpose") != purpose:
        return None
    return int(data["sub"])
