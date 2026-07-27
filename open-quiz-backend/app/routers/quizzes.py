from fastapi import APIRouter

from app.dependencies import ProfessorUser

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.get("")
def list_quizzes(_: ProfessorUser) -> list[dict[str, object]]:
    """Return the authenticated professor's quizzes.

    Quiz persistence will be added in the next API slice.
    """
    return []
