from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
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


class QuestionBank(Base):
    __tablename__ = "question_banks"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "grade_level",
            "chapter",
            name="uq_question_bank_owner_classification",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    grade_level: Mapped[str] = mapped_column(String(80))
    chapter: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id"), index=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(20))
    answer_mode: Mapped[str] = mapped_column(String(20))
    answer_mode_disclosed: Mapped[bool] = mapped_column(Boolean, default=True)
    correction_mode: Mapped[str] = mapped_column(String(20))
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class QuestionCode(Base):
    __tablename__ = "question_codes"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)


class QuestionChoice(Base):
    __tablename__ = "question_choices"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_choice_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    label: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


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


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    limiter_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    window_started_at: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer)


class SecurityState(Base):
    __tablename__ = "security_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
