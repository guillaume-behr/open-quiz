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
        try:
            submitted = json.loads(answer.answer_data)
        except TypeError, ValueError:
            submitted = {}
        if question is None:
            answer.score = 0
            answer.is_graded = True
        elif question.answer_mode == "written":
            if not answer.is_graded:
                answer.score = 0
        else:
            selected_ids = set(
                submitted.get("selected_choice_ids", [])
                if isinstance(submitted, dict)
                else []
            )
            score = sum(
                choice.points
                for choice in choices
                if choice.id in selected_ids
                and (quiz_session.allow_negative_points or choice.points >= 0)
            )
            answer.score = round(score, 2)
            answer.is_graded = True
