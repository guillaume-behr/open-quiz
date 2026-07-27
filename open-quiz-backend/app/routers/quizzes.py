from fastapi import APIRouter

from app.dependencies import CurrentUser

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.get("")
def list_quizzes(_: CurrentUser) -> list[dict[str, object]]:
    """Return the authenticated professor's quizzes.

    Quiz persistence will be added in the next API slice.
    """
    return []
