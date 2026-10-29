from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class OAuthIn(BaseModel):
    provider: str = Field(pattern="^(google|apple)$")
    id_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    phone: str | None
    roles: list[str]
    email_verified: bool
    phone_verified: bool
    identity_verified: bool
    rating_avg: float
    rating_count: int
    driver_status: str | None = None
    push_token: str | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    push_token: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=500)
