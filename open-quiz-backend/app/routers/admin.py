from time import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.audit import audit_event
from app.dependencies import AdminUser, DbSession
from app.grade_levels import ensure_default_grade_levels
from app.models import (
    AuthenticationChallenge,
    RefreshSession,
    TwoFactorCredential,
    User,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.routers.auth import password_rate_subject, two_factor_rate_subject
from app.schemas import (
    UserCreate,
    UserCredentialReset,
    UserResponse,
    UserStatusUpdate,
)
from app.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["administration"])


def professor_account(user_id: int, session: DbSession) -> User:
    user = session.get(User, user_id)
    if user is None or user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte enseignant introuvable",
        )
    return user


def revoke_user_sessions(user_id: int, session: DbSession) -> None:
    session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=int(time()))
    )
    session.execute(
        delete(AuthenticationChallenge).where(
            AuthenticationChallenge.user_id == user_id
        )
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    _: AdminUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> list[User]:
    """Return one page of users to an authenticated administrator."""
    total = session.scalar(select(func.count()).select_from(User)) or 0
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    return list(
        session.scalars(
            select(User)
            .order_by(User.display_name, User.username, User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    admin_user: AdminUser,
    session: DbSession,
) -> User:
    """Create a professor account as an authenticated administrator."""
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    try:
        session.flush()
        ensure_default_grade_levels(user.id, session)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet identifiant est déjà utilisé",
        ) from None
    session.refresh(user)
    audit_event(
        "admin.user_created",
        actor_id=admin_user.id,
        created_user_id=user.id,
    )
    return user


@router.post(
    "/users/{user_id}/status",
    response_model=UserResponse,
)
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    admin_user: AdminUser,
    session: DbSession,
) -> User:
    """Enable or disable a professor and revoke access when disabled."""
    user = professor_account(user_id, session)
    status_changed = user.is_active != payload.is_active
    user.is_active = payload.is_active
    if status_changed:
        user.access_token_generation += 1
    if status_changed and not payload.is_active:
        revoke_user_sessions(user.id, session)
    session.commit()
    session.refresh(user)
    audit_event(
        "admin.user_status_updated",
        actor_id=admin_user.id,
        user_id=user.id,
        is_active=user.is_active,
    )
    return user


@router.post(
    "/users/{user_id}/credentials",
    response_model=UserResponse,
)
def reset_user_credentials(
    user_id: int,
    payload: UserCredentialReset,
    request: Request,
    admin_user: AdminUser,
    session: DbSession,
) -> User:
    """Reset a professor password, sessions, and optionally 2FA enrollment."""
    user = professor_account(user_id, session)
    user.password_hash = hash_password(payload.password)
    revoke_user_sessions(user.id, session)
    if payload.reset_two_factor:
        session.execute(
            delete(TwoFactorCredential).where(TwoFactorCredential.user_id == user.id)
        )
    session.commit()
    limiter = request.app.state.login_rate_limiter
    limiter.clear_subject(session, password_rate_subject(user.username))
    limiter.clear_subject(session, two_factor_rate_subject(user.id))
    session.refresh(user)
    audit_event(
        "admin.user_credentials_reset",
        actor_id=admin_user.id,
        user_id=user.id,
        reset_two_factor=payload.reset_two_factor,
    )
    return user
