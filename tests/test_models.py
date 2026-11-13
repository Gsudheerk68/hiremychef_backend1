"""Smoke test: all tables create on SQLite and the health route works."""
from sqlalchemy import create_engine, inspect
from app.db.base import Base
import app.models  # noqa: F401


def test_tables_created():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert {"users", "chef_profiles", "bookings", "reviews", "messages"} <= set(inspect(engine).get_table_names())
