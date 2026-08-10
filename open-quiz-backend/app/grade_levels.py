from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GradeLevel

DEFAULT_GRADE_LEVELS = ("Seconde", "Première", "Terminale")


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
    session.add_all(
        GradeLevel(owner_id=owner_id, name=name)
        for name in DEFAULT_GRADE_LEVELS
        if name not in existing
    )
