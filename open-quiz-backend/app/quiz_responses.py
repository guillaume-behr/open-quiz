"""Response bodies describing quizzes to their teacher."""

from sqlalchemy import case, func, select

from app.dependencies import DbSession
from app.enums import Difficulty
from app.models import Question, QuestionBank, Quiz, QuizQuestionBank
from app.schemas import QuizBankSummary, QuizResponse


def quiz_responses(quizzes: list[Quiz], session: DbSession) -> list[QuizResponse]:
    if not quizzes:
        return []
    banks_by_quiz: dict[int, list[QuizBankSummary]] = {quiz.id: [] for quiz in quizzes}
    rows = session.execute(
        select(
            QuizQuestionBank.quiz_id,
            QuestionBank,
            func.count(Question.id),
            func.sum(case((Question.difficulty == Difficulty.EASY, 1), else_=0)),
            func.sum(case((Question.difficulty == Difficulty.MEDIUM, 1), else_=0)),
            func.sum(case((Question.difficulty == Difficulty.HARD, 1), else_=0)),
        )
        .join(
            QuizQuestionBank,
            QuizQuestionBank.question_bank_id == QuestionBank.id,
        )
        .outerjoin(Question, Question.question_bank_id == QuestionBank.id)
        .where(QuizQuestionBank.quiz_id.in_(banks_by_quiz))
        .group_by(QuizQuestionBank.quiz_id, QuestionBank.id)
        .order_by(
            QuizQuestionBank.quiz_id,
            QuestionBank.grade_level,
            QuestionBank.chapter,
        )
    )
    for quiz_id, bank, count, easy_count, medium_count, hard_count in rows:
        banks_by_quiz[quiz_id].append(
            QuizBankSummary(
                id=bank.id,
                grade_level=bank.grade_level,
                chapter=bank.chapter,
                question_count=count,
                easy_question_count=easy_count or 0,
                medium_question_count=medium_count or 0,
                hard_question_count=hard_count or 0,
            )
        )
    return [
        QuizResponse(
            id=quiz.id,
            mode=quiz.mode,
            title=quiz.title,
            source_language=quiz.source_language,
            question_count=quiz.question_count,
            duration_seconds=quiz.duration_seconds,
            allow_previous_questions=quiz.allow_previous_questions,
            allow_answer_review=quiz.allow_answer_review,
            show_provisional_grades=quiz.show_provisional_grades,
            allow_negative_points=quiz.allow_negative_points,
            same_questions_for_all=quiz.same_questions_for_all,
            easy_question_count=quiz.easy_question_count,
            medium_question_count=quiz.medium_question_count,
            hard_question_count=quiz.hard_question_count,
            question_banks=banks_by_quiz[quiz.id],
            created_at=quiz.created_at,
        )
        for quiz in quizzes
    ]
