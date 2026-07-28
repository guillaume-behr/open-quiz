import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizSession,
    QuizSessionQuestion,
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
        submitted = json.loads(answer.answer_data)
        if question is None:
            answer.score = 0
        elif question.answer_mode == "written":
            expected = next((choice for choice in choices if choice.is_correct), None)
            written = str(submitted.get("written_answer", "")).strip()
            answer.score = (
                expected.points
                if expected is not None
                and written.casefold() == expected.label.strip().casefold()
                else 0
            )
        else:
            choices_by_id = {choice.id: choice for choice in choices}
            answer.score = sum(
                choices_by_id[choice_id].points
                for choice_id in submitted.get("selected_choice_ids", [])
                if choice_id in choices_by_id
            )


def recompute_finished_scores_for_question(
    question_id: int,
    session: Session,
) -> None:
    quiz_sessions = list(
        session.scalars(
            select(QuizSession)
            .join(
                QuizSessionQuestion,
                QuizSessionQuestion.session_id == QuizSession.id,
            )
            .where(
                QuizSessionQuestion.question_id == question_id,
                QuizSession.status == "finished",
            )
        )
    )
    for quiz_session in quiz_sessions:
        compute_final_scores(quiz_session, session)
