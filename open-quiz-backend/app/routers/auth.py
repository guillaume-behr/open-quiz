from time import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.audit import audit_event
from app.dependencies import DbSession
from app.models import RefreshSession, User
from app.schemas import LoginRequest, TokenResponse
from app.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
REFRESH_COOKIE = "open_quiz_refresh"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = request.app.state.settings.frontend_origin.rstrip("/")
    if origin and origin.rstrip("/") != expected:
        audit_event("auth.origin_rejected", ip=client_ip(request), origin=origin)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid origin"
        )


def set_refresh_cookie(response: Response, token: str, request: Request) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/auth",
    )


def issue_session(
    user: User, request: Request, response: Response, session: Session
) -> TokenResponse:
    settings = request.app.state.settings
    now = int(time())
    session.execute(
        delete(RefreshSession).where(
            RefreshSession.expires_at <= now,
        )
    )
    older_session_ids = list(
        session.scalars(
            select(RefreshSession.id)
            .where(
                RefreshSession.user_id == user.id,
                RefreshSession.revoked_at.is_(None),
            )
            .order_by(RefreshSession.id.desc())
            .offset(9)
        )
    )
    if older_session_ids:
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.id.in_(older_session_ids))
            .values(revoked_at=now)
        )
    refresh_token = create_refresh_token()
    session.add(
        RefreshSession(
            token_hash=hash_refresh_token(refresh_token),
            user_id=user.id,
            expires_at=now + settings.refresh_token_days * 86400,
        )
    )
    session.commit()
    set_refresh_cookie(response, refresh_token, request)
    return TokenResponse(
        access_token=create_access_token(
            user.id, settings.jwt_secret, settings.access_token_minutes
        )
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> TokenResponse:
    """Authenticate a user and start a refreshable session."""
    validate_origin(request)
    ip_address = client_ip(request)
    limiter = request.app.state.login_rate_limiter
    retry_after = limiter.retry_after(ip_address, payload.username)
    if retry_after:
        audit_event("auth.login_rate_limited", ip=ip_address)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    user = session.scalar(select(User).where(User.username == payload.username))
    encoded_password = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, encoded_password)
    if user is None or not user.is_active or not password_valid:
        limiter.record_failure(ip_address, payload.username)
        audit_event("auth.login_failed", ip=ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    limiter.clear(ip_address, payload.username)
    audit_event("auth.login_succeeded", ip=ip_address, user_id=user.id)
    return issue_session(user, request, response, session)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: DbSession,
) -> TokenResponse:
    """Rotate a valid refresh session and return a new access token."""
    validate_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    stored_session = (
        session.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_refresh_token(raw_token)
            )
        )
        if raw_token
        else None
    )
    now = int(time())
    if (
        stored_session is None
        or stored_session.revoked_at is not None
        or stored_session.expires_at <= now
    ):
        audit_event("auth.refresh_rejected", ip=client_ip(request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session",
        )

    result = session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == stored_session.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session",
        )

    user = session.get(User, stored_session.user_id)
    if user is None or not user.is_active:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session",
        )

    audit_event("auth.refresh_succeeded", ip=client_ip(request), user_id=user.id)
    return issue_session(user, request, response, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: DbSession,
) -> None:
    """Revoke the current refresh session and clear its cookie."""
    validate_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash == hash_refresh_token(raw_token),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=int(time()))
        )
        session.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    audit_event("auth.logout", ip=client_ip(request))
