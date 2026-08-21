from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import GradeLevel

DEFAULT_GRADE_LEVELS = ("2nd", "1ere", "Tle")


def grade_level_order(column):
    """Sort the default lycée levels chronologically, then custom levels."""
    return case(
        {name: position for position, name in enumerate(DEFAULT_GRADE_LEVELS)},
        value=column,
        else_=len(DEFAULT_GRADE_LEVELS),
    )


def grade_level_import_context(
    owner_id: int, session: Session
) -> tuple[list[str], str]:
    names = list(
        session.scalars(
            select(GradeLevel.name)
            .where(GradeLevel.owner_id == owner_id)
            .order_by(
                grade_level_order(GradeLevel.name),
                GradeLevel.name,
                GradeLevel.id,
            )
        )
    )
    comment = (
        f"Niveaux de classe disponibles : {', '.join(names)}."
        if names
        else "Aucun niveau de classe n’est encore défini."
    )
    return names, comment


def ensure_grade_level(owner_id: int, name: str, session: Session) -> GradeLevel:
    with session.no_autoflush:
        grade_level = session.scalar(
            select(GradeLevel).where(
                GradeLevel.owner_id == owner_id,
                GradeLevel.name == name,
            )
        )
    if grade_level is None:
        grade_level = GradeLevel(owner_id=owner_id, name=name)
        session.add(grade_level)
    return grade_level


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
