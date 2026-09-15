from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    QuizAnswer,
    QuizJoinCode,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)


def release_join_codes(codes: list[str], session: Session) -> None:
    """Return join codes to the pool once nothing refers to them any more.

    A code is reserved in its own table so two live sessions can never share
    one. Deleting the session without releasing its reservation leaks a row
    per session forever: restarting training discards the previous attempt,
    so a student alone can burn one code per attempt with nothing to reclaim
    it.
    """
    if not codes:
        return
    session.execute(delete(QuizJoinCode).where(QuizJoinCode.code.in_(codes)))


def delete_quiz_session_records(session_ids: list[int], session: Session) -> None:
    if not session_ids:
        return
    join_codes = list(
        session.scalars(
            select(QuizSession.join_code).where(QuizSession.id.in_(session_ids))
        )
    )
    session.execute(delete(QuizAnswer).where(QuizAnswer.session_id.in_(session_ids)))
    session.execute(
        delete(QuizParticipant).where(QuizParticipant.session_id.in_(session_ids))
    )
    session.execute(
        delete(QuizSessionQuestion).where(
            QuizSessionQuestion.session_id.in_(session_ids)
        )
    )
    session.execute(
        delete(QuizSessionStudentQuestion).where(
            QuizSessionStudentQuestion.session_id.in_(session_ids)
        )
    )
    session.execute(delete(QuizSession).where(QuizSession.id.in_(session_ids)))
    release_join_codes(join_codes, session)
