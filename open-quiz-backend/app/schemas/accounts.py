"""Sign-in, two-factor authentication and teacher accounts."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import validate_teacher_password


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    audience: Literal["professor", "admin"] | None = None

    @field_validator("username")
    @classmethod
    def trim_login_username(cls, value: str) -> str:
        return value.strip()


class TokenResponse(BaseModel):
    access_token: str
    refresh_proof: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret.


class LoginResponse(BaseModel):
    status: Literal["setup_required", "verification_required"]
    challenge_token: str
    secret: str | None = None
    provisioning_uri: str | None = None


class LoginSessionResponse(TokenResponse):
    """A login that needs no code: this browser passed two-factor today."""

    status: Literal["authenticated"] = "authenticated"


class LogoutRequest(BaseModel):
    # Also forget that this browser passed two-factor authentication today, as
    # "clear data from this device" asks. A plain sign-out keeps it.
    forget_browser: bool = False


# An IANA name such as "Europe/Paris" or "America/Argentina/Buenos_Aires".
TIMEZONE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+)*$")


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=1, max_length=2048)
    # [0-9], not \d: \d also matches non-ASCII digits such as "١٢٣٤٥٦".
    code: str = Field(pattern=r"^[0-9]{6}$")
    # The browser's time zone, which decides when "today" ends for the trusted
    # browser. Anything unusable falls back to UTC rather than failing a login.
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def usable_timezone(cls, value: str | None) -> str | None:
        if value is None or len(value) > 64 or not TIMEZONE_NAME_PATTERN.match(value):
            return None
        return value


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=16, max_length=256)

    _validate_password = field_validator("password")(validate_teacher_password)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserCredentialReset(BaseModel):
    password: str = Field(min_length=16, max_length=256)
    reset_two_factor: bool = True

    _validate_password = field_validator("password")(validate_teacher_password)
