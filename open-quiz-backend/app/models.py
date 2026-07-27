from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RefreshSessionFamily(Base):
    __tablename__ = "refresh_session_families"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("refresh_sessions.id"), primary_key=True
    )
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TwoFactorCredential(Base):
    __tablename__ = "two_factor_credentials"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_secret: Mapped[str] = mapped_column(String(255))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuthenticationChallenge(Base):
    __tablename__ = "authentication_challenges"

    token_id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LoginFailure(Base):
    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    limiter_key: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[int] = mapped_column(Integer, index=True)


class SecurityState(Base):
    __tablename__ = "security_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
