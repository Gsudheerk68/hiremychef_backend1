from datetime import date
from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ChefUnavailableDate(Base):
    """A day the chef has blocked. Chefs are available by default; accepted bookings also block a day."""
    __tablename__ = "chef_unavailable_dates"
    __table_args__ = (UniqueConstraint("chef_id", "date", name="uq_chef_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chef_id: Mapped[int] = mapped_column(ForeignKey("chef_profiles.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(120))
