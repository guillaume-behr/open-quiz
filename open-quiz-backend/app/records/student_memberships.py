from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domain.session_status import ACTIVE_SESSION_STATUSES
from app.enums import SessionStatus
from app.models import (
    QuizParticipant,
    QuizSession,
    Student,
)
from app.records.quiz_sessions import delete_quiz_session_records


def delete_unfinished_training_sessions(
    membership_ids: list[int], session: Session
) -> None:
    """Remove disposable training attempts before their students disappear."""
    if not membership_ids:
        return
    training_session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                QuizParticipant.student_id.in_(membership_ids),
                QuizSession.training_question_bank_id.is_not(None),
                QuizSession.status != SessionStatus.FINISHED,
            )
        )
    )
    if not training_session_ids:
        return
    delete_quiz_session_records(training_session_ids, session)


def revoke_student_participations(
    membership_id: int,
    session: Session,
) -> list[int]:
    """Invalidate quiz capabilities after an account security change.

    Returns the open sessions the student was taking part in, which they
    have now left: their live views need telling.
    """
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == membership_id)
        .values(access_token_hash=None)
    )
    active_session_ids = select(QuizSession.id).where(
        QuizSession.status.in_(ACTIVE_SESSION_STATUSES)
    )
    return list(
        session.scalars(
            update(QuizParticipant)
            .where(
                QuizParticipant.student_id == membership_id,
                QuizParticipant.session_id.in_(active_session_ids),
                QuizParticipant.left_at.is_(None),
            )
            .values(left_at=datetime.now(UTC))
            .returning(QuizParticipant.session_id)
        )
    )


def delete_student_membership(membership_id: int, session: Session) -> None:
    delete_unfinished_training_sessions([membership_id], session)
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
    session.execute(delete(Student).where(Student.id == membership_id))
