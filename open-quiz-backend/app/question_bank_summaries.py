from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Question, QuestionBank
from app.schemas import QuestionBankResponse


def question_bank_summary_query():
    """Build the shared aggregate query used for question-bank summaries."""
    return select(
        QuestionBank,
        func.count(Question.id),
        func.sum(case((Question.difficulty == "easy", 1), else_=0)),
        func.sum(case((Question.difficulty == "medium", 1), else_=0)),
        func.sum(case((Question.difficulty == "hard", 1), else_=0)),
    ).outerjoin(Question, Question.question_bank_id == QuestionBank.id)


def question_bank_summary_response(
    question_bank: QuestionBank,
    question_count: int,
    easy_count: int | None,
    medium_count: int | None,
    hard_count: int | None,
) -> QuestionBankResponse:
    return QuestionBankResponse.model_validate(question_bank).model_copy(
        update={
            "question_count": question_count,
            "easy_question_count": easy_count or 0,
            "medium_question_count": medium_count or 0,
            "hard_question_count": hard_count or 0,
        }
    )


def load_question_bank_summaries(
    question_bank_ids: list[int], session: Session
) -> list[QuestionBankResponse]:
    if not question_bank_ids:
        return []
    rows = session.execute(
        question_bank_summary_query()
        .where(QuestionBank.id.in_(question_bank_ids))
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
    )
    return [question_bank_summary_response(*row) for row in rows]
