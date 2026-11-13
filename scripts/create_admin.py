"""Create the first admin account (admins cannot self-register).
Usage: python -m scripts.create_admin admin@example.com "Admin Name" StrongPass123"""
import sys
from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, UserRole

email, name, password = sys.argv[1].lower(), sys.argv[2], sys.argv[3]
with SessionLocal() as db:
    if db.scalar(select(User).where(User.email == email)):
        sys.exit("User already exists")
    db.add(User(email=email, full_name=name, hashed_password=hash_password(password), role=UserRole.admin))
    db.commit()
    print("Admin created:", email)
