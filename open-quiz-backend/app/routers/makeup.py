"""Makeup sessions: one join code for a class to retake finished quizzes.

The teacher offers some of the quizzes the class has finished; each student
joins with the code, picks one of them and answers it in a child QuizSession
of their own.
"""

from collections import defaultdict
from datetime import UTC, datetime
from math import ceil
from secrets import token_urlsafe
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.class_names import format_class_name
from app.dependencies import DbSession, ProfessorUser
from app.errors import ErrorCode, api_error
from app.grading import (
    compute_final_scores,
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
from app.routers.quizzes import (
    as_utc,
    delete_makeup_session_records,
    discard_active_training_sessions,
    enforce_public_rate_limit,
    generate_join_code,
    participant_token_hash,
    publish_active_quiz_sessions_update,
    publish_makeup_update,
    publish_quiz_topics,
    publish_quiz_update,
    quiz_responses,
    session_response,
    student_state_response,
)
from app.routers.student_auth import current_student
from app.schemas import (
    MakeupParticipantResponse,
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

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def makeup_session_response(
    makeup: MakeupSession, session: DbSession
) -> MakeupSessionResponse:
    quizzes = list(
        session.scalars(
            select(Quiz)
            .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
            .where(MakeupSessionQuiz.session_id == makeup.id)
            .order_by(Quiz.title, Quiz.id)
        )
    )
    child_sessions = list(
        session.scalars(
            select(QuizSession)
            .where(QuizSession.makeup_session_id == makeup.id)
            .order_by(QuizSession.id)
        )
    )
    quizzes_by_id = {quiz.id: quiz for quiz in quizzes}
    child_responses = [
        session_response(child, quizzes_by_id[child.quiz_id], session)
        for child in child_sessions
        if child.quiz_id in quizzes_by_id
    ]
    participants = [
        MakeupParticipantResponse(
            **participant.model_dump(),
            quiz_title=child.quiz_title,
            total_questions=child.total_questions,
        )
        for child in child_responses
        for participant in child.participants
    ]
    return MakeupSessionResponse(
        id=makeup.id,
        class_id=makeup.class_id,
        class_name=(
            format_class_name(student_class.grade_level, student_class.name)
            if makeup.class_id is not None
            and (student_class := session.get(StudentClass, makeup.class_id))
            is not None
            else makeup.class_name
        ),
        join_code=makeup.join_code,
        status=makeup.status,
        quizzes=[
            MakeupQuizOption(
                id=quiz.id,
                title=quiz.title,
                duration_seconds=quiz.duration_seconds,
            )
            for quiz in quizzes
        ],
        participant_count=len(participants),
        participants=participants,
        created_at=makeup.created_at,
    )


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
        raise HTTPException(status_code=404, detail="Session de rattrapage introuvable")
    return makeup


@router.get("/makeup/sessions", response_model=list[MakeupSessionResponse])
def list_makeup_sessions(
    professor: ProfessorUser, session: DbSession
) -> list[MakeupSessionResponse]:
    obsolete_cancelled_ids = list(
        session.scalars(
            select(MakeupSession.id).where(
                MakeupSession.owner_id == professor.id,
                MakeupSession.status == "cancelled",
                ~MakeupSession.id.in_(
                    select(QuizSession.makeup_session_id)
                    .join(QuizAnswer, QuizAnswer.session_id == QuizSession.id)
                    .where(QuizSession.makeup_session_id.is_not(None))
                ),
            )
        )
    )
    for makeup_session_id in obsolete_cancelled_ids:
        delete_makeup_session_records(makeup_session_id, session)
    if obsolete_cancelled_ids:
        session.commit()
    makeups = list(
        session.scalars(
            select(MakeupSession)
            .where(
                MakeupSession.owner_id == professor.id,
                MakeupSession.status != "cancelled",
            )
            .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
        )
    )
    return [makeup_session_response(item, session) for item in makeups]


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
                QuizSession.status == "finished",
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
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    finished_ids = class_finished_quiz_ids(student_class.id, professor, session)
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(
                Quiz.owner_id == professor.id,
                Quiz.mode == "exam",
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
                Quiz.mode == "exam",
            )
        )
    )
    if student_class is None or len(quizzes) != len(quiz_ids):
        raise HTTPException(status_code=422, detail="Classe ou quiz invalide")
    eligible = class_finished_quiz_ids(student_class.id, professor, session)
    if not quiz_ids.issubset(eligible):
        raise HTTPException(
            status_code=422,
            detail="Seuls les quiz déjà passés par la classe peuvent être rattrapés",
        )
    makeup = MakeupSession(
        owner_id=professor.id,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status="waiting",
    )
    session.add(makeup)
    session.flush()
    session.add_all(
        MakeupSessionQuiz(session_id=makeup.id, quiz_id=quiz_id) for quiz_id in quiz_ids
    )
    session.commit()
    publish_makeup_update(request, professor.id)
    return makeup_session_response(makeup, session)


@router.post(
    "/makeup/sessions/{session_id}/{action}",
    response_model=MakeupSessionResponse,
)
def control_makeup_session(
    session_id: int,
    action: str,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse | Response:
    makeup = owned_makeup_session(session_id, professor, session)
    allowed = {
        "start": ("waiting", "in_progress"),
        "pause": ("in_progress", "paused"),
        "resume": ("paused", "in_progress"),
        "finish": ("in_progress", "finished"),
        "cancel": ("waiting", "cancelled"),
    }
    if action not in allowed:
        raise HTTPException(status_code=404)
    expected, target = allowed[action]
    if makeup.status != expected:
        raise HTTPException(
            status_code=409, detail="Action impossible pour cette session"
        )
    child_topics = list(
        session.execute(
            select(QuizSession.id, QuizSession.join_code).where(
                QuizSession.makeup_session_id == makeup.id
            )
        )
    )
    if action == "cancel":
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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Impossible d’annuler ce rattrapage car des réponses ont déjà "
                    "été enregistrées"
                ),
            )
        delete_makeup_session_records(makeup.id, session)
        session.commit()
        for child_id, join_code in child_topics:
            publish_quiz_topics(request, child_id, join_code)
        publish_makeup_update(request, professor.id)
        publish_active_quiz_sessions_update(request, professor.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    transition = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == expected,
        )
        .values(status=target)
        .execution_options(synchronize_session=False)
    )
    if transition.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Action impossible pour cette session"
        )
    makeup.status = target
    children = list(
        session.scalars(
            select(QuizSession).where(QuizSession.makeup_session_id == makeup.id)
        )
    )
    if action == "start" and not children:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Au moins un élève doit choisir un quiz avant le démarrage",
        )
    now = datetime.now(UTC)
    for child in children:
        if action == "start":
            if child.status != "waiting":
                continue
            child.status = "in_progress"
            child.started_at = now
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = 0
        elif action == "pause":
            if child.status != "in_progress":
                continue
            child.status = "paused"
            child.paused_at = now
        elif action == "resume":
            if child.status != "paused" or child.paused_at is None:
                continue
            paused_at = as_utc(child.paused_at)
            child.paused_duration_seconds = (child.paused_duration_seconds or 0) + ceil(
                max(0, (now - paused_at).total_seconds())
            )
            child.paused_at = None
            child.status = "in_progress"
        else:  # finish
            if child.status not in {"in_progress", "paused"}:
                continue
            child.status = "finished"
            compute_final_scores(child, session)
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = None
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
            MakeupSession.status == "waiting",
        )
    )
    if makeup is None:
        # Bound join-code brute-force per student account, never per IP.
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
        raise HTTPException(
            status_code=403,
            detail=api_error(
                ErrorCode.MAKEUP_JOIN_REJECTED, "Impossible de rejoindre ce rattrapage"
            ),
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=403,
            detail=api_error(
                ErrorCode.MAKEUP_JOIN_REJECTED, "Impossible de rejoindre ce rattrapage"
            ),
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
        status="waiting",
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
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == join_code.strip().upper(),
            MakeupSession.status == "waiting",
        )
    )
    if makeup is None:
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.MAKEUP_SELECTION_CLOSED,
                "Ce rattrapage n’accepte plus de choix",
            ),
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
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.MAKEUP_SELECTION_INVALID, "Sélection de quiz invalide"
            ),
        )
    waiting = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == "waiting",
        )
        .values(status="waiting")
        .execution_options(synchronize_session=False)
    )
    if waiting.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.MAKEUP_SELECTION_CLOSED,
                "Ce rattrapage n’accepte plus de choix",
            ),
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
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.MAKEUP_SELECTION_INVALID, "Sélection de quiz invalide"
            ),
        )
    discard_active_training_sessions(
        [membership.id], quiz_bank_ids(quiz.id, session), session
    )
    child = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_answer_review=quiz.allow_answer_review,
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=False,
        class_id=makeup.class_id,
        class_name=makeup.class_name,
        join_code=generate_join_code(session),
        status="waiting",
        makeup_session_id=makeup.id,
    )
    session.add(child)
    session.flush()
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
