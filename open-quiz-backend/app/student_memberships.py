from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models import MakeupSessionSelection, QuizParticipant, Student


def delete_student_membership(membership_id: int, session: Session) -> None:
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == membership_id)
        .values(student_id=None)
    )
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.student_id == membership_id
        )
    )
    session.execute(delete(Student).where(Student.id == membership_id))
