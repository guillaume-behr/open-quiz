import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizSession,
)


def selected_choice_score(
    choices: list[QuestionChoice],
    selected_ids: set[int],
    *,
    allow_negative_points: bool,
) -> float:
    selected = [choice for choice in choices if choice.id in selected_ids]
    if not allow_negative_points and any(not choice.is_correct for choice in selected):
        # Otherwise selecting every option earns every positive point while
        # wrong zero-point options are silently ignored.
        return 0.0
    return round(
        sum(
            choice.points
            for choice in selected
            if allow_negative_points or choice.points >= 0
        ),
        2,
    )


def decoded_answer_data(answer: QuizAnswer) -> dict:
    """Read a stored answer payload, tolerating any unreadable legacy row."""
    try:
        submitted = json.loads(answer.answer_data)
    except TypeError, ValueError:
        return {}
    return submitted if isinstance(submitted, dict) else {}


def selected_choice_ids(answer: QuizAnswer) -> set[int]:
    selected = decoded_answer_data(answer).get("selected_choice_ids")
    return set(selected) if isinstance(selected, list) else set()


def compute_final_scores(quiz_session: QuizSession, session: Session) -> None:
    answers = list(
        session.scalars(
            select(QuizAnswer).where(QuizAnswer.session_id == quiz_session.id)
        )
    )
    question_ids = {answer.question_id for answer in answers}
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    if question_ids:
        for choice in session.scalars(
            select(QuestionChoice).where(QuestionChoice.question_id.in_(question_ids))
        ):
            choices_by_question[choice.question_id].append(choice)
    questions = {
        question.id: question
        for question in session.scalars(
            select(Question).where(Question.id.in_(question_ids))
        )
    }
    for answer in answers:
        question = questions.get(answer.question_id)
        choices = choices_by_question.get(answer.question_id, [])
        if question is None:
            answer.score = 0
            answer.is_graded = True
        elif question.answer_mode == "written":
            if not answer.is_graded:
                answer.score = 0
        else:
            answer.score = selected_choice_score(
                choices,
                selected_choice_ids(answer),
                allow_negative_points=bool(quiz_session.allow_negative_points),
            )
            answer.is_graded = True
