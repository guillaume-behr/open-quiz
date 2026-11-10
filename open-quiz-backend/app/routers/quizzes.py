from datetime import UTC, datetime
from math import ceil
from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    Request,
    status,
)
from sqlalchemy import delete, func, select, update

from app.audit import audit_event
from app.class_names import format_class_name
from app.database import affected_rows
from app.dependencies import DbSession, ProfessorUser
from app.enums import QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.live_updates import (
    publish_active_quiz_sessions_update,
    publish_quiz_topics,
    publish_quiz_update,
)
from app.models import (
    MakeupSessionQuiz,
    QuestionBank,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    Student,
    StudentClass,
    TrainingQuizProfile,
)
from app.pagination import (
    LIKE_ESCAPE_CHARACTER,
    Paging,
    contains_pattern,
    focused_page,
)
from app.participants import (
    generate_join_code,
)
from app.question_responses import load_question_responses
from app.quiz_lookup import (
    owned_quiz,
    owned_quiz_session,
)
from app.quiz_session_records import (
    delete_quiz_session_records,
)
from app.schemas import (
    QuestionResponse,
    QuizCreate,
    QuizLaunch,
    QuizResponse,
    QuizSessionResponse,
)
from app.services.question_draws import (
    difficulty_counts_for_banks,
    draw_question_ids,
    draw_unique_question_ids,
    question_draw_pool,
    quiz_bank_ids,
)
from app.services.session_lifecycle import (
    discard_active_training_sessions,
    expire_quiz_session,
)
from app.session_responses import (
    active_session_responses,
    quiz_responses,
    session_response,
)
from app.session_status import ACTIVE_SESSION_STATUSES

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def validate_bank_selection(
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBank]:
    banks = list(
        session.scalars(
            select(QuestionBank).where(
                QuestionBank.id.in_(payload.question_bank_ids),
                QuestionBank.owner_id == professor.id,
            )
        )
    )
    if len(banks) != len(payload.question_bank_ids):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.QUESTION_BANK_SELECTION_INVALID,
            "Une ou plusieurs banques de questions sont invalides",
        )
    difficulty_counts_for_banks(payload, payload.question_bank_ids, session)
    return banks


def quiz_response(quiz: Quiz, session: DbSession) -> QuizResponse:
    return quiz_responses([quiz], session)[0]


@router.get("", response_model=list[QuizResponse])
def list_quizzes(
    professor: ProfessorUser,
    session: DbSession,
    paging: Paging,
    search: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
    mode: Annotated[str, Query(pattern="^exam$")] = QuizMode.EXAM,
    focus: Annotated[int | None, Query(ge=1)] = None,
) -> list[QuizResponse]:
    filters = [Quiz.owner_id == professor.id, Quiz.mode == mode]
    if search:
        filters.append(
            Quiz.title.ilike(contains_pattern(search), escape=LIKE_ESCAPE_CHARACTER)
        )
    if grade_level:
        filters.append(
            Quiz.id.in_(
                select(QuizQuestionBank.quiz_id)
                .join(
                    QuestionBank,
                    QuestionBank.id == QuizQuestionBank.question_bank_id,
                )
                .where(QuestionBank.grade_level == grade_level)
            )
        )
    order = (Quiz.title, Quiz.id)
    if focus is not None:
        paging.page = (
            focused_page(session, Quiz, filters, order, focus, paging.page_size)
            or paging.page
        )
    total = session.scalar(select(func.count()).select_from(Quiz).where(*filters)) or 0
    paging.set_total(total)
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(*filters)
            .order_by(*order)
            .offset(paging.offset)
            .limit(paging.page_size)
        )
    )
    return quiz_responses(quizzes, session)


@router.post(
    "",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_quiz(
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizResponse:
    validate_bank_selection(payload, professor, session)
    quiz = Quiz(
        owner_id=professor.id,
        mode=payload.mode,
        title=payload.title,
        source_language=payload.source_language,
        question_count=payload.question_count,
        duration_seconds=payload.duration_seconds,
        allow_previous_questions=payload.allow_previous_questions,
        allow_answer_review=payload.allow_answer_review,
        allow_negative_points=payload.allow_negative_points,
        same_questions_for_all=payload.same_questions_for_all,
        easy_question_count=payload.easy_question_count,
        medium_question_count=payload.medium_question_count,
        hard_question_count=payload.hard_question_count,
        easy_points=0,
        medium_points=0,
        hard_points=0,
    )
    session.add(quiz)
    session.flush()
    session.add_all(
        QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank_id)
        for bank_id in payload.question_bank_ids
    )
    session.commit()
    session.refresh(quiz)
    return quiz_response(quiz, session)


@router.get("/sessions/active", response_model=list[QuizSessionResponse])
def list_active_sessions(
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizSessionResponse]:
    return active_session_responses(professor, session)


@router.get(
    "/sessions/{session_id}",
    response_model=QuizSessionResponse,
)
def get_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    return session_response(quiz_session, quiz, session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status not in {SessionStatus.FINISHED, SessionStatus.CANCELLED}:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_DELETABLE,
            "Seules les sessions terminées ou annulées peuvent être supprimées",
        )
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()
    audit_event(
        "quiz.session_deleted",
        professor_id=professor.id,
        session_id=session_id,
    )


@router.post(
    "/sessions/{session_id}/start",
    response_model=QuizSessionResponse,
)
def start_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status == SessionStatus.WAITING:
        started_at = datetime.now(UTC)
        transition = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status == SessionStatus.WAITING,
            )
            .values(status=SessionStatus.IN_PROGRESS, started_at=started_at)
            .execution_options(synchronize_session=False)
        )
        if affected_rows(transition) != 1:
            session.rollback()
            session.refresh(quiz_session)
            return session_response(quiz_session, quiz, session)
        participants = list(
            session.scalars(
                select(QuizParticipant).where(
                    QuizParticipant.session_id == quiz_session.id,
                    QuizParticipant.left_at.is_(None),
                )
            )
        )
        if not participants:
            session.rollback()
            raise ApiError(
                status.HTTP_409_CONFLICT,
                ErrorCode.QUIZ_SESSION_NO_PARTICIPANTS,
                "Au moins un élève doit rejoindre le quiz avant son démarrage",
            )
        quiz_session.status = SessionStatus.IN_PROGRESS
        quiz_session.started_at = started_at
        for participant in participants:
            participant.current_position = 0
        session.commit()
        session.refresh(quiz_session)
        publish_quiz_update(request, quiz_session, session)
    return session_response(quiz_session, quiz, session)


@router.delete(
    "/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_quiz(
    quiz_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz = owned_quiz(quiz_id, professor, session)
    active_session_id = session.scalar(
        select(QuizSession.id)
        .where(
            QuizSession.quiz_id == quiz.id,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .limit(1)
    )
    if active_session_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_HAS_ACTIVE_SESSION,
            "Un quiz avec une session active ne peut pas être supprimé",
        )
    if (
        session.scalar(
            select(QuizSession.id)
            .where(
                QuizSession.quiz_id == quiz.id,
                QuizSession.status == SessionStatus.FINISHED,
            )
            .limit(1)
        )
        is not None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_HAS_RESULTS,
            "Impossible de supprimer ce quiz car il possède des résultats "
            "qui doivent être conservés",
        )
    if (
        session.scalar(
            select(MakeupSessionQuiz.session_id)
            .where(MakeupSessionQuiz.quiz_id == quiz.id)
            .limit(1)
        )
        is not None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_USED_BY_MAKEUP,
            "Impossible de supprimer ce quiz car un rattrapage l’utilise",
        )
    session.execute(delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id == quiz_id))
    session.execute(
        delete(TrainingQuizProfile).where(TrainingQuizProfile.quiz_id == quiz_id)
    )
    session.execute(
        delete(MakeupSessionQuiz).where(MakeupSessionQuiz.quiz_id == quiz_id)
    )
    cancelled_session_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                QuizSession.quiz_id == quiz.id,
                QuizSession.status == SessionStatus.CANCELLED,
            )
        )
    )
    delete_quiz_session_records(cancelled_session_ids, session)
    session.execute(delete(Quiz).where(Quiz.id == quiz_id))
    session.commit()
    audit_event(
        "quiz.deleted",
        professor_id=professor.id,
        quiz_id=quiz_id,
    )


@router.post(
    "/sessions/{session_id}/pause",
    response_model=QuizSessionResponse,
)
def pause_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != SessionStatus.IN_PROGRESS:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_RUNNING,
            "Seul un quiz en cours peut être mis en pause",
        )
    transition = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == SessionStatus.IN_PROGRESS,
        )
        .values(status=SessionStatus.PAUSED, paused_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if affected_rows(transition) != 1:
        # A concurrent request finished or paused it since it was read.
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_RUNNING,
            "Seul un quiz en cours peut être mis en pause",
        )
    session.commit()
    session.refresh(quiz_session)
    publish_quiz_update(request, quiz_session, session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/resume",
    response_model=QuizSessionResponse,
)
def resume_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != SessionStatus.PAUSED or quiz_session.paused_at is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_PAUSED,
            "Seul un quiz en pause peut être repris",
        )
    transition = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == SessionStatus.PAUSED,
            QuizSession.paused_at == quiz_session.paused_at,
        )
        .values(
            status=SessionStatus.IN_PROGRESS,
            paused_at=None,
            paused_duration_seconds=(quiz_session.paused_duration_seconds or 0)
            + ceil(
                max(0, (datetime.now(UTC) - quiz_session.paused_at).total_seconds())
            ),
        )
        .execution_options(synchronize_session=False)
    )
    if affected_rows(transition) != 1:
        # A concurrent request resumed or finished it since it was read.
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_PAUSED,
            "Seul un quiz en pause peut être repris",
        )
    session.commit()
    session.refresh(quiz_session)
    publish_quiz_update(request, quiz_session, session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status not in ACTIVE_SESSION_STATUSES:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_CANCELLABLE,
            "Cette session ne peut plus être annulée",
        )
    if (
        session.scalar(
            select(QuizAnswer.id)
            .where(QuizAnswer.session_id == quiz_session.id)
            .limit(1)
        )
        is not None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_HAS_ANSWERS,
            "Impossible d’annuler ce quiz car des réponses ont déjà été "
            "enregistrées. Terminez la session pour conserver les résultats",
        )
    join_code = quiz_session.join_code
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()
    publish_quiz_topics(request, session_id, join_code)
    publish_active_quiz_sessions_update(request, professor.id)
    audit_event(
        "quiz.session_cancelled_and_deleted",
        professor_id=professor.id,
        session_id=session_id,
    )


@router.get("/{quiz_id}/preview", response_model=list[QuestionResponse])
def preview_quiz(
    quiz_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionResponse]:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != QuizMode.EXAM:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"
        )
    return load_question_responses(list(draw_question_ids(quiz, session)), session)


@router.post(
    "/{quiz_id}/update",
    response_model=QuizResponse,
)
def update_quiz(
    quiz_id: int,
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizResponse:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != QuizMode.EXAM:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"
        )
    active_session_id = session.scalar(
        select(QuizSession.id)
        .where(
            QuizSession.quiz_id == quiz.id,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .limit(1)
    )
    if active_session_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_HAS_ACTIVE_SESSION,
            "Un quiz avec une session active ne peut pas être modifié",
        )
    validate_bank_selection(payload, professor, session)
    quiz.title = payload.title
    quiz.mode = QuizMode.EXAM
    quiz.source_language = payload.source_language
    quiz.question_count = payload.question_count
    quiz.duration_seconds = payload.duration_seconds
    quiz.allow_previous_questions = payload.allow_previous_questions
    quiz.allow_answer_review = payload.allow_answer_review
    quiz.allow_negative_points = payload.allow_negative_points
    quiz.same_questions_for_all = payload.same_questions_for_all
    quiz.easy_question_count = payload.easy_question_count
    quiz.medium_question_count = payload.medium_question_count
    quiz.hard_question_count = payload.hard_question_count
    quiz.easy_points = 0
    quiz.medium_points = 0
    quiz.hard_points = 0
    session.execute(delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id == quiz.id))
    session.add_all(
        QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank_id)
        for bank_id in payload.question_bank_ids
    )
    session.commit()
    session.refresh(quiz)
    return quiz_response(quiz, session)


@router.post(
    "/{quiz_id}/launch",
    response_model=QuizSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def launch_quiz(
    quiz_id: int,
    payload: QuizLaunch,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != QuizMode.EXAM:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_TRAINING_NOT_LAUNCHABLE,
            "Un entraînement est lancé directement par l’élève",
        )
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == payload.class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.QUIZ_CLASS_INVALID,
            "La classe sélectionnée est invalide",
        )
    students = list(
        session.scalars(
            select(Student).where(
                Student.class_id == student_class.id,
                Student.account_id.is_not(None),
            )
        )
    )
    if not students:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_CLASS_EMPTY,
            "La classe doit contenir au moins un élève",
        )
    discard_active_training_sessions(
        select(Student.id).where(Student.class_id == student_class.id),
        quiz_bank_ids(quiz.id, session),
        session,
    )
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_answer_review=quiz.allow_answer_review,
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=quiz.same_questions_for_all,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status=SessionStatus.WAITING,
    )
    session.add(quiz_session)
    session.flush()
    pool = question_draw_pool(quiz, session)
    if quiz.same_questions_for_all:
        session.add_all(
            QuizSessionQuestion(
                session_id=quiz_session.id,
                question_id=question_id,
                position=position,
            )
            for position, question_id in enumerate(pool.draw())
        )
    else:
        assignments: list[QuizSessionStudentQuestion] = []
        used_draws: set[tuple[int, ...]] = set()
        for student in students:
            student_question_ids = draw_unique_question_ids(pool, used_draws)
            assignments.extend(
                QuizSessionStudentQuestion(
                    session_id=quiz_session.id,
                    student_id=student.id,
                    student_identifier=student.identifier,
                    question_id=question_id,
                    position=position,
                )
                for position, question_id in enumerate(student_question_ids)
            )
        session.add_all(assignments)
    session.commit()
    session.refresh(quiz_session)
    publish_active_quiz_sessions_update(request, professor.id)
    return session_response(quiz_session, quiz, session)
