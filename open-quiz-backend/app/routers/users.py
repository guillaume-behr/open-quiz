from fastapi import APIRouter

from app.dependencies import CurrentUser
from app.models import User
from app.schemas import UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return user
