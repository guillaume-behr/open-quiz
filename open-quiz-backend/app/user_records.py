from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    AuthenticationChallenge,
    ClassTrainingQuestionBank,
    GradeLevel,
    MakeupSession,
    MakeupSessionQuiz,
    MakeupSessionSelection,
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    RefreshSession,
    RefreshSessionFamily,
    Student,
    StudentAccount,
    StudentClass,
    TrainingQuizProfile,
    TwoFactorCredential,
    User,
)
from app.quiz_session_records import delete_quiz_session_records


def delete_user_records(user_id: int, session: Session) -> None:
    """Erase a professor account and everything it owns.

    Every identifier is read before the first delete: once a parent row is
    gone, a subquery that derives its children from it returns nothing and the
    children outlive the account they belonged to.
    """
    quiz_ids = list(session.scalars(select(Quiz.id).where(Quiz.owner_id == user_id)))
    class_ids = list(
        session.scalars(select(StudentClass.id).where(StudentClass.owner_id == user_id))
    )
    bank_ids = list(
        session.scalars(select(QuestionBank.id).where(QuestionBank.owner_id == user_id))
    )
    makeup_ids = list(
        session.scalars(
            select(MakeupSession.id).where(MakeupSession.owner_id == user_id)
        )
    )
    account_ids = list(
        session.scalars(
            select(StudentAccount.id).where(StudentAccount.owner_id == user_id)
        )
    )
    student_ids = list(
        session.scalars(
            select(Student.id).where(
                or_(
                    Student.class_id.in_(class_ids),
                    Student.account_id.in_(account_ids),
                )
            )
        )
    )
    question_ids = list(
        session.scalars(
            select(Question.id).where(Question.question_bank_id.in_(bank_ids))
        )
    )
    refresh_ids = list(
        session.scalars(
            select(RefreshSession.id).where(RefreshSession.user_id == user_id)
        )
    )
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

    delete_quiz_session_records(session_ids, session)
    # A participant of someone else's session must never keep a foreign key to
    # a student who is about to disappear.
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id.in_(student_ids))
        .values(student_id=None)
    )
    session.execute(
        delete(MakeupSessionSelection).where(
            or_(
                MakeupSessionSelection.session_id.in_(makeup_ids),
                MakeupSessionSelection.student_id.in_(student_ids),
            )
        )
    )
    session.execute(
        delete(MakeupSessionQuiz).where(MakeupSessionQuiz.session_id.in_(makeup_ids))
    )
    session.execute(delete(MakeupSession).where(MakeupSession.id.in_(makeup_ids)))
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            or_(
                ClassTrainingQuestionBank.class_id.in_(class_ids),
                ClassTrainingQuestionBank.question_bank_id.in_(bank_ids),
            )
        )
    )
    session.execute(
        delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id.in_(quiz_ids))
    )
    session.execute(
        delete(TrainingQuizProfile).where(
            or_(
                TrainingQuizProfile.owner_id == user_id,
                TrainingQuizProfile.quiz_id.in_(quiz_ids),
            )
        )
    )
    session.execute(delete(Quiz).where(Quiz.id.in_(quiz_ids)))
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id.in_(question_ids))
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
    )
    session.execute(delete(Question).where(Question.id.in_(question_ids)))
    session.execute(delete(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
    session.execute(delete(Student).where(Student.id.in_(student_ids)))
    session.execute(delete(StudentAccount).where(StudentAccount.id.in_(account_ids)))
    session.execute(delete(StudentClass).where(StudentClass.id.in_(class_ids)))
    session.execute(delete(GradeLevel).where(GradeLevel.owner_id == user_id))
    session.execute(
        delete(RefreshSessionFamily).where(
            RefreshSessionFamily.session_id.in_(refresh_ids)
        )
    )
    session.execute(delete(RefreshSession).where(RefreshSession.id.in_(refresh_ids)))
    session.execute(
        delete(TwoFactorCredential).where(TwoFactorCredential.user_id == user_id)
    )
    session.execute(
        delete(AuthenticationChallenge).where(
            AuthenticationChallenge.user_id == user_id
        )
    )
    session.execute(delete(User).where(User.id == user_id))
