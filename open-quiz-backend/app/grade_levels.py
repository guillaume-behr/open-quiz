from sqlalchemy import select

from app.models import GradeLevel


def ensure_grade_level(owner_id: int, name: str, session) -> GradeLevel:
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
