"""Makeup sessions: one join code for a class to retake finished quizzes.

The teacher offers some of the quizzes the class has finished; each student
joins with the code, picks one of them and answers it in a child QuizSession
of their own.
"""

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil
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
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.class_names import format_class_name
from app.database import affected_rows
from app.dependencies import DbSession, ProfessorUser, current_student
from app.enums import QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.live_updates import (
    publish_active_quiz_sessions_update,
    publish_makeup_update,
    publish_quiz_topics,
    publish_quiz_update,
)
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    MakeupSessionSelection,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import Paging
from app.participants import (
    enforce_public_rate_limit,
    generate_join_code,
    participant_token_hash,
)
from app.schemas import (
    MakeupQuizOption,
    MakeupQuizSelection,
    MakeupSessionCreate,
    MakeupSessionJoinResponse,
    MakeupSessionResponse,
    QuizJoin,
    QuizResponse,
    StudentQuizJoinResponse,
)
from app.services.question_draws import (
    draw_unique_question_ids,
    question_draw_pool,
    quiz_bank_ids,
)
from app.services.session_lifecycle import (
    delete_makeup_session_records,
    discard_active_training_sessions,
    finish_session,
)
from app.session_responses import (
    makeup_responses,
    makeup_session_response,
    quiz_responses,
    student_state_response,
)
from app.student_accounts import owned_class

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


class MakeupAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    FINISH = "finish"
    CANCEL = "cancel"


# The statuses each action accepts, and the one it leads to. A paused make-up
# can be finished directly: resuming it first would restart every clock.
MAKEUP_TRANSITIONS: dict[
    MakeupAction, tuple[tuple[SessionStatus, ...], SessionStatus]
] = {
    MakeupAction.START: ((SessionStatus.WAITING,), SessionStatus.IN_PROGRESS),
    MakeupAction.PAUSE: ((SessionStatus.IN_PROGRESS,), SessionStatus.PAUSED),
    MakeupAction.RESUME: ((SessionStatus.PAUSED,), SessionStatus.IN_PROGRESS),
    MakeupAction.FINISH: (
        (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED),
        SessionStatus.FINISHED,
    ),
}
# Cancelling deletes the make-up session instead of changing its status.
CANCELLABLE_STATUSES = (SessionStatus.WAITING,)


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
            404, ErrorCode.MAKEUP_NOT_FOUND, "Session de rattrapage introuvable"
        )
    return makeup


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


def class_finished_quiz_ids(
    student_class_id: int, professor: ProfessorUser, session: DbSession
) -> set[int]:
    """Quizzes for which the class already completed an exam session."""
    return set(
        session.scalars(
            select(QuizSession.quiz_id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.class_id == student_class_id,
                QuizSession.status == SessionStatus.FINISHED,
            )
        )
    )


@router.get("/makeup/quiz-options", response_model=list[QuizResponse])
def makeup_quiz_options(
    class_id: Annotated[int, Query(ge=1)],
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizResponse]:
    """Quizzes a class may make up: only those the class has already taken."""
    student_class = owned_class(class_id, professor, session)
    finished_ids = class_finished_quiz_ids(student_class.id, professor, session)
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
        raise ApiError(422, ErrorCode.MAKEUP_QUIZZES_INVALID, "Classe ou quiz invalide")
    eligible = class_finished_quiz_ids(student_class.id, professor, session)
    if not quiz_ids.issubset(eligible):
        raise ApiError(
            422,
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
    has_answers = (
        session.scalar(
            select(QuizAnswer.id)
            .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
            .where(QuizSession.makeup_session_id == makeup.id)
            .limit(1)
        )
        is not None
    )
    if has_answers:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_HAS_ANSWERS,
            "Impossible d’annuler ce rattrapage car des réponses ont déjà "
            "été enregistrées",
        )
    delete_makeup_session_records(makeup.id, session)
    session.commit()
    for child_id, join_code in child_topics:
        publish_quiz_topics(request, child_id, join_code)
    publish_makeup_update(request, professor_id)
    publish_active_quiz_sessions_update(request, professor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def apply_makeup_action(
    child: QuizSession,
    quiz: Quiz,
    action: MakeupAction,
    now: datetime,
    session: Session,
) -> None:
    """Carry a makeup action over to one student's quiz session.

    Pausing and resuming only apply if the child is still in the status they
    were checked against, so a child that finished meanwhile stays finished.
    """
    if action == MakeupAction.START:
        if child.status != SessionStatus.WAITING:
            return
        child.status = SessionStatus.IN_PROGRESS
        child.started_at = now
        for participant in session.scalars(
            select(QuizParticipant).where(QuizParticipant.session_id == child.id)
        ):
            participant.current_position = 0
    elif action == MakeupAction.PAUSE:
        if child.status != SessionStatus.IN_PROGRESS:
            return
        session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == child.id,
                QuizSession.status == SessionStatus.IN_PROGRESS,
            )
            .values(status=SessionStatus.PAUSED, paused_at=now)
            .execution_options(synchronize_session=False)
        )
        session.refresh(child)
    elif action == MakeupAction.RESUME:
        if child.status != SessionStatus.PAUSED or child.paused_at is None:
            return
        session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == child.id,
                QuizSession.status == SessionStatus.PAUSED,
                QuizSession.paused_at == child.paused_at,
            )
            .values(
                status=SessionStatus.IN_PROGRESS,
                paused_at=None,
                paused_duration_seconds=(child.paused_duration_seconds or 0)
                + ceil(max(0, (now - child.paused_at).total_seconds())),
            )
            .execution_options(synchronize_session=False)
        )
        session.refresh(child)
    else:  # finish
        finish_session(
            child,
            quiz,
            session,
            from_statuses=(SessionStatus.IN_PROGRESS, SessionStatus.PAUSED),
        )


@router.post(
    "/makeup/sessions/{session_id}/{action}",
    response_model=MakeupSessionResponse,
)
def control_makeup_session(
    session_id: int,
    action: MakeupAction,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse | Response:
    makeup = owned_makeup_session(session_id, professor, session)
    expected = (
        CANCELLABLE_STATUSES
        if action == MakeupAction.CANCEL
        else MAKEUP_TRANSITIONS[action][0]
    )
    if makeup.status not in expected:
        raise ApiError(
            409,
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
    target = MAKEUP_TRANSITIONS[action][1]
    transition = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status.in_(expected),
        )
        .values(status=target)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(transition) != 1:
        session.rollback()
        raise ApiError(
            409,
            ErrorCode.MAKEUP_ACTION_NOT_ALLOWED,
            "Action impossible pour cette session",
        )
    makeup.status = target
    children = [
        (child, quiz)
        for child, quiz in session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(QuizSession.makeup_session_id == makeup.id)
        )
    ]
    if action == MakeupAction.START and not children:
        session.rollback()
        raise ApiError(
            409,
            ErrorCode.MAKEUP_NO_SELECTION,
            "Au moins un élève doit choisir un quiz avant le démarrage",
        )
    now = datetime.now(UTC)
    for child, quiz in children:
        apply_makeup_action(child, quiz, action, now, session)
    session.commit()
    for child, _ in children:
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
            403, ErrorCode.MAKEUP_JOIN_REJECTED, "Impossible de rejoindre ce rattrapage"
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    if membership is None:
        raise ApiError(
            403, ErrorCode.MAKEUP_JOIN_REJECTED, "Impossible de rejoindre ce rattrapage"
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


def chosen_makeup_quiz(
    join_code: str,
    payload: MakeupQuizSelection,
    account: StudentAccount,
    request: Request,
    session: Session,
) -> tuple[MakeupSession, Student, Quiz]:
    """The open makeup session, the student's place in it and the quiz chosen."""
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == join_code.strip().upper(),
            MakeupSession.status == SessionStatus.WAITING,
        )
    )
    if makeup is None:
        enforce_public_rate_limit(
            request,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
        raise ApiError(
            409,
            ErrorCode.MAKEUP_SELECTION_CLOSED,
            "Ce rattrapage n’accepte plus de choix",
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    quiz = session.scalar(
        select(Quiz)
        .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
        .where(
            MakeupSessionQuiz.session_id == makeup.id,
            Quiz.id == payload.quiz_id,
        )
    )
    existing = session.scalar(
        select(QuizSession.id)
        .join(QuizParticipant, QuizParticipant.session_id == QuizSession.id)
        .where(
            QuizSession.makeup_session_id == makeup.id,
            QuizParticipant.student_id == (membership.id if membership else -1),
        )
    )
    if membership is None or quiz is None or existing is not None:
        raise ApiError(
            409, ErrorCode.MAKEUP_SELECTION_INVALID, "Sélection de quiz invalide"
        )
    return makeup, membership, quiz


def claim_makeup_selection(
    makeup: MakeupSession, membership: Student, session: Session
) -> None:
    """Record the student's one choice, refusing a second or a late one."""
    waiting = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == SessionStatus.WAITING,
        )
        .values(status=SessionStatus.WAITING)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(waiting) != 1:
        session.rollback()
        raise ApiError(
            409,
            ErrorCode.MAKEUP_SELECTION_CLOSED,
            "Ce rattrapage n’accepte plus de choix",
        )
    claimed_student_id = session.scalar(
        insert(MakeupSessionSelection)
        .values(session_id=makeup.id, student_id=membership.id)
        .on_conflict_do_nothing(
            index_elements=[
                MakeupSessionSelection.session_id,
                MakeupSessionSelection.student_id,
            ]
        )
        .returning(MakeupSessionSelection.student_id)
    )
    if claimed_student_id is None:
        raise ApiError(
            409, ErrorCode.MAKEUP_SELECTION_INVALID, "Sélection de quiz invalide"
        )


def makeup_child_session(
    makeup: MakeupSession, quiz: Quiz, session: Session
) -> QuizSession:
    """The student's own session of the quiz they chose."""
    child = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_answer_review=quiz.allow_answer_review,
        show_provisional_grades=quiz.show_provisional_grades,
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=False,
        class_id=makeup.class_id,
        class_name=makeup.class_name,
        join_code=generate_join_code(session),
        status=SessionStatus.WAITING,
        makeup_session_id=makeup.id,
    )
    session.add(child)
    session.flush()
    return child


def draw_makeup_questions(
    child: QuizSession,
    makeup: MakeupSession,
    quiz: Quiz,
    membership: Student,
    session: Session,
) -> None:
    """Draw questions no other student of this makeup got for the same quiz."""
    existing_draw_rows = list(
        session.execute(
            select(
                QuizSessionStudentQuestion.session_id,
                QuizSessionStudentQuestion.question_id,
            )
            .join(
                QuizSession,
                QuizSession.id == QuizSessionStudentQuestion.session_id,
            )
            .where(
                QuizSession.makeup_session_id == makeup.id,
                QuizSession.quiz_id == quiz.id,
            )
        )
    )
    questions_by_session: dict[int, list[int]] = defaultdict(list)
    for existing_session_id, question_id in existing_draw_rows:
        questions_by_session[existing_session_id].append(question_id)
    used_draws = {
        tuple(sorted(question_ids)) for question_ids in questions_by_session.values()
    }
    question_ids = draw_unique_question_ids(
        question_draw_pool(quiz, session), used_draws
    )
    session.add_all(
        QuizSessionStudentQuestion(
            session_id=child.id,
            student_id=membership.id,
            student_identifier=membership.identifier,
            question_id=question_id,
            position=position,
        )
        for position, question_id in enumerate(question_ids)
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
