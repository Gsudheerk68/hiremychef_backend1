from datetime import datetime
from sqlalchemy import Text, Integer, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_rating_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)  # one review per booking
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    chef_id: Mapped[int] = mapped_column(ForeignKey("chef_profiles.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="review")
