from datetime import datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.domain.session_status import ACTIVE_SESSION_STATUSES
from app.enums import QuizMode, SessionStatus
from app.models import Quiz, QuizSession
from app.records.quiz_sessions import delete_quiz_session_records
from app.services.session_lifecycle import anyone_took_a_question, finish_session


def _active_sessions_before(
    cutoff: datetime, mode: str, session: Session
) -> list[tuple[QuizSession, Quiz]]:
    return [
        (quiz_session, quiz)
        for quiz_session, quiz in session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == mode,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
                QuizSession.created_at <= cutoff,
            )
        )
    ]


def close_abandoned_sessions(cutoff: datetime, session: Session) -> tuple[int, int]:
    """Settle sessions their teacher never came back to close.

    A running session ends with its timer, but a waiting room never launched
    or a session left paused stays active until its owner closes it, so a
    teacher who is disabled or who has left keeps participant names, answers
    and monitoring events alive forever. This sweep is the owner-free path: a
    quiz lasts at most eight hours, so anything still open long past the
    cutoff is over.

    An exam that collected answers or skips is graded and then kept under the
    ordinary result retention; one that collected neither holds nothing but
    the names of a waiting room, and training attempts are disposable, so both are deleted.

    Returns the number of sessions finished and the number deleted.
    """
    finished = 0
    discarded: list[int] = []
    for quiz_session, quiz in _active_sessions_before(cutoff, QuizMode.EXAM, session):
        # Skipped questions count as work: the exam is graded, with them at
        # zero, rather than discarded as an empty waiting room.
        if not anyone_took_a_question(quiz_session, session):
            discarded.append(quiz_session.id)
            continue
        if finish_session(
            quiz_session, quiz, session, from_statuses=ACTIVE_SESSION_STATUSES
        ):
            finished += 1

    discarded.extend(
        quiz_session.id
        for quiz_session, _ in _active_sessions_before(
            cutoff, QuizMode.TRAINING, session
        )
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
                Quiz.mode == QuizMode.TRAINING,
                QuizSession.status == SessionStatus.FINISHED,
                QuizSession.created_at <= cutoff,
            )
        )
    )


def retained_exam_result(cutoff: datetime) -> ColumnElement[bool]:
    """Whether a finished exam session is still within its result retention.

    Results read by teachers apply this filter, so an expired result is never
    shown or exported even before the next maintenance pass deletes it.
    """
    return or_(QuizSession.started_at.is_(None), QuizSession.started_at > cutoff)


def expired_exam_result_ids(cutoff: datetime, session: Session) -> list[int]:
    """List finished exam sessions past their result retention."""
    return list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == QuizMode.EXAM,
                QuizSession.status == SessionStatus.FINISHED,
                ~retained_exam_result(cutoff),
            )
        )
    )
