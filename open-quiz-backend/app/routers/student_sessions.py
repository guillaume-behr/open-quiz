"""Student participation: joining a quiz session and taking it.

A student joins with a join code and receives a participant token; with it
they read the session state, answer, navigate, review and hand in their
answers, report anti-cheating events (focus loss, copy attempts…), and load
question and choice images.
"""

import json
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession
from app.errors import ErrorCode, api_error
from app.models import (
    Question,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
)
from app.question_responses import load_question_records
from app.routers.quizzes import (
    VIOLATION_DEDUPLICATION_SECONDS,
    accessible_question_positions,
    active_exam_bank_ids_for_class,
    answer_review_enabled,
    as_utc,
    authenticated_participant,
    current_question_id,
    enforce_public_rate_limit,
    expire_quiz_session,
    finish_when_nobody_can_answer,
    last_answered_question_id,
    participant_token_hash,
    publish_quiz_update,
    reject_quiz_join,
    session_question_ids,
    student_state_response,
)
from app.routers.student_auth import current_student
from app.schemas import (
    QuizJoin,
    StudentQuizAnswer,
    StudentQuizJoinResponse,
    StudentQuizNavigation,
    StudentQuizStateResponse,
    StudentQuizViolation,
    TrainingFeedback,
)
from app.services.grading import (
    decoded_answer_data,
)
from app.session_status import ACTIVE_SESSION_STATUSES

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.post(
    "/join",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_quiz(
    payload: QuizJoin,
    request: Request,
    session: DbSession,
    account: StudentAccount = Depends(current_student),
) -> StudentQuizJoinResponse:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == payload.join_code, Quiz.mode == "exam")
    ).first()
    if row is None:
        reject_quiz_join(request, session, f"join:unknown:{account.id}")
    quiz_session, quiz = row
    join_subject = f"join:session:{quiz_session.id}"
    if quiz_session.class_id is None:
        reject_quiz_join(request, session, join_subject)
    student = session.scalar(
        select(Student).where(
            Student.class_id == quiz_session.class_id,
            Student.account_id == account.id,
        )
    )
    if student is None:
        reject_quiz_join(request, session, join_subject)
    if quiz_session.same_questions_for_all is False:
        assigned_question_id = session.scalar(
            select(QuizSessionStudentQuestion.question_id)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .limit(1)
        )
        if assigned_question_id is None:
            reject_quiz_join(request, session, join_subject)
        session.execute(
            update(QuizSessionStudentQuestion)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .values(student_identifier=student.identifier)
        )
    existing = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.student_id == student.id,
        )
    )
    if existing is not None:
        if existing.left_at is None or quiz_session.status not in {
            "waiting",
            "in_progress",
            "paused",
        }:
            reject_quiz_join(request, session, join_subject)
        participant_token = token_urlsafe(32)
        active_session = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
            .values(status=QuizSession.status)
            .execution_options(synchronize_session=False)
        )
        if active_session.rowcount != 1:
            session.rollback()
            reject_quiz_join(request, session, join_subject)
        reconnected = session.execute(
            update(QuizParticipant)
            .where(
                QuizParticipant.id == existing.id,
                QuizParticipant.left_at.is_not(None),
            )
            .values(
                access_token_hash=participant_token_hash(participant_token),
                left_at=None,
                student_identifier=student.identifier,
                student_display_name=student.display_name,
            )
            .execution_options(synchronize_session=False)
        )
        if reconnected.rowcount != 1:
            session.rollback()
            reject_quiz_join(request, session, join_subject)
        session.commit()
        session.refresh(existing)
        publish_quiz_update(request, quiz_session, session)
        state = student_state_response(quiz_session, quiz, existing, session)
        return StudentQuizJoinResponse(
            **state.model_dump(), participant_token=participant_token
        )
    if quiz_session.status != "waiting":
        reject_quiz_join(request, session, join_subject)
    waiting = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == "waiting",
        )
        .values(status="waiting")
        .execution_options(synchronize_session=False)
    )
    if waiting.rowcount != 1:
        session.rollback()
        reject_quiz_join(request, session, join_subject)
    participant_token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_id=student.id,
        student_identifier=student.identifier,
        student_display_name=student.display_name,
        access_token_hash=participant_token_hash(participant_token),
    )
    session.add(participant)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        reject_quiz_join(request, session, join_subject)
    publish_quiz_update(request, quiz_session, session)
    state = student_state_response(quiz_session, quiz, participant, session)
    return StudentQuizJoinResponse(
        **state.model_dump(),
        participant_token=participant_token,
    )


@router.post(
    "/student/sessions/{join_code}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_student_quiz(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    participant.left_at = datetime.now(UTC)
    participant.access_token_hash = None
    session.flush()
    finish_when_nobody_can_answer(quiz_session, quiz, session)
    session.commit()
    publish_quiz_update(request, quiz_session, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/student/sessions/{join_code}",
    response_model=StudentQuizStateResponse,
)
def get_student_quiz_state(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    state = student_state_response(quiz_session, quiz, participant, session)
    return state


@router.post(
    "/student/sessions/{join_code}/answer",
    response_model=StudentQuizStateResponse,
)
def submit_student_answer(
    join_code: str,
    payload: StudentQuizAnswer,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    # "finished" is allowed past this gate only so a concurrent duplicate of
    # the last answer can still be recognised below: finish_when_nobody_can_answer
    # runs in the same transaction as the winning submission, so a losing
    # duplicate can reach here after that transition already committed. Any
    # other non-"in_progress" status (paused included) still rejects outright.
    if quiz_session.status not in ("in_progress", "finished"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_NOT_ACCEPTING_ANSWERS,
                "Le quiz n’accepte pas de réponses actuellement",
            ),
        )
    if participant.student_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(ErrorCode.QUIZ_STUDENT_REMOVED, "L’élève n’existe plus"),
        )
    if (
        quiz_session.training_question_bank_id is not None
        and quiz_session.class_id is not None
        and quiz_session.training_question_bank_id
        in active_exam_bank_ids_for_class(quiz_session.class_id, session)
    ):
        # Opening an exam discards these trainings; this also covers one
        # started concurrently, which must not give feedback during the exam.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.TRAINING_BLOCKED_BY_EXAM,
                "Cet entraînement est indisponible pendant un examen",
            ),
        )
    question_id = current_question_id(quiz_session, participant, session)
    retargeting_finished_answer = question_id is None
    if retargeting_finished_answer:
        question_id = last_answered_question_id(quiz_session, participant, session)
    if question_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_NO_CURRENT_QUESTION, "Aucune question en cours"
            ),
        )
    questions_by_id, choices_by_question = load_question_records([question_id], session)
    question = questions_by_id.get(question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_QUESTION_UNAVAILABLE,
                "La question actuelle n’est pas disponible",
            ),
        )
    choices = choices_by_question.get(question_id, [])
    choices_by_id = {choice.id: choice for choice in choices}

    feedback: TrainingFeedback | None = None
    if question.answer_mode == "written":
        written_answer = (payload.written_answer or "").strip()
        if not written_answer or payload.selected_choice_ids is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=api_error(
                    ErrorCode.ANSWER_WRITTEN_REQUIRED,
                    "Une réponse rédactionnelle est requise",
                ),
            )
        answer_data = {"written_answer": written_answer}
        expected_answer = next(
            (choice.label for choice in choices if choice.is_correct),
            "",
        )
        if quiz.mode == "training":
            feedback = TrainingFeedback(
                question_id=question.id,
                is_correct=None,
                correct_choice_ids=[],
                expected_answer=expected_answer,
                submitted_answer=written_answer,
                requires_manual_review=True,
            )
    else:
        if payload.selected_choice_ids is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=api_error(
                    ErrorCode.ANSWER_CHOICE_REQUIRED,
                    "Au moins une proposition doit être sélectionnée",
                ),
            )
        selected_ids = list(dict.fromkeys(payload.selected_choice_ids or []))
        if payload.written_answer is not None or (
            question.answer_mode == "single"
            and question.answer_mode_disclosed
            and len(selected_ids) != 1
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=api_error(
                    ErrorCode.ANSWER_MODE_MISMATCH,
                    "La réponse envoyée ne correspond pas au type de la question",
                ),
            )
        if any(choice_id not in choices_by_id for choice_id in selected_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=api_error(
                    ErrorCode.ANSWER_CHOICE_INVALID,
                    "Une proposition sélectionnée est invalide",
                ),
            )
        answer_data = {"selected_choice_ids": selected_ids}
        if quiz.mode == "training":
            correct_ids = [choice.id for choice in choices if choice.is_correct]
            feedback = TrainingFeedback(
                question_id=question.id,
                is_correct=set(selected_ids) == set(correct_ids),
                correct_choice_ids=correct_ids,
            )

    if retargeting_finished_answer:
        # The participant already moved past this question: only accept the
        # submission if it matches what a concurrent duplicate already
        # recorded for it, rather than silently rewriting a finished answer.
        existing_answer = session.scalar(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
                QuizAnswer.question_id == question_id,
            )
        )
        if (
            existing_answer is None
            or decoded_answer_data(existing_answer) != answer_data
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=api_error(
                    ErrorCode.QUIZ_NO_CURRENT_QUESTION, "Aucune question en cours"
                ),
            )

    # Atomic upsert: concurrent submissions for the same question can never
    # create duplicate answers nor crash on the uniqueness constraint.
    answer_statement = insert(QuizAnswer).values(
        session_id=quiz_session.id,
        participant_id=participant.id,
        question_id=question_id,
        answer_data=json.dumps(answer_data, ensure_ascii=False),
        score=0,
        is_graded=False,
    )
    session.execute(
        answer_statement.on_conflict_do_update(
            index_elements=[
                QuizAnswer.session_id,
                QuizAnswer.participant_id,
                QuizAnswer.question_id,
            ],
            set_={
                "answer_data": answer_statement.excluded.answer_data,
                "score": 0,
                "is_graded": False,
            },
        )
    )
    total_questions = len(session_question_ids(quiz_session, session, participant))
    if (
        participant.current_position is not None
        and participant.current_position + 1 < total_questions
    ):
        participant.current_position += 1
    else:
        participant.current_position = None
    if (
        participant.current_position is None
        and participant.submitted_at is None
        and not answer_review_enabled(quiz_session, quiz)
    ):
        # Without the review step the last answer is the final submission.
        participant.submitted_at = datetime.now(UTC)
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
    )
    state = student_state_response(quiz_session, quiz, participant, session)
    if feedback is not None:
        state.training_feedback = feedback
    return state


def require_answer_review_offered(quiz_session: QuizSession, quiz: Quiz) -> None:
    """Reject a review request on a quiz that has no final submission step."""
    if not answer_review_enabled(quiz_session, quiz):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_REVIEW_UNAVAILABLE,
                "La relecture des réponses n’est pas disponible",
            ),
        )


def require_reviewable_participant(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
) -> None:
    """Reject a participant who may not reach the answer review step.

    The session must still be running and every assigned question must already
    have an answer.
    """
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_REVIEW_UNAVAILABLE,
                "La relecture des réponses n’est pas disponible",
            ),
        )
    question_ids = session_question_ids(quiz_session, session, participant)
    answered_question_ids = set(
        session.scalars(
            select(QuizAnswer.question_id).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    if not question_ids or not set(question_ids).issubset(answered_question_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_ANSWERS_INCOMPLETE,
                "Toutes les questions doivent être répondues",
            ),
        )


@router.post(
    "/student/sessions/{join_code}/review",
    response_model=StudentQuizStateResponse,
)
def review_student_answers(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    """Leave the questions and go back to the summary of the given answers."""
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
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
        )
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/submit",
    response_model=StudentQuizStateResponse,
)
def submit_student_quiz(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    """Hand in a reviewed paper, which ends the quiz for this participant."""
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
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
    publish_quiz_update(request, quiz_session, session)
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/navigate",
    response_model=StudentQuizStateResponse,
)
def navigate_student_quiz(
    join_code: str,
    payload: StudentQuizNavigation,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    target_position = payload.question_number - 1
    allow_previous_questions = quiz_session.allow_previous_questions
    if allow_previous_questions is None:
        allow_previous_questions = quiz.allow_previous_questions
    question_ids = session_question_ids(quiz_session, session, participant)
    answered_question_ids = set(
        session.scalars(
            select(QuizAnswer.question_id).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    accessible_positions = accessible_question_positions(
        question_ids,
        answered_question_ids,
        participant.current_position,
    )
    reviewing = (
        participant.current_position is None
        and participant.submitted_at is None
        and answer_review_enabled(quiz_session, quiz)
        and bool(question_ids)
        and set(question_ids).issubset(answered_question_ids)
    )
    if (
        quiz_session.status != "in_progress"
        or not allow_previous_questions
        or (participant.current_position is None and not reviewing)
        or target_position not in accessible_positions
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_PREVIOUS_QUESTION_LOCKED,
                "Le retour à cette question n’est pas autorisé",
            ),
        )
    participant.current_position = target_position
    session.commit()
    publish_quiz_update(
        request,
        quiz_session,
        session,
        active_sessions_changed=False,
        makeup_sessions_changed=False,
    )
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/violation",
    status_code=status.HTTP_204_NO_CONTENT,
)
def report_student_violation(
    join_code: str,
    payload: StudentQuizViolation,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_violation_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress" or participant.current_position is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    now = datetime.now(UTC)
    last_violation_at = participant.last_violation_at
    if last_violation_at is not None:
        last_violation_at = as_utc(last_violation_at)
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
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def active_participant_for_image(
    join_code: str,
    quiz_token: str | None,
    request: Request,
    session: DbSession,
    missing_detail: str,
) -> tuple[QuizSession, QuizParticipant]:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=missing_detail,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=missing_detail,
        )
    question = session.get(Question, question_id)
    if (
        question is None
        or question.image_data is None
        or question.image_content_type is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=missing_detail,
        )
    return Response(
        content=question.image_data,
        media_type=question.image_content_type,
    )


@router.get("/student/sessions/{join_code}/choices/{choice_id}/image")
def get_student_choice_image(
    join_code: str,
    choice_id: int,
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
    choice = session.scalar(
        select(QuestionChoice)
        .join(Question, Question.id == QuestionChoice.question_id)
        .where(
            QuestionChoice.id == choice_id,
            QuestionChoice.question_id == question_id,
            Question.answer_mode != "written",
        )
    )
    if choice is None or choice.image_data is None or choice.image_content_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=missing_detail,
        )
    return Response(
        content=choice.image_data,
        media_type=choice.image_content_type,
    )
