"""How a student answered each question, as a teacher or the student reads it."""

from app.enums import AnswerMode
from app.models import (
    Question,
    QuestionChoice,
    QuestionCode,
    QuizAnswer,
)
from app.schemas.student_quizzes import QuizAnswerReview
from app.services.grading import decoded_answer_data


def answer_review(
    answer: QuizAnswer,
    question: Question,
    position: int,
    choices: list[QuestionChoice],
    max_score: float,
    code: QuestionCode | None = None,
) -> QuizAnswerReview:
    submitted = decoded_answer_data(answer)
    choices_by_id = {choice.id: choice for choice in choices}
    if question.answer_mode == AnswerMode.WRITTEN:
        submitted_answers = [str(submitted.get("written_answer", ""))]
        is_correct = (
            answer.score >= max_score if answer.is_graded and max_score > 0 else None
        )
    else:
        submitted_ids = submitted.get("selected_choice_ids", [])
        if not isinstance(submitted_ids, list):
            submitted_ids = []
        # Only real integers can name a choice, and labels are looked up by id.
        submitted_ids = [
            choice_id for choice_id in submitted_ids if type(choice_id) is int
        ]
        submitted_answers = [
            choices_by_id[choice_id].label
            for choice_id in submitted_ids
            if choice_id in choices_by_id
        ]
        is_correct = set(submitted_ids) == {
            choice.id for choice in choices if choice.is_correct
        }
    expected_answers = [choice.label for choice in choices if choice.is_correct]
    return QuizAnswerReview(
        id=answer.id,
        question_id=question.id,
        position=position + 1,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        code_content=code.content if code else None,
        code_language=code.language if code else None,
        response_language=question.response_language,
        submitted_answers=submitted_answers,
        expected_answers=expected_answers,
        score=answer.score,
        max_score=max_score,
        is_graded=answer.is_graded,
        is_correct=is_correct,
        feedback=answer.feedback,
    )


def unanswered_review(
    question: Question,
    position: int,
    choices: list[QuestionChoice],
    max_score: float,
    code: QuestionCode | None = None,
) -> QuizAnswerReview:
    """A question the student was given and never answered: no mark, no row."""
    return QuizAnswerReview(
        id=None,
        question_id=question.id,
        position=position + 1,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        code_content=code.content if code else None,
        code_language=code.language if code else None,
        response_language=question.response_language,
        submitted_answers=[],
        expected_answers=[choice.label for choice in choices if choice.is_correct],
        score=0.0,
        max_score=max_score,
        is_graded=True,
        is_correct=False,
    )
