from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, String, Text, Integer, Numeric, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.enums import BookingStatus


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chef_id: Mapped[int] = mapped_column(ForeignKey("chef_profiles.id"), index=True)
    service_type: Mapped[str] = mapped_column(String(60))
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_day: Mapped[date] = mapped_column(Date, index=True)  # India calendar day of the event
    guests: Mapped[int] = mapped_column(Integer)
    cuisine: Mapped[str | None] = mapped_column(String(60))
    location: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    estimated_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.pending, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["User"] = relationship(foreign_keys=[customer_id])
    chef: Mapped["ChefProfile"] = relationship(back_populates="bookings")
    review: Mapped["Review | None"] = relationship(back_populates="booking", uselist=False)
