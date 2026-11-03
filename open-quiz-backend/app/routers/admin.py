from time import time

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.audit import audit_event
from app.auth_guards import password_rate_subject, two_factor_rate_subject
from app.dependencies import AdminUser, DbSession
from app.enums import QuizMode
from app.errors import ApiError, ErrorCode
from app.grade_levels import ensure_default_grade_levels
from app.models import (
    AuthenticationChallenge,
    Quiz,
    QuizSession,
    RefreshSession,
    TwoFactorCredential,
    User,
)
from app.pagination import (
    Paging,
)
from app.schemas import (
    UserCreate,
    UserCredentialReset,
    UserResponse,
    UserStatusUpdate,
)
from app.security import hash_password
from app.session_status import ACTIVE_SESSION_STATUSES
from app.user_records import delete_user_records

router = APIRouter(prefix="/api/admin", tags=["administration"])


def professor_account(user_id: int, session: DbSession) -> User:
    user = session.get(User, user_id)
    if user is None or user.is_admin:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.TEACHER_NOT_FOUND,
            "Compte enseignant introuvable",
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
    paging: Paging,
) -> list[User]:
    """Return one page of users to an authenticated administrator."""
    total = session.scalar(select(func.count()).select_from(User)) or 0
    paging.set_total(total)
    return list(
        session.scalars(
            select(User)
            .order_by(User.display_name, User.username, User.id)
            .offset(paging.offset)
            .limit(paging.page_size)
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
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.USERNAME_TAKEN,
            "Cet identifiant est déjà utilisé",
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
    limiter.clear_subject(password_rate_subject(user.username))
    limiter.clear_subject(two_factor_rate_subject(user.id))
    request.app.state.two_factor_daily_rate_limiter.clear_subject(
        two_factor_rate_subject(user.id)
    )
    session.refresh(user)
    audit_event(
        "admin.user_credentials_reset",
        actor_id=admin_user.id,
        user_id=user.id,
        reset_two_factor=payload.reset_two_factor,
    )
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    admin_user: AdminUser,
    session: DbSession,
) -> Response:
    """Erase a professor account and every record it owns.

    Deactivating a departing teacher leaves their classes, students and
    results in place with no term, so an erasure request has to have a path
    that actually removes them.
    """
    user = professor_account(user_id, session)
    running = session.scalar(
        select(QuizSession.id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            Quiz.owner_id == user.id,
            Quiz.mode == QuizMode.EXAM,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .limit(1)
    )
    if running is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.TEACHER_IN_ACTIVE_EXAM,
            "Cet enseignant anime une session d’examen en cours",
        )
    delete_user_records(user.id, session)
    session.commit()
    audit_event(
        "admin.user_deleted",
        actor_id=admin_user.id,
        deleted_user_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
