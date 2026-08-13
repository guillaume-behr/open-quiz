from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)


def delete_quiz_session_records(session_ids: list[int], session: Session) -> None:
    if not session_ids:
        return
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
