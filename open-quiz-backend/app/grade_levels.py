"""Grade levels: the per-teacher vocabulary that categorizes classes and banks.

A class or a question bank stores its level by name; the GradeLevel rows hold
the list a teacher picks from. The routes live with the classes, under
/api/classes/grade-levels.
"""

from fastapi import status
from sqlalchemy import Select, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode
from app.models import GradeLevel, QuestionBank, StudentClass, utc_now

DEFAULT_GRADE_LEVELS = ("2nd", "1ere", "Tle")


def grade_level_order(column):
    """Sort the default lycée levels chronologically, then custom levels."""
    return case(
        {name: position for position, name in enumerate(DEFAULT_GRADE_LEVELS)},
        value=column,
        else_=len(DEFAULT_GRADE_LEVELS),
    )


def owned_grade_levels(owner_id: int, session: Session) -> list[GradeLevel]:
    return list(
        session.scalars(
            select(GradeLevel)
            .where(GradeLevel.owner_id == owner_id)
            .order_by(
                grade_level_order(GradeLevel.name),
                GradeLevel.name,
                GradeLevel.id,
            )
        )
    )


def grade_level_import_context(
    owner_id: int, session: Session
) -> tuple[list[str], str]:
    names = [level.name for level in owned_grade_levels(owner_id, session)]
    comment = (
        f"Niveaux de classe disponibles : {', '.join(names)}."
        if names
        else "Aucun niveau de classe n’est encore défini."
    )
    return names, comment


def ensure_grade_level(owner_id: int, name: str, session: Session) -> str:
    """The name of the teacher's level matching ``name`` ignoring case.

    The level is created if it does not exist. A concurrent request creating
    it first makes the insert do nothing: the re-read then finds that one.
    Callers store the returned name, so a class and a bank of "tle" and "Tle"
    share one level.
    """
    session.execute(
        insert(GradeLevel)
        .values(owner_id=owner_id, name=name, created_at=utc_now())
        .on_conflict_do_nothing()
    )
    return session.execute(
        _named(owner_id, name).with_only_columns(GradeLevel.name)
    ).scalar_one()


def ensure_default_grade_levels(owner_id: int, session: Session) -> None:
    existing = set(
        session.scalars(select(GradeLevel.name).where(GradeLevel.owner_id == owner_id))
    )
    # Defaults initialize a new account only. Existing installations keep their
    # own vocabulary instead of receiving renamed duplicates.
    if existing:
        return
    session.add_all(
        GradeLevel(owner_id=owner_id, name=name) for name in DEFAULT_GRADE_LEVELS
    )


def list_grade_levels(owner_id: int, session: Session) -> list[GradeLevel]:
    """The teacher's levels, seeded with the defaults on first use."""
    ensure_default_grade_levels(owner_id, session)
    try:
        session.commit()
    except IntegrityError:
        # Two initial dashboard requests can try to seed the same defaults.
        # The unique constraint decides the winner; the loser can safely read
        # the now-persisted rows instead of turning first login into a 500.
        session.rollback()
    return owned_grade_levels(owner_id, session)


def _named(owner_id: int, name: str) -> Select[GradeLevel]:
    # Both sides through PostgreSQL's lower(), as the unique index compares.
    return select(GradeLevel).where(
        GradeLevel.owner_id == owner_id,
        func.lower(GradeLevel.name) == func.lower(name),
    )


def create_grade_level(owner_id: int, name: str, session: Session) -> GradeLevel:
    """The level of that name, ignoring case, created if it does not exist."""
    ensure_grade_level(owner_id, name, session)
    session.commit()
    return session.execute(_named(owner_id, name)).scalar_one()


def delete_grade_level(owner_id: int, grade_level_id: int, session: Session) -> None:
    grade_level = session.scalar(
        select(GradeLevel).where(
            GradeLevel.id == grade_level_id,
            GradeLevel.owner_id == owner_id,
        )
    )
    if grade_level is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.GRADE_LEVEL_NOT_FOUND,
            "Niveau introuvable",
        )
    is_used = (
        session.scalar(
            select(StudentClass.id).where(
                StudentClass.owner_id == owner_id,
                StudentClass.grade_level == grade_level.name,
            )
        )
        is not None
        or session.scalar(
            select(QuestionBank.id).where(
                QuestionBank.owner_id == owner_id,
                QuestionBank.grade_level == grade_level.name,
            )
        )
        is not None
    )
    if is_used:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.GRADE_LEVEL_IN_USE,
            "Impossible de supprimer ce niveau car des classes, des élèves "
            "ou des banques de questions y sont encore associés",
        )
    session.delete(grade_level)
    session.commit()
