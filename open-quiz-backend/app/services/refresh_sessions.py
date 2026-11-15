"""Staff refresh sessions: the cookie, its proof, issuing and rotating them.

Each refresh session belongs to a family; presenting one already rotated
means its cookie leaked, and the whole family is revoked.
"""

from hmac import compare_digest
from time import time

from fastapi import Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import audit_event
from app.core.config import app_settings
from app.core.errors import ApiError, ErrorCode
from app.core.security import (
    access_token_version,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    refresh_request_proof,
)
from app.models import (
    RefreshSession,
    RefreshSessionFamily,
    TwoFactorCredential,
    User,
)
from app.schemas.accounts import TokenResponse
from app.services.credentials import revoke_refresh_sessions, revoke_user_sessions

REFRESH_COOKIE = "open_quiz_refresh"


REFRESH_PROOF_HEADER = "X-Refresh-Proof"


# Signed-in devices kept per account; signing in on one more drops the oldest.
MAX_REFRESH_SESSIONS_PER_USER = 10


SECONDS_PER_DAY = 86400


def set_refresh_cookie(
    response: Response,
    token: str,
    request: Request,
    expires_at: int,
) -> None:
    settings = app_settings(request)
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=max(0, expires_at - int(time())),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response, request: Request) -> None:
    settings = app_settings(request)
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/auth",
        secure=settings.cookie_secure,
        samesite="strict",
    )


def validate_refresh_proof(request: Request, raw_token: str | None) -> bool:
    supplied_proof = request.headers.get(REFRESH_PROOF_HEADER)
    if raw_token is None or supplied_proof is None:
        return False
    expected_proof = refresh_request_proof(
        raw_token,
        app_settings(request).jwt_secret,
    )
    return compare_digest(supplied_proof, expected_proof)


def issue_session(
    user: User,
    request: Request,
    response: Response,
    session: Session,
    *,
    family_id: str | None = None,
    expires_at: int | None = None,
) -> TokenResponse:
    settings = app_settings(request)
    now = int(time())
    session_expires_at = (
        expires_at
        if expires_at is not None
        else now + settings.refresh_token_days * SECONDS_PER_DAY
    )
    # Expired sessions are swept by the hourly maintenance, not on every
    # sign-in and refresh; an expired one is refused anyway.
    older_session_ids = list(
        session.scalars(
            select(RefreshSession.id)
            .where(
                RefreshSession.user_id == user.id,
                RefreshSession.revoked_at.is_(None),
            )
            .order_by(RefreshSession.id.desc())
            # The session issued below takes the last place.
            .offset(MAX_REFRESH_SESSIONS_PER_USER - 1)
        )
    )
    if older_session_ids:
        # Sessions past the cap are deleted, not revoked: a revoked token that
        # comes back reads as a stolen cookie replayed, while the old device
        # merely signing in again is no such thing. Unknown, it gets a plain
        # 401.
        session.execute(
            delete(RefreshSessionFamily).where(
                RefreshSessionFamily.session_id.in_(older_session_ids)
            )
        )
        session.execute(
            delete(RefreshSession).where(RefreshSession.id.in_(older_session_ids))
        )
    refresh_token = create_refresh_token()
    refresh_session = RefreshSession(
        token_hash=hash_refresh_token(refresh_token),
        user_id=user.id,
        expires_at=session_expires_at,
    )
    session.add(refresh_session)
    session.flush()
    session.add(
        RefreshSessionFamily(
            session_id=refresh_session.id,
            family_id=family_id or hash_refresh_token(create_refresh_token()),
        )
    )
    session.commit()
    set_refresh_cookie(response, refresh_token, request, session_expires_at)
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            settings.jwt_secret,
            settings.access_token_minutes,
            access_token_version(
                user.password_hash,
                settings.jwt_secret,
                user.access_token_generation,
            ),
            session_expires_at=session_expires_at,
        ),
        refresh_proof=refresh_request_proof(refresh_token, settings.jwt_secret),
    )


def revoke_refresh_family(
    session: Session,
    session_id: int,
    now: int,
) -> bool:
    family = session.get(RefreshSessionFamily, session_id)
    if family is None:
        return False
    family_session_ids = select(RefreshSessionFamily.session_id).where(
        RefreshSessionFamily.family_id == family.family_id
    )
    revoke_refresh_sessions(session, now, RefreshSession.id.in_(family_session_ids))
    session.commit()
    return True


def presented_refresh_session(
    request: Request, session: Session, now: int
) -> RefreshSession:
    """The live refresh session the cookie names, proved by this window.

    Presenting one that was already rotated means the cookie leaked: its
    whole family is revoked.
    """
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token is None:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    if not validate_refresh_proof(request, raw_token):
        audit_event("auth.refresh_proof_rejected")
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_REFRESH_PROOF_INVALID,
            "Preuve de session invalide",
        )
    stored_session = session.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == hash_refresh_token(raw_token)
        )
    )
    if stored_session is None or stored_session.expires_at <= now:
        audit_event("auth.refresh_rejected")
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    if stored_session.revoked_at is not None:
        family_revoked = revoke_refresh_family(session, stored_session.id, now)
        audit_event(
            "auth.refresh_reuse_detected",
            user_id=stored_session.user_id,
            family_revoked=family_revoked,
        )
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    return stored_session


def retire_refresh_session(
    stored_session: RefreshSession, session: Session, now: int
) -> RefreshSessionFamily:
    """Revoke the session being rotated, and return the family it belongs to."""
    # Startup revokes every live session without a family
    # (app/services/security_state.py), so the one being rotated has one, unless a
    # sign-in on another device deleted it past the session cap since it was
    # read: that cookie is simply no longer valid.
    family = session.execute(
        select(RefreshSessionFamily).where(
            RefreshSessionFamily.session_id == stored_session.id
        )
    ).scalar_one_or_none()
    if family is None:
        session.rollback()
        audit_event("auth.refresh_rejected")
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    if (
        revoke_refresh_sessions(session, now, RefreshSession.id == stored_session.id)
        != 1
    ):
        session.rollback()
        family_revoked = revoke_refresh_family(session, stored_session.id, now)
        audit_event(
            "auth.refresh_reuse_detected",
            user_id=stored_session.user_id,
            family_revoked=family_revoked,
        )
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    return family


def refreshable_user(
    stored_session: RefreshSession, session: Session, now: int
) -> User:
    """The account, unless it was disabled or lost its authenticator meanwhile."""
    user = session.get(User, stored_session.user_id)
    two_factor = session.get(TwoFactorCredential, stored_session.user_id)
    if (
        user is None
        or not user.is_active
        or two_factor is None
        or not two_factor.confirmed
    ):
        # Pending challenges stay: one may be the setup a 2FA reset started,
        # which an old tab refreshing its session must not cancel.
        revoke_user_sessions(session, stored_session.user_id, now, challenges=False)
        session.commit()
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_REFRESH_SESSION_INVALID,
            "Session de connexion invalide",
        )
    return user
