from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.grading import compute_final_scores
from app.models import Quiz, QuizAnswer, QuizParticipant, QuizSession
from app.quiz_session_records import delete_quiz_session_records
from app.session_status import ACTIVE_SESSION_STATUSES


def _active_sessions_before(
    cutoff: datetime, mode: str, session: Session
) -> list[QuizSession]:
    return list(
        session.scalars(
            select(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == mode,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
                QuizSession.created_at <= cutoff,
            )
        )
    )


def close_abandoned_sessions(cutoff: datetime, session: Session) -> tuple[int, int]:
    """Settle sessions their teacher never came back to close.

    A session only leaves an active status when its owner opens the dashboard,
    so a teacher who is disabled or who has left keeps participant names,
    answers and monitoring events alive forever. This sweep is the owner-free
    path: a quiz lasts at most eight hours, so anything still open long past
    the cutoff is over.

    An exam that collected answers is graded and then kept under the ordinary
    result retention; one that collected none holds nothing but the names of a
    waiting room, and training attempts are disposable, so both are deleted.

    Returns the number of sessions finished and the number deleted.
    """
    finished = 0
    discarded: list[int] = []
    for quiz_session in _active_sessions_before(cutoff, "exam", session):
        answered = session.scalar(
            select(QuizAnswer.id)
            .where(QuizAnswer.session_id == quiz_session.id)
            .limit(1)
        )
        if answered is None:
            discarded.append(quiz_session.id)
            continue
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.session_id == quiz_session.id)
            .values(current_position=None)
        )
        quiz_session.status = "finished"
        compute_final_scores(quiz_session, session)
        finished += 1

    discarded.extend(
        quiz_session.id
        for quiz_session in _active_sessions_before(cutoff, "training", session)
    )
    delete_quiz_session_records(discarded, session)
    return finished, len(discarded)


def expired_training_session_ids(cutoff: datetime, session: Session) -> list[int]:
    """List finished training attempts past their retention."""
    return list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == "training",
                QuizSession.status == "finished",
                QuizSession.created_at <= cutoff,
            )
        )
    )
