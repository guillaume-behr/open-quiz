"""Student progress through a running quiz: answering, reviewing, navigating.

The participant answers the current question, goes back to an earlier one
when the quiz allows it, reviews the given answers and hands in the paper.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status

from app.core.dependencies import DbSession
from app.core.errors import ApiError, ErrorCode
from app.domain.choice_tokens import ChoiceTokens
from app.enums import SessionStatus
from app.live.updates import publish_quiz_update
from app.responses.student_sessions import student_state_response
from app.schemas.student_quizzes import (
    StudentQuizAnswer,
    StudentQuizNavigation,
    StudentQuizStateResponse,
)
from app.services.answers import (
    advance_participant,
    answered_question,
    require_answer_accepted,
    require_answer_review_offered,
    require_reviewable_participant,
    require_same_finished_answer,
    store_answer,
    validated_answer,
)
from app.services.participants import CurrentParticipant
from app.services.question_assignments import (
    accessible_question_positions,
    session_question_ids,
)
from app.services.session_lifecycle import (
    answer_review_enabled,
    answered_question_ids,
    expire_quiz_session,
    finish_when_nobody_can_answer,
    lock_for_participant_write,
    previous_questions_allowed,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.post(
    "/student/sessions/{join_code}/answer",
    response_model=StudentQuizStateResponse,
)
def submit_student_answer(
    payload: StudentQuizAnswer,
    context: CurrentParticipant,
    request: Request,
    session: DbSession,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    expire_quiz_session(quiz_session, quiz, session)
    lock_for_participant_write(quiz_session, participant, session)
    require_answer_accepted(quiz_session, participant, session)
    question, choices, retargeting = answered_question(
        quiz_session, participant, session
    )
    if payload.question_id != question.id:
        # The page shows another question than the one the server is on: a
        # stale view must not record its answer against this question.
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.ANSWER_QUESTION_MISMATCH,
            "La réponse concerne une autre question que la question en cours",
        )
    answer_data, feedback = validated_answer(
        payload,
        question,
        choices,
        quiz,
        ChoiceTokens(session, quiz_session, participant),
    )
    if retargeting:
        require_same_finished_answer(
            quiz_session, participant, question.id, answer_data, session
        )
        # A repeat of an answer already recorded changes nothing; writing it
        # again would also reset a grade the finished session already gave.
        state = student_state_response(quiz_session, quiz, participant, session)
        if feedback is not None:
            state.training_feedback = feedback
        return state
    store_answer(quiz_session, participant, question.id, answer_data, session)
    advance_participant(quiz_session, quiz, participant, session)
    session.flush()
    finish_when_nobody_can_answer(quiz_session, quiz, session)
    session.commit()
    publish_quiz_update(
        request,
        quiz_session,
        session,
        # Rebuilding a whole makeup session for every answer is wasteful, but
        # its supervision view must see a participant reaching the end.
        makeup_sessions_changed=participant.current_position is None,
        participant=participant,
    )
    state = student_state_response(quiz_session, quiz, participant, session)
    if feedback is not None:
        state.training_feedback = feedback
    return state


@router.post(
    "/student/sessions/{join_code}/review",
    response_model=StudentQuizStateResponse,
)
def review_student_answers(
    context: CurrentParticipant,
    request: Request,
    session: DbSession,
) -> StudentQuizStateResponse:
    """Leave the questions and go back to the summary of the given answers."""
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    expire_quiz_session(quiz_session, quiz, session)
    lock_for_participant_write(quiz_session, participant, session)
    require_answer_review_offered(quiz_session, quiz)
    if participant.submitted_at is not None:
        return student_state_response(quiz_session, quiz, participant, session)
    require_reviewable_participant(quiz_session, participant, session)
    if participant.current_position is not None:
        participant.current_position = None
        session.commit()
        publish_quiz_update(
            request,
            quiz_session,
            session,
            active_sessions_changed=False,
            makeup_sessions_changed=False,
            participant=participant,
        )
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/submit",
    response_model=StudentQuizStateResponse,
)
def submit_student_quiz(
    context: CurrentParticipant,
    request: Request,
    session: DbSession,
) -> StudentQuizStateResponse:
    """Hand in a reviewed paper, which ends the quiz for this participant."""
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    expire_quiz_session(quiz_session, quiz, session)
    lock_for_participant_write(quiz_session, participant, session)
    require_answer_review_offered(quiz_session, quiz)
    if participant.submitted_at is not None:
        # A duplicate confirmation must not fail the student whose paper is
        # already handed in.
        return student_state_response(quiz_session, quiz, participant, session)
    require_reviewable_participant(quiz_session, participant, session)
    participant.current_position = None
    participant.submitted_at = datetime.now(UTC)
    session.flush()
    finish_when_nobody_can_answer(quiz_session, quiz, session)
    session.commit()
    publish_quiz_update(request, quiz_session, session, participant=participant)
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/navigate",
    response_model=StudentQuizStateResponse,
)
def navigate_student_quiz(
    payload: StudentQuizNavigation,
    context: CurrentParticipant,
    request: Request,
    session: DbSession,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    expire_quiz_session(quiz_session, quiz, session)
    lock_for_participant_write(quiz_session, participant, session)
    target_position = payload.question_number - 1
    question_ids = session_question_ids(quiz_session, session, participant)
    answered_ids = answered_question_ids(quiz_session, participant, session)
    accessible_positions = accessible_question_positions(
        question_ids,
        answered_ids,
        participant.current_position,
    )
    reviewing = (
        participant.current_position is None
        and participant.submitted_at is None
        and answer_review_enabled(quiz_session, quiz)
        and bool(question_ids)
        and set(question_ids).issubset(answered_ids)
    )
    if (
        quiz_session.status != SessionStatus.IN_PROGRESS
        or not previous_questions_allowed(quiz_session, quiz)
        or (participant.current_position is None and not reviewing)
        or target_position not in accessible_positions
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_PREVIOUS_QUESTION_LOCKED,
            "Le retour à cette question n’est pas autorisé",
        )
    participant.current_position = target_position
    session.commit()
    publish_quiz_update(
        request,
        quiz_session,
        session,
        active_sessions_changed=False,
        makeup_sessions_changed=False,
        participant=participant,
    )
    return student_state_response(quiz_session, quiz, participant, session)
