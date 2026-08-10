from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.models import GradeLevel, QuestionBank, StudentClass
from app.schemas import GradeLevelCreate, GradeLevelResponse

router = APIRouter(prefix="/api/grade-levels", tags=["grade levels"])


@router.get("", response_model=list[GradeLevelResponse])
def list_grade_levels(
    professor: ProfessorUser,
    session: DbSession,
) -> list[GradeLevel]:
    return list(
        session.scalars(
            select(GradeLevel)
            .where(GradeLevel.owner_id == professor.id)
            .order_by(GradeLevel.name, GradeLevel.id)
        )
    )


@router.post(
    "",
    response_model=GradeLevelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_grade_level(
    payload: GradeLevelCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> GradeLevel:
    existing = session.scalar(
        select(GradeLevel).where(
            GradeLevel.owner_id == professor.id,
            func.lower(GradeLevel.name) == payload.name.lower(),
        )
    )
    if existing is not None:
        return existing
    grade_level = GradeLevel(owner_id=professor.id, name=payload.name)
    session.add(grade_level)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(GradeLevel).where(
                GradeLevel.owner_id == professor.id,
                func.lower(GradeLevel.name) == payload.name.lower(),
            )
        )
        if existing is None:
            raise
        return existing
    session.refresh(grade_level)
    return grade_level


@router.delete("/{grade_level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grade_level(
    grade_level_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    grade_level = session.scalar(
        select(GradeLevel).where(
            GradeLevel.id == grade_level_id,
            GradeLevel.owner_id == professor.id,
        )
    )
    if grade_level is None:
        raise HTTPException(status_code=404, detail="Niveau introuvable")
    is_used = (
        session.scalar(
            select(StudentClass.id).where(
                StudentClass.owner_id == professor.id,
                StudentClass.grade_level == grade_level.name,
            )
        )
        is not None
        or session.scalar(
            select(QuestionBank.id).where(
                QuestionBank.owner_id == professor.id,
                QuestionBank.grade_level == grade_level.name,
            )
        )
        is not None
    )
    if is_used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce niveau est encore utilisé",
        )
    session.delete(grade_level)
    session.commit()
