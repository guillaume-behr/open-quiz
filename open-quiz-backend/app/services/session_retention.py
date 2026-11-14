from datetime import datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.domain.session_status import ACTIVE_SESSION_STATUSES
from app.enums import QuizMode, SessionStatus
from app.models import MakeupSession, Quiz, QuizSession
from app.records.quiz_sessions import delete_quiz_session_records
from app.services.session_lifecycle import (
    anyone_took_a_question,
    delete_makeup_session_records,
    finish_session,
)


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
                # Settled with their make-up (close_abandoned_makeups).
                QuizSession.makeup_session_id.is_(None),
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


def close_abandoned_makeups(cutoff: datetime, session: Session) -> tuple[int, int]:
    """Settle make-up sessions their teacher never finished.

    A make-up stays open until its teacher finishes it, holding its students'
    names, blocking the deletion of its class and banks, and keeping its
    children out of the session sweep's reach as a whole. Past the cutoff it
    is settled with them: each open child that collected answers or skips is
    graded, the others are discarded, as close_abandoned_sessions does. The
    make-up is kept, finished, while a child remains, and deleted otherwise.
    One whose student is still mid-exam waits for that exam's timer.

    Rows a teacher is changing are skipped: the next run settles them.
    Returns the number of make-ups finished and the number deleted.
    """
    finished = deleted = 0
    makeups = list(
        session.scalars(
            select(MakeupSession)
            .where(
                MakeupSession.status.in_(ACTIVE_SESSION_STATUSES),
                MakeupSession.created_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for makeup in makeups:
        children = session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.makeup_session_id == makeup.id,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        ).all()
        # A make-up may have waited long before it started: a child still
        # running ends with its timer, and the make-up at a later run.
        if any(child.status == SessionStatus.IN_PROGRESS for child, _ in children):
            continue
        discarded: list[int] = []
        for child, quiz in children:
            if anyone_took_a_question(child, session):
                finish_session(
                    child, quiz, session, from_statuses=ACTIVE_SESSION_STATUSES
                )
            else:
                discarded.append(child.id)
        delete_quiz_session_records(discarded, session)
        if (
            session.scalar(
                select(QuizSession.id)
                .where(QuizSession.makeup_session_id == makeup.id)
                .limit(1)
            )
            is None
        ):
            delete_makeup_session_records(makeup.id, session)
            deleted += 1
        else:
            makeup.status = SessionStatus.FINISHED
            finished += 1
    session.flush()
    return finished, deleted


def delete_emptied_makeups(session: Session) -> int:
    """Delete the finished make-ups none of whose sessions remain.

    Their children go with the result retention, or when a teacher deletes
    them; the make-up itself then only holds a class name and selections.
    """
    emptied = list(
        session.scalars(
            select(MakeupSession.id).where(
                MakeupSession.status == SessionStatus.FINISHED,
                ~select(QuizSession.id)
                .where(QuizSession.makeup_session_id == MakeupSession.id)
                .exists(),
            )
        )
    )
    for makeup_id in emptied:
        delete_makeup_session_records(makeup_id, session)
    return len(emptied)


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
