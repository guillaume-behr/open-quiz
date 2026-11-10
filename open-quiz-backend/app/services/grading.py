"""Grading: how an answer scores and the best score a question allows.

selected_choice_score is the single scoring rule for choice questions;
question_maximum_scores derives each question's reachable maximum from that
same rule, compute_final_scores applies it to every answer of a session,
regrade_question applies it to every unpublished answer to one edited
question, and training_result totals a training attempt.
"""

import json
from collections import defaultdict

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.orm import Session

from app.enums import AnswerMode, SessionStatus
from app.models import (
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)
from app.question_responses import load_question_records
from app.services.question_assignments import session_question_ids


def selected_choice_score(
    choices: list[QuestionChoice],
    selected_ids: set[int],
    *,
    allow_negative_points: bool,
) -> float:
    """Score one answer, never paying for a selection wider than the key.

    Picking an incorrect choice has to cost something, or ticking every box
    collects every positive point and scores full marks without reading the
    question. Without negative points nothing can express that cost, so any
    incorrect choice zeroes the question.

    Enabling negative points must not weaken that. A choice the teacher gave a
    negative value carries its own penalty and is charged as written; one still
    sitting at zero or above carries none — the editor defaults distractors to
    zero — so it falls back to the same rule rather than being free.
    """
    selected = [choice for choice in choices if choice.id in selected_ids]
    if any(
        not choice.is_correct and (not allow_negative_points or choice.points >= 0)
        for choice in selected
    ):
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
    """Read a stored answer payload, treating an unreadable one as empty.

    The answer route only stores JSON objects, so this is a safeguard against
    rows changed outside the application, such as a hand-edited database or a
    damaged backup: scoring that session must not fail on one bad row.
    """
    return decoded_answer_payload(answer.answer_data)


def decoded_answer_payload(answer_data: str) -> dict:
    try:
        submitted = json.loads(answer_data)
    except TypeError, ValueError:
        return {}
    return submitted if isinstance(submitted, dict) else {}


def selected_choice_ids(answer: QuizAnswer) -> set[int]:
    return stored_choice_ids(answer.answer_data)


def stored_choice_ids(answer_data: str) -> set[int]:
    """Choice ids of a stored answer, ignoring any entry that is not an id.

    The answer route validates every id as an integer before storing it, so
    this only matters for a row changed outside the application. Such a row
    could hold nested lists or objects, which are unhashable, or booleans,
    which would compare equal to ids 0 and 1.
    """
    selected = decoded_answer_payload(answer_data).get("selected_choice_ids")
    if not isinstance(selected, list):
        return set()
    return {
        choice_id
        for choice_id in selected
        if isinstance(choice_id, int) and not isinstance(choice_id, bool)
    }


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
        elif question.answer_mode == AnswerMode.WRITTEN:
            if not answer.is_graded:
                answer.score = 0
        else:
            answer.score = selected_choice_score(
                choices,
                selected_choice_ids(answer),
                allow_negative_points=bool(quiz_session.allow_negative_points),
            )
            answer.is_graded = True


def regrade_question(
    question: Question,
    choices: list[QuestionChoice],
    session: Session,
) -> None:
    """Rescore the answers to one edited question, in one read and one write.

    Only finished sessions whose grades are not published yet are rescored:
    published marks never change as a side effect of an edit. Each answer is
    scored with the same rule compute_final_scores applies, but only this
    question's answers are touched, so the cost follows the number of answers
    rather than one round of queries per session.
    """
    rows = session.execute(
        select(
            QuizAnswer.id,
            QuizAnswer.answer_data,
            QuizAnswer.is_graded,
            QuizSession.allow_negative_points,
        )
        .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
        .where(
            QuizAnswer.question_id == question.id,
            QuizSession.status == SessionStatus.FINISHED,
            QuizSession.grades_published_at.is_(None),
        )
    ).all()
    if question.answer_mode == AnswerMode.WRITTEN:
        # A written answer keeps the mark a teacher gave it; one still waiting
        # for a mark counts as zero, as compute_final_scores does.
        changes = [
            {"id": answer_id, "score": 0.0, "is_graded": False}
            for answer_id, _, is_graded, _ in rows
            if not is_graded
        ]
    else:
        changes = [
            {
                "id": answer_id,
                "score": selected_choice_score(
                    choices,
                    stored_choice_ids(answer_data),
                    allow_negative_points=bool(allow_negative_points),
                ),
                "is_graded": True,
            }
            for answer_id, answer_data, _, allow_negative_points in rows
        ]
    if changes:
        # ORM bulk UPDATE by primary key: a single executemany.
        session.execute(update(QuizAnswer), changes)


def question_maximum_scores(
    question_ids: list[int],
    session: Session,
) -> dict[int, float]:
    """Best score a participant can actually reach on each question.

    This has to follow the same rule as selected_choice_score, where selecting
    an incorrect choice either zeroes the question or subtracts. Answering the
    key exactly is therefore the best any selection can do, in both negative
    and non-negative point modes, so the ceiling does not depend on the mode.
    Counting distractors would report a ceiling nobody can reach.
    """
    if not question_ids:
        return {}
    positive_points = case(
        (
            and_(QuestionChoice.is_correct.is_(True), QuestionChoice.points > 0),
            QuestionChoice.points,
        ),
        else_=0,
    )
    maximums = {
        question_id: float(maximum or 0)
        for question_id, maximum in session.execute(
            select(
                QuestionChoice.question_id,
                case(
                    (
                        Question.answer_mode == AnswerMode.SINGLE,
                        func.max(positive_points),
                    ),
                    else_=func.sum(positive_points),
                ),
            )
            .join(Question, Question.id == QuestionChoice.question_id)
            .where(QuestionChoice.question_id.in_(question_ids))
            .group_by(QuestionChoice.question_id, Question.answer_mode)
        )
    }
    return {question_id: maximums.get(question_id, 0) for question_id in question_ids}


def participant_maximum_scores(
    quiz_session: QuizSession,
    participants: list[QuizParticipant],
    session: Session,
) -> dict[int, float]:
    if not participants:
        return {}

    # Load assignments and choice totals once for the whole session. Calling
    # session_question_points for every participant made result polling issue
    # two or three additional queries per student, which quickly overwhelmed
    # the database for full classrooms.
    personalized_by_student: dict[int, list[int]] = defaultdict(list)
    personalized_by_identifier: dict[str, list[int]] = defaultdict(list)
    personalized_rows = list(
        session.execute(
            select(
                QuizSessionStudentQuestion.student_id,
                QuizSessionStudentQuestion.student_identifier,
                QuizSessionStudentQuestion.question_id,
            )
            .where(QuizSessionStudentQuestion.session_id == quiz_session.id)
            .order_by(QuizSessionStudentQuestion.position)
        )
    )
    for student_id, student_identifier, question_id in personalized_rows:
        if student_id is not None:
            personalized_by_student[student_id].append(question_id)
        personalized_by_identifier[student_identifier].append(question_id)

    common_question_ids = list(
        session.scalars(
            select(QuizSessionQuestion.question_id)
            .where(QuizSessionQuestion.session_id == quiz_session.id)
            .order_by(QuizSessionQuestion.position)
        )
    )
    used_question_ids = set(common_question_ids)
    used_question_ids.update(row.question_id for row in personalized_rows)
    maximums = question_maximum_scores(list(used_question_ids), session)

    result: dict[int, float] = {}
    for participant in participants:
        question_ids = (
            personalized_by_student.get(participant.student_id, [])
            if participant.student_id is not None
            else []
        )
        if not question_ids:
            question_ids = personalized_by_identifier.get(
                participant.student_identifier, common_question_ids
            )
        result[participant.id] = round(
            sum(float(maximums.get(question_id) or 0) for question_id in question_ids),
            2,
        )
    return result


def session_question_points(
    quiz_session: QuizSession,
    session: Session,
    participant: QuizParticipant,
) -> dict[int, float]:
    question_ids = session_question_ids(quiz_session, session, participant)
    return question_maximum_scores(question_ids, session)


def training_result(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: Session,
) -> tuple[float, float, int]:
    question_ids = session_question_ids(quiz_session, session, participant)
    if not question_ids:
        return 0.0, 0.0, 0
    questions, choices_by_question = load_question_records(question_ids, session)
    answers = {
        answer.question_id: answer
        for answer in session.scalars(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    }
    score = 0.0
    maximum = 0.0
    pending = 0
    maximums = question_maximum_scores(question_ids, session)
    for question_id in question_ids:
        question = questions.get(question_id)
        if question is None:
            continue
        if question.answer_mode == AnswerMode.WRITTEN:
            if question_id in answers:
                pending += 1
            continue
        choices = choices_by_question[question_id]
        maximum += maximums.get(question_id, 0)
        answer = answers.get(question_id)
        if answer is None:
            continue
        selected_ids = selected_choice_ids(answer)
        score += selected_choice_score(
            choices,
            selected_ids,
            allow_negative_points=False,
        )
    return round(score, 2), round(maximum, 2), pending
