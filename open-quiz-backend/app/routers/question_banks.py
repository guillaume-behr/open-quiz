from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    status,
)
from sqlalchemy import delete, func, select

from app.dependencies import DbSession, ProfessorUser
from app.errors import ApiError, ErrorCode
from app.grade_levels import ensure_grade_level
from app.models import (
    ClassTrainingQuestionBank,
    Question,
    QuestionBank,
    QuizQuestionBank,
    StudentClass,
)
from app.pagination import (
    LIKE_ESCAPE_CHARACTER,
    Paging,
    contains_pattern,
    focused_page,
)
from app.question_bank_summaries import (
    question_bank_summary_query,
    question_bank_summary_response,
)
from app.question_records import (
    discard_training_sessions_using_questions,
    owned_question_bank,
)
from app.schemas import (
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBankUpdate,
)
from app.unique_names import commit_unique_bank

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])


@router.get("", response_model=list[QuestionBankResponse])
def list_question_banks(
    professor: ProfessorUser,
    session: DbSession,
    paging: Paging,
    search: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
    focus: Annotated[int | None, Query(ge=1)] = None,
) -> list[QuestionBankResponse]:
    """Return one filtered page of question banks owned by the professor.

    With ``focus``, the page returned is the one holding that bank.
    """
    filters = [QuestionBank.owner_id == professor.id]
    if search:
        filters.append(
            QuestionBank.chapter.ilike(
                contains_pattern(search), escape=LIKE_ESCAPE_CHARACTER
            )
        )
    if grade_level:
        filters.append(QuestionBank.grade_level == grade_level)
    order = (QuestionBank.grade_level, QuestionBank.chapter, QuestionBank.id)
    if focus is not None:
        paging.page = (
            focused_page(session, QuestionBank, filters, order, focus, paging.page_size)
            or paging.page
        )
    total = (
        session.scalar(select(func.count()).select_from(QuestionBank).where(*filters))
        or 0
    )
    paging.set_total(total)
    rows = session.execute(
        question_bank_summary_query()
        .where(*filters)
        .group_by(QuestionBank.id)
        .order_by(*order)
        .offset(paging.offset)
        .limit(paging.page_size)
    )
    return [
        question_bank_summary_response(
            question_bank,
            question_count,
            easy_count,
            medium_count,
            hard_count,
            trainable_count,
        )
        for (
            question_bank,
            question_count,
            easy_count,
            medium_count,
            hard_count,
            trainable_count,
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
        grade_level=ensure_grade_level(professor.id, payload.grade_level, session),
        chapter=payload.chapter,
    )
    session.add(question_bank)
    commit_unique_bank(session)
    session.refresh(question_bank)
    return question_bank


@router.post("/{question_bank_id}/update", response_model=QuestionBankResponse)
def update_question_bank(
    question_bank_id: int,
    payload: QuestionBankUpdate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBankResponse:
    """Update the chapter and grade level of a question bank.

    A new grade level withdraws the bank from the training of the classes of
    another level.
    """
    question_bank = owned_question_bank(question_bank_id, professor, session)
    grade_level = ensure_grade_level(professor.id, payload.grade_level, session)
    if question_bank.grade_level != grade_level:
        mismatched_class_ids = select(StudentClass.id).where(
            StudentClass.owner_id == professor.id,
            StudentClass.grade_level != grade_level,
        )
        session.execute(
            delete(ClassTrainingQuestionBank).where(
                ClassTrainingQuestionBank.question_bank_id == question_bank.id,
                ClassTrainingQuestionBank.class_id.in_(mismatched_class_ids),
            )
        )
    question_bank.grade_level = grade_level
    question_bank.chapter = payload.chapter
    commit_unique_bank(session)
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
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUESTION_BANK_IN_USE,
            "Cette banque est utilisée par un quiz",
        )
    question_ids = list(
        session.scalars(
            select(Question.id).where(Question.question_bank_id == question_bank_id)
        )
    )
    discard_training_sessions_using_questions(question_ids, session)
    # Questions, their choices and code, and class training links cascade.
    session.execute(delete(QuestionBank).where(QuestionBank.id == question_bank_id))
    session.commit()
