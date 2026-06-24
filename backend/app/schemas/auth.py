from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _normalize_email(value: str) -> str:
    """Canonicalise email to lowercase so password and Google (OIDC) auth match the
    same account and the unique index can't be bypassed with case variants."""
    return value.strip().lower()


# EmailStr validates format first, then we lowercase it.
NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]


class UserCreate(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    email_verified: bool
    totp_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: NormalizedEmail


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    secret: str
    uri: str


class TOTPVerifyRequest(BaseModel):
    code: str
