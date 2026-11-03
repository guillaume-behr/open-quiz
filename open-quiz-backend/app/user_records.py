from dataclasses import dataclass

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
from app.quiz_session_records import (
    delete_quiz_session_records,
    release_join_codes,
)

# Every table that depends on users, directly or through other tables, and
# that delete_user_records() therefore clears. A test walks the foreign keys
# and fails when a new dependent table is missing here, and so from the erasure.
ERASED_TABLES = frozenset(
    {
        "authentication_challenges",
        "class_training_question_banks",
        "grade_levels",
        "makeup_session_quizzes",
        "makeup_session_selections",
        "makeup_sessions",
        "question_banks",
        "question_choices",
        "question_codes",
        "questions",
        "quiz_answers",
        "quiz_participants",
        "quiz_question_banks",
        "quiz_session_questions",
        "quiz_session_student_questions",
        "quiz_sessions",
        "quizzes",
        "refresh_session_families",
        "refresh_sessions",
        "student_accounts",
        "student_classes",
        "students",
        "training_quiz_profiles",
        "two_factor_credentials",
        "users",
    }
)


@dataclass(frozen=True)
class OwnedRecords:
    """Identifiers of everything a professor account owns."""

    user_id: int
    quiz_ids: list[int]
    class_ids: list[int]
    bank_ids: list[int]
    makeup_ids: list[int]
    account_ids: list[int]
    student_ids: list[int]
    question_ids: list[int]
    refresh_ids: list[int]
    session_ids: list[int]


def owned_records(user_id: int, session: Session) -> OwnedRecords:
    """Read every identifier before the first delete.

    Once a parent row is gone, a subquery that derives its children from it
    returns nothing and the children outlive the account they belonged to.
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
    return OwnedRecords(
        user_id=user_id,
        quiz_ids=quiz_ids,
        class_ids=class_ids,
        bank_ids=bank_ids,
        makeup_ids=makeup_ids,
        account_ids=account_ids,
        student_ids=student_ids,
        question_ids=question_ids,
        refresh_ids=refresh_ids,
        session_ids=session_ids,
    )


def delete_user_records(user_id: int, session: Session) -> None:
    """Erase a professor account and everything it owns.

    Children go before their parents: quiz sessions, makeup sessions, quizzes
    and banks, then classes and students, and finally the account itself.
    """
    owned = owned_records(user_id, session)
    delete_quiz_session_records(owned.session_ids, session)
    _detach_foreign_participants(owned, session)
    _erase_makeup_sessions(owned, session)
    _erase_quizzes_and_banks(owned, session)
    _erase_classes_and_students(owned, session)
    _erase_account(owned, session)


def _detach_foreign_participants(owned: OwnedRecords, session: Session) -> None:
    # A participant of someone else's session must never keep a foreign key to
    # a student who is about to disappear.
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id.in_(owned.student_ids))
        .values(student_id=None)
    )


def _erase_makeup_sessions(owned: OwnedRecords, session: Session) -> None:
    session.execute(
        delete(MakeupSessionSelection).where(
            or_(
                MakeupSessionSelection.session_id.in_(owned.makeup_ids),
                MakeupSessionSelection.student_id.in_(owned.student_ids),
            )
        )
    )
    session.execute(
        delete(MakeupSessionQuiz).where(
            MakeupSessionQuiz.session_id.in_(owned.makeup_ids)
        )
    )
    makeup_join_codes = list(
        session.scalars(
            select(MakeupSession.join_code).where(
                MakeupSession.id.in_(owned.makeup_ids)
            )
        )
    )
    session.execute(delete(MakeupSession).where(MakeupSession.id.in_(owned.makeup_ids)))
    release_join_codes(makeup_join_codes, session)


def _erase_quizzes_and_banks(owned: OwnedRecords, session: Session) -> None:
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            or_(
                ClassTrainingQuestionBank.class_id.in_(owned.class_ids),
                ClassTrainingQuestionBank.question_bank_id.in_(owned.bank_ids),
            )
        )
    )
    session.execute(
        delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id.in_(owned.quiz_ids))
    )
    session.execute(
        delete(TrainingQuizProfile).where(
            or_(
                TrainingQuizProfile.owner_id == owned.user_id,
                TrainingQuizProfile.quiz_id.in_(owned.quiz_ids),
            )
        )
    )
    session.execute(delete(Quiz).where(Quiz.id.in_(owned.quiz_ids)))
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id.in_(owned.question_ids))
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id.in_(owned.question_ids))
    )
    session.execute(delete(Question).where(Question.id.in_(owned.question_ids)))
    session.execute(delete(QuestionBank).where(QuestionBank.id.in_(owned.bank_ids)))


def _erase_classes_and_students(owned: OwnedRecords, session: Session) -> None:
    session.execute(delete(Student).where(Student.id.in_(owned.student_ids)))
    session.execute(
        delete(StudentAccount).where(StudentAccount.id.in_(owned.account_ids))
    )
    session.execute(delete(StudentClass).where(StudentClass.id.in_(owned.class_ids)))
    session.execute(delete(GradeLevel).where(GradeLevel.owner_id == owned.user_id))


def _erase_account(owned: OwnedRecords, session: Session) -> None:
    session.execute(
        delete(RefreshSessionFamily).where(
            RefreshSessionFamily.session_id.in_(owned.refresh_ids)
        )
    )
    session.execute(
        delete(RefreshSession).where(RefreshSession.id.in_(owned.refresh_ids))
    )
    session.execute(
        delete(TwoFactorCredential).where(TwoFactorCredential.user_id == owned.user_id)
    )
    session.execute(
        delete(AuthenticationChallenge).where(
            AuthenticationChallenge.user_id == owned.user_id
        )
    )
    session.execute(delete(User).where(User.id == owned.user_id))
