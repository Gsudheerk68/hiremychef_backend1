from datetime import date
from pydantic import BaseModel, Field, field_validator


class ChefOut(BaseModel):
    """Field names match what the React frontend already uses."""
    id: int
    name: str
    city: str | None
    years: int
    cuisines: list[str]
    certifications: list[str]
    rating: float
    reviews: int
    price: float
    available: bool
    verified: bool
    photo: str | None
    bio: str | None


class ChefPage(BaseModel):
    items: list[ChefOut]
    total: int
    page: int
    page_size: int
    pages: int


class ChefUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=2000)
    city: str | None = Field(default=None, max_length=80)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    cuisines: list[str] | None = Field(default=None, max_length=10)
    certifications: list[str] | None = Field(default=None, max_length=10)
    price_per_session: float | None = Field(default=None, ge=0, le=1_000_000)
    photo_url: str | None = Field(default=None, max_length=500)
    is_available: bool | None = None

    @field_validator("cuisines", "certifications")
    @classmethod
    def clean_list(cls, v):
        if v is None:
            return v
        out = [x.strip() for x in v if x.strip()]
        if any(len(x) > 60 for x in out):
            raise ValueError("each item must be 60 characters or fewer")
        return out

    @field_validator("photo_url")
    @classmethod
    def http_only(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("photo_url must start with http:// or https://")
        return v


class DatesIn(BaseModel):
    dates: list[date] = Field(min_length=1, max_length=60)


class AvailabilityOut(BaseModel):
    start: date
    end: date
    blocked: list[date]  # set by the chef
    booked: list[date]   # accepted bookings
