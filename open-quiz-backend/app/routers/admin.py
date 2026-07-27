from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import audit_event
from app.dependencies import AdminUser, DbSession
from app.models import User
from app.schemas import UserCreate, UserResponse
from app.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.get("/users", response_model=list[UserResponse])
def list_users(_: AdminUser, session: DbSession) -> list[User]:
    """Return all users to an authenticated administrator."""
    return list(session.scalars(select(User).order_by(User.created_at.desc())))


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    request: Request,
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
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already in use",
        ) from None
    session.refresh(user)
    audit_event(
        "admin.user_created",
        actor_id=admin_user.id,
        created_user_id=user.id,
        ip=request.client.host if request.client else "unknown",
    )
    return user
