import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
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
    participants = {
        participant.id: participant
        for participant in session.scalars(
            select(QuizParticipant).where(QuizParticipant.session_id == quiz_session.id)
        )
    }
    common_points = dict(
        session.execute(
            select(QuizSessionQuestion.question_id, QuizSessionQuestion.points).where(
                QuizSessionQuestion.session_id == quiz_session.id
            )
        ).all()
    )
    personalized_points_by_student = {
        (student_id, question_id): points
        for student_id, question_id, points in session.execute(
            select(
                QuizSessionStudentQuestion.student_id,
                QuizSessionStudentQuestion.question_id,
                QuizSessionStudentQuestion.points,
            ).where(QuizSessionStudentQuestion.session_id == quiz_session.id)
        )
    }
    personalized_points_by_identifier = {
        (identifier, question_id): points
        for identifier, question_id, points in session.execute(
            select(
                QuizSessionStudentQuestion.student_identifier,
                QuizSessionStudentQuestion.question_id,
                QuizSessionStudentQuestion.points,
            ).where(QuizSessionStudentQuestion.session_id == quiz_session.id)
        )
    }
    for answer in answers:
        question = questions.get(answer.question_id)
        choices = choices_by_question.get(answer.question_id, [])
        submitted = json.loads(answer.answer_data)
        participant = participants.get(answer.participant_id)
        question_points = common_points.get(answer.question_id)
        if participant is not None:
            question_points = personalized_points_by_student.get(
                (participant.student_id, answer.question_id),
                personalized_points_by_identifier.get(
                    (participant.student_identifier, answer.question_id),
                    question_points,
                ),
            )
        if question_points is None:
            question_points = 0.0
        if question is None:
            answer.score = 0
            answer.is_graded = True
        elif question.answer_mode == "written":
            if not answer.is_graded:
                answer.score = 0
        else:
            correct_ids = {choice.id for choice in choices if choice.is_correct}
            selected_ids = set(submitted.get("selected_choice_ids", []))
            answer.score = question_points if selected_ids == correct_ids else 0
            answer.is_graded = True
