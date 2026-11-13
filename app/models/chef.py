from decimal import Decimal
from sqlalchemy import String, Text, Boolean, Integer, Numeric, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class ChefProfile(Base):
    __tablename__ = "chef_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    bio: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    cuisines: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    price_per_session: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    photo_url: Mapped[str | None] = mapped_column(String(500))
    rating_avg: Mapped[float] = mapped_column(default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # admin approval
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="chef_profile")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="chef")
