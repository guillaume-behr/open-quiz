from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.enums import AnswerMode, Difficulty
from app.models import Question, QuestionBank, QuizQuestionBank
from app.schemas.questions import QuestionBankResponse


def question_bank_summary_query() -> Select[
    QuestionBank, int, int | None, int | None, int | None, int | None, int
]:
    """Build the shared aggregate query used for question-bank summaries."""
    # A subquery rather than a join: joining the quizzes would repeat each
    # question once per quiz and inflate the question counts.
    quiz_count = (
        select(func.count(QuizQuestionBank.quiz_id))
        .where(QuizQuestionBank.question_bank_id == QuestionBank.id)
        .correlate(QuestionBank)
        .scalar_subquery()
    )
    return select(
        QuestionBank,
        func.count(Question.id),
        func.sum(case((Question.difficulty == Difficulty.EASY, 1), else_=0)),
        func.sum(case((Question.difficulty == Difficulty.MEDIUM, 1), else_=0)),
        func.sum(case((Question.difficulty == Difficulty.HARD, 1), else_=0)),
        # Training never draws written questions: only the others count there.
        func.sum(case((Question.answer_mode != AnswerMode.WRITTEN, 1), else_=0)),
        quiz_count,
    ).outerjoin(Question, Question.question_bank_id == QuestionBank.id)


def question_bank_summary_response(
    question_bank: QuestionBank,
    question_count: int,
    easy_count: int | None,
    medium_count: int | None,
    hard_count: int | None,
    trainable_count: int | None,
    quiz_count: int,
) -> QuestionBankResponse:
    return QuestionBankResponse.model_validate(question_bank).model_copy(
        update={
            "question_count": question_count,
            "easy_question_count": easy_count or 0,
            "medium_question_count": medium_count or 0,
            "hard_question_count": hard_count or 0,
            "trainable_question_count": trainable_count or 0,
            "quiz_count": quiz_count,
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
