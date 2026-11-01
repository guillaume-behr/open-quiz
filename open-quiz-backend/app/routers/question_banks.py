from typing import Annotated

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.grade_levels import ensure_grade_level
from app.models import (
    ClassTrainingQuestionBank,
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.question_bank_summaries import (
    question_bank_summary_query,
    question_bank_summary_response,
)
from app.quiz_session_records import delete_quiz_session_records
from app.schemas import (
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBankUpdate,
)

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])


@router.get("", response_model=list[QuestionBankResponse])
def list_question_banks(
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    search: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
) -> list[QuestionBankResponse]:
    """Return one filtered page of question banks owned by the professor."""
    filters = [QuestionBank.owner_id == professor.id]
    if search:
        filters.append(QuestionBank.chapter.ilike(f"%{search}%"))
    if grade_level:
        filters.append(QuestionBank.grade_level == grade_level)
    total = (
        session.scalar(select(func.count()).select_from(QuestionBank).where(*filters))
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    rows = session.execute(
        question_bank_summary_query()
        .where(*filters)
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [
        question_bank_summary_response(
            question_bank,
            question_count,
            easy_count,
            medium_count,
            hard_count,
        )
        for (
            question_bank,
            question_count,
            easy_count,
            medium_count,
            hard_count,
        ) in rows
    ]


@router.post(
    "",
    response_model=QuestionBankResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question_bank(
    payload: QuestionBankCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBank:
    """Create a question bank classified by grade level and chapter."""
    question_bank = QuestionBank(
        owner_id=professor.id,
        grade_level=payload.grade_level,
        chapter=payload.chapter,
    )
    session.add(question_bank)
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une banque existe déjà pour ce niveau et ce titre",
        ) from None
    session.refresh(question_bank)
    return question_bank


@router.post("/{question_bank_id}/update", response_model=QuestionBankResponse)
def update_question_bank(
    question_bank_id: int,
    payload: QuestionBankUpdate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBankResponse:
    """Update the title and grade level of a question bank."""
    question_bank = owned_question_bank(question_bank_id, professor, session)
    if question_bank.grade_level != payload.grade_level:
        mismatched_class_ids = select(StudentClass.id).where(
            StudentClass.owner_id == professor.id,
            StudentClass.grade_level != payload.grade_level,
        )
        session.execute(
            delete(ClassTrainingQuestionBank).where(
                ClassTrainingQuestionBank.question_bank_id == question_bank.id,
                ClassTrainingQuestionBank.class_id.in_(mismatched_class_ids),
            )
        )
    question_bank.grade_level = payload.grade_level
    question_bank.chapter = payload.chapter
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une banque existe déjà pour ce niveau et ce titre",
        ) from None
    session.refresh(question_bank)
    row = session.execute(
        question_bank_summary_query()
        .where(QuestionBank.id == question_bank.id)
        .group_by(QuestionBank.id)
    ).one()
    return question_bank_summary_response(*row)


@router.delete(
    "/{question_bank_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_question_bank(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    """Delete a question bank and every question it contains."""
    owned_question_bank(question_bank_id, professor, session)
    if (
        session.scalar(
            select(QuizQuestionBank.quiz_id).where(
                QuizQuestionBank.question_bank_id == question_bank_id
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette banque est utilisée par un quiz",
        )
    question_ids = list(
        session.scalars(
            select(Question.id).where(Question.question_bank_id == question_bank_id)
        )
    )
    discard_training_sessions_using_questions(question_ids, session)
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.question_bank_id == question_bank_id
        )
    )
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id.in_(question_ids))
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
    )
    session.execute(
        delete(Question).where(Question.question_bank_id == question_bank_id)
    )
    session.execute(delete(QuestionBank).where(QuestionBank.id == question_bank_id))
    session.commit()


def owned_question_bank(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBank:
    question_bank = session.scalar(
        select(QuestionBank).where(
            QuestionBank.id == question_bank_id,
            QuestionBank.owner_id == professor.id,
        )
    )
    if question_bank is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Banque de questions introuvable",
        )
    return question_bank


def discard_training_sessions_using_questions(
    question_ids: list[int],
    session: DbSession,
) -> None:
    """Drop every training attempt that drew any of these questions."""
    if not question_ids:
        return
    common_session_ids = select(QuizSessionQuestion.session_id).where(
        QuizSessionQuestion.question_id.in_(question_ids)
    )
    personalized_session_ids = select(QuizSessionStudentQuestion.session_id).where(
        QuizSessionStudentQuestion.question_id.in_(question_ids)
    )
    training_session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == "training",
                QuizSession.id.in_(common_session_ids.union(personalized_session_ids)),
            )
        )
    )
    if not training_session_ids:
        return
    delete_quiz_session_records(training_session_ids, session)
