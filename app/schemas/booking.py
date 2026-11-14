from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.core.timeutils import now_local, to_utc
from app.services.pricing import SERVICE_FACTORS

ServiceType = Literal[tuple(SERVICE_FACTORS)]  # type: ignore[valid-type]


class BookingCreate(BaseModel):
    """Extra fields such as `estimated_price` are ignored: the server computes the price."""
    chef_id: int
    service_type: ServiceType
    event_date: datetime  # local time without offset, e.g. 2026-12-25T19:00:00
    guests: int = Field(ge=1, le=500)
    cuisine: str | None = Field(default=None, max_length=60)
    location: str = Field(min_length=3, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("event_date")
    @classmethod
    def in_future(cls, v: datetime) -> datetime:
        if to_utc(v) <= now_local():
            raise ValueError("Event date must be in the future")
        return v


class EstimateIn(BaseModel):
    chef_id: int
    guests: int = Field(ge=1, le=500)
    service_type: ServiceType


class EstimateOut(BaseModel):
    estimated_price: int


class BookingOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    chef_id: int
    chef_name: str
    chef_photo: str | None
    service_type: str
    event_date: datetime  # India wall-clock, no offset
    guests: int
    cuisine: str | None
    location: str
    notes: str | None
    estimated_price: float
    status: str
    created_at: datetime
    reviewed: bool


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    id: int
    customer_name: str
    rating: int
    comment: str | None
    created_at: datetime
