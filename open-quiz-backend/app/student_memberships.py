from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import MakeupSessionSelection, QuizParticipant, QuizSession, Student


def revoke_student_participations(
    membership_id: int,
    session: Session,
) -> None:
    """Invalidate quiz capabilities after an account security change."""
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == membership_id)
        .values(access_token_hash=None)
    )
    active_session_ids = select(QuizSession.id).where(
        QuizSession.status.in_(["waiting", "in_progress", "paused"])
    )
    session.execute(
        update(QuizParticipant)
        .where(
            QuizParticipant.student_id == membership_id,
            QuizParticipant.session_id.in_(active_session_ids),
        )
        .values(
            left_at=datetime.now(UTC),
        )
    )


def delete_student_membership(membership_id: int, session: Session) -> None:
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == membership_id)
        .values(
            student_id=None,
            access_token_hash=None,
            current_position=None,
            left_at=datetime.now(UTC),
        )
    )
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.student_id == membership_id
        )
    )
    session.execute(delete(Student).where(Student.id == membership_id))
