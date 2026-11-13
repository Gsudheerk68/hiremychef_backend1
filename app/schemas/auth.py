from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.enums import UserRole


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    # Admins can never self-register; only customer or chef is accepted.
    role: Literal["customer", "chef"] = "customer"
    # Chef-only optional fields
    city: str | None = None
    cuisines: list[str] = []
    years_experience: int = Field(default=0, ge=0, le=60)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=64)
    role: str | None = None  # sent by the frontend demo; ignored (role comes from the database)


class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=64)
