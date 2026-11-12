from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    MakeupSession,
    QuestionBank,
    Quiz,
    QuizSession,
    StudentClass,
    User,
)
from app.quiz_session_records import (
    delete_quiz_session_records,
    release_join_codes,
)


def delete_user_records(user_id: int, session: Session) -> None:
    """Erase a professor account and everything it owns.

    Every table that depends on users cascades from the account row
    (tests/test_admin.py checks each new one does). Join codes have no foreign
    key, so the sessions and make-up sessions release theirs by hand first.
    """
    quiz_ids = select(Quiz.id).where(Quiz.owner_id == user_id)
    class_ids = select(StudentClass.id).where(StudentClass.owner_id == user_id)
    bank_ids = select(QuestionBank.id).where(QuestionBank.owner_id == user_id)
    makeup_ids = select(MakeupSession.id).where(MakeupSession.owner_id == user_id)
    session_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                or_(
                    QuizSession.quiz_id.in_(quiz_ids),
                    QuizSession.class_id.in_(class_ids),
                    QuizSession.makeup_session_id.in_(makeup_ids),
                    QuizSession.training_question_bank_id.in_(bank_ids),
                )
            )
        )
    )
    makeup_join_codes = list(
        session.scalars(
            select(MakeupSession.join_code).where(MakeupSession.owner_id == user_id)
        )
    )
    delete_quiz_session_records(session_ids, session)
    session.execute(delete(User).where(User.id == user_id))
    release_join_codes(makeup_join_codes, session)
