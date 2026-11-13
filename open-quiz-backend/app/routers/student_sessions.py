"""Student participation media: anti-cheating reports and question images.

With their participant token a student reports anti-cheating events (focus
loss, copy attempts…) and loads the images of the current question and of
its choices. Joining and answering live in student_join and student_progress.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status
from sqlalchemy import select

from app.choice_tokens import ChoiceTokens
from app.dependencies import DbSession
from app.enums import AnswerMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.live_updates import publish_quiz_update
from app.models import Question, QuestionChoice, QuizParticipant, QuizSession
from app.participants import (
    VIOLATION_DEDUPLICATION_SECONDS,
    ReportingParticipant,
    rate_limited_participant,
)
from app.schemas import StudentQuizViolation
from app.services.question_assignments import current_question_id
from app.services.session_lifecycle import expire_quiz_session, quiz_session_is_due

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.post(
    "/student/sessions/{join_code}/violation",
    status_code=status.HTTP_204_NO_CONTENT,
)
def report_student_violation(
    payload: StudentQuizViolation,
    context: ReportingParticipant,
    request: Request,
    session: DbSession,
) -> Response:
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    expire_quiz_session(quiz_session, quiz, session)
    if (
        quiz_session.status != SessionStatus.IN_PROGRESS
        or participant.current_position is None
    ):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    now = datetime.now(UTC)
    last_violation_at = participant.last_violation_at
    if (
        participant.last_violation_type == payload.event_type
        and last_violation_at is not None
        and (now - last_violation_at).total_seconds() < VIOLATION_DEDUPLICATION_SECONDS
    ):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    participant.violation_count = (participant.violation_count or 0) + 1
    participant.last_violation_type = payload.event_type
    participant.last_violation_at = now
    session.commit()
    publish_quiz_update(
        request,
        quiz_session,
        session,
        active_sessions_changed=False,
        makeup_sessions_changed=False,
        participant=participant,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def active_participant_for_image(
    join_code: str,
    quiz_token: str | None,
    request: Request,
    session: DbSession,
    missing_detail: str,
) -> tuple[QuizSession, QuizParticipant]:
    context = rate_limited_participant(
        join_code, quiz_token, request, session, "quiz_participant_rate_limiter"
    )
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    # A read: a session past its deadline is refused like a finished one,
    # and left for the expiry loop to finish.
    if quiz_session.status != SessionStatus.IN_PROGRESS or quiz_session_is_due(
        quiz_session, quiz
    ):
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.IMAGE_NOT_FOUND, missing_detail
        )
    return quiz_session, participant


@router.get("/student/sessions/{join_code}/questions/{question_id}/image")
def get_student_question_image(
    join_code: str,
    question_id: int,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    missing_detail = "Image de la question introuvable"
    quiz_session, participant = active_participant_for_image(
        join_code,
        quiz_token,
        request,
        session,
        missing_detail,
    )
    if current_question_id(quiz_session, participant, session) != question_id:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.IMAGE_NOT_FOUND, missing_detail
        )
    question = session.get(Question, question_id)
    if question is None or question.image is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.IMAGE_NOT_FOUND, missing_detail
        )
    return Response(
        content=question.image.data,
        media_type=question.image.content_type,
    )


@router.get("/student/sessions/{join_code}/choices/{choice_token}/image")
def get_student_choice_image(
    join_code: str,
    choice_token: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    missing_detail = "Image de la réponse introuvable"
    quiz_session, participant = active_participant_for_image(
        join_code,
        quiz_token,
        request,
        session,
        missing_detail,
    )
    question_id = current_question_id(quiz_session, participant, session)
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .join(Question, Question.id == QuestionChoice.question_id)
            .where(
                QuestionChoice.question_id == question_id,
                Question.answer_mode != AnswerMode.WRITTEN,
            )
        )
    )
    tokens = ChoiceTokens(session, quiz_session, participant)
    choice = next(
        (choice for choice in choices if tokens.token(choice.id) == choice_token),
        None,
    )
    if choice is None or choice.image is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.IMAGE_NOT_FOUND, missing_detail
        )
    return Response(
        content=choice.image.data,
        media_type=choice.image.content_type,
    )
