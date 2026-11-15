import os.environ["ML_RANKER_ENABLED"] = "0"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app as api
from app.models import User, UserRole


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = override
    with Session() as db:
        db.add(User(email="admin@x.com", full_name="Admin", hashed_password=hash_password("AdminPass123"), role=UserRole.admin))
        db.commit()
    c = TestClient(api)
    c.Session = Session  # lets tests insert rows directly
    yield c
    api.dependency_overrides.clear()
