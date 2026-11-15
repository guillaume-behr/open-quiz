"""The password step of a staff sign-in."""

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit_event
from app.core.auth_guards import (
    check_password,
    password_rate_subject,
    trusted_password_rate_subject,
)
from app.core.errors import ApiError, ErrorCode
from app.models import TwoFactorCredential, User
from app.records.users import username_matches
from app.schemas.accounts import LoginRequest
from app.services.two_factor import browser_is_trusted


def password_attempt_subject(
    username: str, user: User | None, request: Request, session: Session
) -> str:
    """The bucket this password attempt counts against.

    A browser the account trusts has a bucket of its own, so that wrong
    passwords sent from elsewhere cannot lock the owner out of it.
    """
    if user is not None:
        two_factor = session.get(TwoFactorCredential, user.id)
        if two_factor is not None and browser_is_trusted(request, user, two_factor):
            return trusted_password_rate_subject(user.id)
    return password_rate_subject(username)


def password_user(payload: LoginRequest, request: Request, session: Session) -> User:
    """The active account whose password this is, within the attempt limits."""
    account = session.scalar(select(User).where(username_matches(payload.username)))
    active_user = account if account is not None and account.is_active else None
    user, upgraded_hash = check_password(
        payload.password,
        password_attempt_subject(payload.username, account, request, session),
        active_user,
        active_user.password_hash if active_user else None,
        request,
        session,
        audit_prefix="auth",
    )
    if upgraded_hash is not None:
        # Tokens are bound to the hash, so they are issued from the new one.
        user.password_hash = upgraded_hash
        session.commit()
        audit_event("auth.password_hash_upgraded", user_id=user.id)
    return user


def require_audience(user: User, audience: str | None) -> None:
    """Refuse a teacher account on the admin sign-in, and the reverse."""
    if audience == "professor" and user.is_admin:
        audit_event(
            "auth.login_wrong_audience",
            user_id=user.id,
            audience=audience,
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_PROFESSOR_ACCOUNT_REQUIRED,
            "Ce compte n’est pas un compte enseignant",
        )
    if audience == "admin" and not user.is_admin:
        audit_event(
            "auth.login_wrong_audience",
            user_id=user.id,
            audience=audience,
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_ADMIN_ACCOUNT_REQUIRED,
            "Ce compte n’est pas un compte administrateur",
        )
