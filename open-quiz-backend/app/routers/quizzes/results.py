"""Quiz results: finished sessions, their export, grading and publication.

Teachers list and export the results of their finished sessions, read each
participant's answers, grade written answers and publish the grades; students
list the results of their own finished exams, provisional until published.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core.audit import audit_event
from app.core.config import app_settings
from app.core.dependencies import DbSession, ProfessorUser, current_student
from app.core.errors import ApiError, ErrorCode
from app.core.pagination import (
    LIKE_ESCAPE_CHARACTER,
    Paging,
    contains_pattern,
)
from app.enums import AnswerMode, QuizMode, SessionStatus
from app.models import (
    Question,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    StudentAccount,
)
from app.records.quizzes import owned_quiz, owned_quiz_session
from app.records.student_accounts import owned_class
from app.responses.answer_reviews import answer_review
from app.responses.student_history import student_quiz_history
from app.responses.teacher_sessions import session_response
from app.schemas.quizzes import QuizSessionResponse
from app.schemas.student_quizzes import (
    QuizAnswerGrade,
    QuizAnswerReview,
    StudentQuizHistoryItem,
)
from app.services.grading import rounded_score, session_question_points
from app.services.question_assignments import session_question_ids
from app.services.results import finished_session_responses, stream_results_csv
from app.services.session_retention import retained_exam_result

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def exam_result_cutoff(request: Request) -> datetime:
    """Start time before which a finished exam is past its result retention."""
    retention_days = app_settings(request).quiz_result_retention_days
    return datetime.now(UTC) - timedelta(days=retention_days)


@router.get("/sessions/results", response_model=list[QuizSessionResponse])
def list_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    paging: Paging,
    quiz_search: Annotated[str, Query(max_length=160)] = "",
    class_id: Annotated[int | None, Query(ge=1)] = None,
    started_from: datetime | None = None,
    started_before: datetime | None = None,
) -> list[QuizSessionResponse]:
    """Finished exam results, newest first.

    ``class_id`` keeps one class's results (another teacher's class yields
    none, as ownership is checked through the quiz). ``started_from`` and
    ``started_before`` bound the start time, ``[from, before)``, with the
    creation time standing in for a session that never started.
    """
    filters = [
        Quiz.owner_id == professor.id,
        Quiz.mode == QuizMode.EXAM,
        QuizSession.status == SessionStatus.FINISHED,
        retained_exam_result(exam_result_cutoff(request)),
    ]
    if quiz_search:
        filters.append(
            func.coalesce(QuizSession.quiz_title, Quiz.title).ilike(
                contains_pattern(quiz_search), escape=LIKE_ESCAPE_CHARACTER
            )
        )
    if class_id is not None:
        filters.append(QuizSession.class_id == class_id)
    session_start = func.coalesce(QuizSession.started_at, QuizSession.created_at)
    if started_from is not None:
        filters.append(session_start >= started_from)
    if started_before is not None:
        filters.append(session_start < started_before)
    total = (
        session.scalar(
            select(func.count())
            .select_from(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*filters)
        )
        or 0
    )
    paging.set_total(total)
    rows = list(
        session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*filters)
            .order_by(
                QuizSession.started_at.desc(),
                QuizSession.created_at.desc(),
                QuizSession.id.desc(),
            )
            .offset(paging.offset)
            .limit(paging.page_size)
        )
    )
    return finished_session_responses(rows, session)


@router.get("/sessions/results/export")
def export_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    class_id: Annotated[int, Query(ge=1)],
    quiz_id: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    student_class = owned_class(class_id, professor.id, session)

    if quiz_id is not None:
        owned_quiz(quiz_id, professor.id, session)
    safe_class_id = student_class.id
    safe_quiz = f"-quiz-{quiz_id}" if quiz_id is not None else "-tous-les-quiz"
    filename = f"resultats-classe-{safe_class_id}{safe_quiz}.csv"
    return StreamingResponse(
        stream_results_csv(
            request.app.state.session_factory,
            professor.id,
            class_id,
            quiz_id,
            retained_after=exam_result_cutoff(request),
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/sessions/{session_id}/participants/{participant_id}/answers",
    response_model=list[QuizAnswerReview],
)
def list_participant_answers(
    session_id: int,
    participant_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizAnswerReview]:
    quiz_session, _ = owned_quiz_session(session_id, professor.id, session)
    if quiz_session.status != SessionStatus.FINISHED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_FINISHED,
            "Les réponses sont disponibles une fois le quiz terminé",
        )
    participant = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.id == participant_id,
            QuizParticipant.session_id == quiz_session.id,
        )
    )
    if participant is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.PARTICIPANT_NOT_FOUND,
            "Participant introuvable",
        )
    rows = list(
        session.execute(
            select(QuizAnswer, Question)
            .join(Question, Question.id == QuizAnswer.question_id)
            .where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    if (
        participant.left_at is not None
        and (
            quiz_session.started_at is None
            or participant.left_at <= quiz_session.started_at
        )
        and len(rows) == 0
    ):
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.PARTICIPANT_NOT_FOUND,
            "Participant introuvable",
        )
    question_order = {
        question_id: position
        for position, question_id in enumerate(
            session_question_ids(quiz_session, session, participant)
        )
    }
    question_points = session_question_points(quiz_session, session, participant)
    rows.sort(key=lambda row: question_order.get(row[1].id, len(question_order)))
    question_ids = [question.id for _, question in rows]
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    codes_by_question: dict[int, QuestionCode] = {}
    if question_ids:
        for choice in session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id.in_(question_ids))
            .order_by(QuestionChoice.position, QuestionChoice.id)
        ):
            choices_by_question[choice.question_id].append(choice)
        for code in session.scalars(
            select(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
        ):
            codes_by_question[code.question_id] = code
    return [
        answer_review(
            answer,
            question,
            question_order.get(question.id, 0),
            choices_by_question[question.id],
            question_points.get(question.id, 0),
            codes_by_question.get(question.id),
        )
        for answer, question in rows
    ]


@router.get(
    "/student/results",
    response_model=list[StudentQuizHistoryItem],
)
def list_student_quiz_history(
    student: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> list[StudentQuizHistoryItem]:
    return student_quiz_history(student.id, session)


@router.post(
    "/sessions/{session_id}/publish-grades",
    response_model=QuizSessionResponse,
)
def publish_quiz_grades(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor.id, session)
    # Grading locks this row too: a mark being saved is in before publication.
    session.refresh(quiz_session, with_for_update=True)
    if quiz_session.status != SessionStatus.FINISHED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_FINISHED,
            "Les notes ne peuvent être publiées qu'une fois le quiz terminé",
        )
    pending_count = session.scalar(
        select(func.count(QuizAnswer.id)).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.is_graded.is_(False),
        )
    )
    if pending_count:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.GRADES_PENDING,
            "Toutes les réponses doivent être corrigées avant publication",
        )
    if quiz_session.grades_published_at is None:
        quiz_session.grades_published_at = datetime.now(UTC)
        audit_event(
            "quiz.grades_published",
            professor_id=professor.id,
            session_id=quiz_session.id,
        )
        session.commit()
        session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/answers/{answer_id}/grade",
    response_model=QuizAnswerReview,
)
def grade_written_answer(
    session_id: int,
    answer_id: int,
    payload: QuizAnswerGrade,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizAnswerReview:
    quiz_session, _ = owned_quiz_session(session_id, professor.id, session)
    # Held until the commit, so publication cannot slip in between the check
    # below and the new mark, which would change grades already published.
    session.refresh(quiz_session, with_for_update=True)
    if quiz_session.status != SessionStatus.FINISHED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_SESSION_NOT_FINISHED,
            "La correction est disponible une fois le quiz terminé",
        )
    if quiz_session.grades_published_at is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.GRADES_PUBLISHED,
            "Les notes publiées ne peuvent plus être modifiées",
        )
    row = session.execute(
        select(QuizAnswer, Question)
        .join(Question, Question.id == QuizAnswer.question_id)
        .where(
            QuizAnswer.id == answer_id,
            QuizAnswer.session_id == quiz_session.id,
        )
    ).one_or_none()
    if row is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, ErrorCode.ANSWER_NOT_FOUND, "Réponse introuvable"
        )
    answer, question = row
    participant = session.get(QuizParticipant, answer.participant_id)
    question_ids = (
        session_question_ids(quiz_session, session, participant)
        if participant is not None
        else []
    )
    if question.id not in question_ids:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.ANSWER_QUESTION_NOT_IN_SESSION,
            "La question ne fait pas partie de cette session",
        )
    position = question_ids.index(question.id)
    if question.answer_mode != AnswerMode.WRITTEN:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.ANSWER_NOT_WRITTEN,
            "Seules les réponses rédactionnelles sont corrigées manuellement",
        )
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id == question.id)
            .order_by(QuestionChoice.position, QuestionChoice.id)
        )
    )
    # A missing participant has no questions, so the check above refused it.
    max_score = session_question_points(
        quiz_session, session, cast(QuizParticipant, participant)
    ).get(question.id, 0)
    if payload.score > max_score:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.GRADE_ABOVE_MAXIMUM,
            f"La note ne peut pas dépasser {max_score:g}",
        )
    answer.score = rounded_score(payload.score)
    answer.is_graded = True
    answer.feedback = (
        payload.feedback.strip()
        if payload.feedback and payload.feedback.strip()
        else None
    )
    session.commit()
    code = session.get(QuestionCode, question.id)
    return answer_review(answer, question, position, choices, max_score, code)
