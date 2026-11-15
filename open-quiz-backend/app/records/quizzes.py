"""Load a teacher's quizzes, sessions and make-ups, refusing anyone else's."""

from fastapi import (
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import DbSession, ProfessorUser
from app.core.errors import ApiError, ErrorCode
from app.enums import QuizMode
from app.models import (
    MakeupSession,
    Quiz,
    QuizSession,
    TrainingQuizProfile,
)


def owned_quiz(quiz_id: int, professor: ProfessorUser, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
    )
    if quiz is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"
        )
    return quiz


def training_profile_quiz(owner_id: int, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz)
        .join(TrainingQuizProfile, TrainingQuizProfile.quiz_id == Quiz.id)
        .where(TrainingQuizProfile.owner_id == owner_id)
    )
    if quiz is not None:
        return quiz
    quiz = Quiz(
        owner_id=owner_id,
        mode=QuizMode.TRAINING,
        title="Entraînement",
        source_language="fr",
        question_count=0,
        duration_seconds=28800,
        allow_previous_questions=False,
        allow_answer_review=False,
        allow_negative_points=False,
        same_questions_for_all=False,
        easy_question_count=0,
        medium_question_count=0,
        hard_question_count=0,
    )
    session.add(quiz)
    try:
        session.flush()
        session.add(TrainingQuizProfile(owner_id=owner_id, quiz_id=quiz.id))
        session.flush()
    except IntegrityError:
        # A concurrent request created the training profile first; callers
        # have only performed reads so far, so rolling back is safe.
        session.rollback()
        quiz = session.scalar(
            select(Quiz)
            .join(TrainingQuizProfile, TrainingQuizProfile.quiz_id == Quiz.id)
            .where(TrainingQuizProfile.owner_id == owner_id)
        )
        if quiz is None:
            raise
    return quiz


def owned_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> tuple[QuizSession, Quiz]:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.id == session_id,
            Quiz.owner_id == professor.id,
        )
    ).first()
    if row is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.QUIZ_SESSION_NOT_FOUND,
            "Session de quiz introuvable",
        )
    return row


def owned_class_session(
    session_id: int, professor: ProfessorUser, session: DbSession
) -> tuple[QuizSession, Quiz]:
    """A session the class session routes may control: not one student's make-up quiz.

    A make-up's children follow the make-up session's own state machine;
    changing one directly would desynchronise it, and cancelling one would
    strand its student's selection.
    """
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.makeup_session_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_IS_MAKEUP,
            "Cette session se pilote depuis sa session de rattrapage",
        )
    return quiz_session, quiz


def owned_makeup_session(
    session_id: int, professor: ProfessorUser, session: DbSession
) -> MakeupSession:
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.id == session_id,
            MakeupSession.owner_id == professor.id,
        )
    )
    if makeup is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.MAKEUP_NOT_FOUND,
            "Session de rattrapage introuvable",
        )
    return makeup
