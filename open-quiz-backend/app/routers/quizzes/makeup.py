"""Makeup session routes: one join code for a class to retake finished quizzes.

The state machine and each student's choice live in
app/services/makeup_sessions.py.
"""

from secrets import token_urlsafe
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import DbSession, ProfessorUser, current_student
from app.core.errors import ApiError, ErrorCode
from app.core.pagination import Paging
from app.domain.class_names import format_class_name
from app.enums import QuizMode, SessionStatus
from app.live.updates import (
    publish_active_quiz_sessions_update,
    publish_makeup_update,
    publish_quiz_topics,
    publish_quiz_update,
)
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Quiz,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.records.quizzes import owned_makeup_session
from app.records.student_accounts import owned_class
from app.responses.quizzes import quiz_responses
from app.responses.student_sessions import student_state_response
from app.responses.teacher_sessions import makeup_responses, makeup_session_response
from app.schemas.quizzes import (
    MakeupQuizOption,
    MakeupQuizSelection,
    MakeupSessionCreate,
    MakeupSessionJoinResponse,
    MakeupSessionResponse,
    QuizResponse,
)
from app.schemas.student_quizzes import QuizJoin, StudentQuizJoinResponse
from app.services.makeup_sessions import (
    CANCELLABLE_STATUSES,
    MAKEUP_TRANSITIONS,
    MakeupAction,
    chosen_makeup_quiz,
    claim_makeup_selection,
    class_finished_quiz_ids,
    delete_unanswered_makeup_session,
    draw_makeup_questions,
    makeup_child_session,
    transition_makeup_session,
)
from app.services.participants import (
    enforce_public_rate_limit,
    generate_join_code,
    participant_token_hash,
)
from app.services.question_draws import quiz_bank_ids
from app.services.session_lifecycle import discard_active_training_sessions

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


# Kept on purpose: the interface follows make-up sessions on their WebSocket
# feed (live.py), and this read-only list stays as a polling fallback for API
# clients and the backend tests.
@router.get("/makeup/sessions", response_model=list[MakeupSessionResponse])
def list_makeup_sessions(
    professor: ProfessorUser, session: DbSession, paging: Paging
) -> list[MakeupSessionResponse]:
    """Every make-up of the teacher, finished ones included, newest first."""
    owned = MakeupSession.owner_id == professor.id
    paging.set_total(
        session.scalar(select(func.count()).select_from(MakeupSession).where(owned))
        or 0
    )
    makeups = session.scalars(
        select(MakeupSession)
        .where(owned)
        .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
        .offset(paging.offset)
        .limit(paging.page_size)
    )
    return makeup_responses(list(makeups), session)


@router.get("/makeup/quiz-options", response_model=list[QuizResponse])
def makeup_quiz_options(
    class_id: Annotated[int, Query(ge=1)],
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizResponse]:
    """Quizzes a class may make up: only those the class has already taken."""
    student_class = owned_class(class_id, professor.id, session)
    finished_ids = class_finished_quiz_ids(student_class.id, professor.id, session)
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(
                Quiz.owner_id == professor.id,
                Quiz.mode == QuizMode.EXAM,
                Quiz.id.in_(finished_ids),
            )
            .order_by(Quiz.title, Quiz.id)
        )
    )
    return quiz_responses(quizzes, session)


@router.post(
    "/makeup/sessions",
    response_model=MakeupSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_makeup_session(
    payload: MakeupSessionCreate,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == payload.class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    quiz_ids = set(payload.quiz_ids)
    quizzes = list(
        session.scalars(
            select(Quiz).where(
                Quiz.id.in_(quiz_ids),
                Quiz.owner_id == professor.id,
                Quiz.mode == QuizMode.EXAM,
            )
        )
    )
    if student_class is None or len(quizzes) != len(quiz_ids):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.MAKEUP_QUIZZES_INVALID,
            "Classe ou quiz invalide",
        )
    eligible = class_finished_quiz_ids(student_class.id, professor.id, session)
    if not quiz_ids.issubset(eligible):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.MAKEUP_QUIZ_NOT_TAKEN,
            "Seuls les quiz déjà passés par la classe peuvent être rattrapés",
        )
    makeup = MakeupSession(
        owner_id=professor.id,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status=SessionStatus.WAITING,
    )
    session.add(makeup)
    session.flush()
    session.add_all(
        MakeupSessionQuiz(session_id=makeup.id, quiz_id=quiz_id) for quiz_id in quiz_ids
    )
    session.commit()
    publish_makeup_update(request, professor.id)
    return makeup_session_response(makeup, session)


def cancel_makeup_session(
    makeup: MakeupSession,
    child_topics: list[tuple[int, str]],
    request: Request,
    professor_id: int,
    session: Session,
) -> Response:
    """Delete a makeup session nobody has answered in yet."""
    delete_unanswered_makeup_session(makeup, session)
    session.commit()
    for child_id, join_code in child_topics:
        publish_quiz_topics(request, child_id, join_code)
    publish_makeup_update(request, professor_id)
    publish_active_quiz_sessions_update(request, professor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/makeup/sessions/{session_id}/{action}",
    response_model=MakeupSessionResponse,
    # Cancelling deletes the make-up session: there is nothing left to return.
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Make-up session cancelled (action `cancel`)"
        }
    },
)
def control_makeup_session(
    session_id: int,
    action: MakeupAction,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse | Response:
    makeup = owned_makeup_session(session_id, professor.id, session)
    if action == MakeupAction.CANCEL:
        # Every other action changes this row, so its lock keeps the make-up
        # session waiting, and its children without answers, until the
        # delete commits: a concurrent start cannot slip in between.
        session.refresh(makeup, with_for_update=True)
    expected = (
        CANCELLABLE_STATUSES
        if action == MakeupAction.CANCEL
        else MAKEUP_TRANSITIONS[action][0]
    )
    if makeup.status not in expected:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_ACTION_NOT_ALLOWED,
            "Action impossible pour cette session",
        )
    child_topics: list[tuple[int, str]] = [
        (child_id, join_code)
        for child_id, join_code in session.execute(
            select(QuizSession.id, QuizSession.join_code).where(
                QuizSession.makeup_session_id == makeup.id
            )
        )
    ]
    if action == MakeupAction.CANCEL:
        return cancel_makeup_session(
            makeup, child_topics, request, professor.id, session
        )
    children = transition_makeup_session(makeup, action, session)
    session.commit()
    for child in children:
        publish_quiz_update(request, child, session)
    publish_makeup_update(request, professor.id)
    return makeup_session_response(makeup, session)


@router.post(
    "/makeup/join",
    response_model=MakeupSessionJoinResponse,
)
def join_makeup_session(
    payload: QuizJoin,
    request: Request,
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> MakeupSessionJoinResponse:
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == payload.join_code,
            MakeupSession.status == SessionStatus.WAITING,
        )
    )
    if makeup is None:
        # Bound join-code brute-force per student account, never per IP.
        enforce_public_rate_limit(
            request,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.MAKEUP_JOIN_REJECTED,
            "Impossible de rejoindre ce rattrapage",
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    if membership is None:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.MAKEUP_JOIN_REJECTED,
            "Impossible de rejoindre ce rattrapage",
        )
    eligible = list(
        session.scalars(
            select(Quiz)
            .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
            .where(
                MakeupSessionQuiz.session_id == makeup.id,
            )
            .order_by(Quiz.title, Quiz.id)
        )
    )
    return MakeupSessionJoinResponse(
        join_code=makeup.join_code,
        class_name=makeup.class_name,
        status=SessionStatus.WAITING,
        quizzes=[
            MakeupQuizOption(
                id=quiz.id,
                title=quiz.title,
                duration_seconds=quiz.duration_seconds,
            )
            for quiz in eligible
        ],
    )


@router.post(
    "/makeup/{join_code}/select",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def select_makeup_quiz(
    join_code: str,
    payload: MakeupQuizSelection,
    request: Request,
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> StudentQuizJoinResponse:
    makeup, membership, quiz = chosen_makeup_quiz(
        join_code, payload, account, request, session
    )
    claim_makeup_selection(makeup, membership, session)
    discard_active_training_sessions(
        [membership.id], quiz_bank_ids(quiz.id, session), session
    )
    child = makeup_child_session(makeup, quiz, session)
    draw_makeup_questions(child, makeup, quiz, membership, session)
    token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=child.id,
        student_id=membership.id,
        student_identifier=membership.identifier,
        student_display_name=membership.display_name,
        access_token_hash=participant_token_hash(token),
    )
    session.add(participant)
    session.commit()
    publish_quiz_update(request, child, session)
    publish_makeup_update(request, makeup.owner_id)
    state = student_state_response(child, quiz, participant, session)
    return StudentQuizJoinResponse(**state.model_dump(), participant_token=token)
