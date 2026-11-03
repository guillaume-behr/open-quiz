"""Load a teacher's quizzes and sessions, refusing those of anyone else."""

from fastapi import (
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.enums import QuizMode
from app.errors import ApiError, ErrorCode
from app.models import (
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
        easy_points=0,
        medium_points=0,
        hard_points=0,
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
