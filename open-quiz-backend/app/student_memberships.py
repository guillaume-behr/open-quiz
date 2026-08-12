from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    MakeupSessionSelection,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    Student,
)


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
                QuizSession.status != "finished",
            )
        )
    )
    if not training_session_ids:
        return
    session.execute(
        delete(QuizAnswer).where(QuizAnswer.session_id.in_(training_session_ids))
    )
    session.execute(
        delete(QuizParticipant).where(
            QuizParticipant.session_id.in_(training_session_ids)
        )
    )
    session.execute(
        delete(QuizSessionQuestion).where(
            QuizSessionQuestion.session_id.in_(training_session_ids)
        )
    )
    session.execute(
        delete(QuizSessionStudentQuestion).where(
            QuizSessionStudentQuestion.session_id.in_(training_session_ids)
        )
    )
    session.execute(delete(QuizSession).where(QuizSession.id.in_(training_session_ids)))


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
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.student_id == membership_id
        )
    )
    session.execute(delete(Student).where(Student.id == membership_id))
