"""Question draws: which questions each participant of a quiz receives.

A quiz asks for a number of questions per difficulty from its banks; every
participant draws that many at random, distinct from the other participants'
draws while unused combinations remain. Training draws a shuffled bank.

The functions take a SQLAlchemy session and raise InsufficientQuestionsError
rather than an HTTP error, so they can be used and tested without FastAPI.
"""

from math import comb
from random import SystemRandom

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Question, Quiz, QuizQuestionBank
from app.schemas import QuizCreate

randomizer = SystemRandom()
MAX_TRAINING_QUESTIONS = 200


class InsufficientQuestionsError(Exception):
    """The banks hold fewer questions of a difficulty than the quiz requests."""

    def __init__(self) -> None:
        super().__init__(
            "Nombre de questions insuffisant pour une ou plusieurs difficultés "
            "dans les banques sélectionnées"
        )


def difficulty_counts(payload: Quiz | QuizCreate) -> dict[str, int]:
    return {
        "easy": payload.easy_question_count,
        "medium": payload.medium_question_count,
        "hard": payload.hard_question_count,
    }


def quiz_bank_ids(quiz_id: int, session: Session) -> list[int]:
    return list(
        session.scalars(
            select(QuizQuestionBank.question_bank_id).where(
                QuizQuestionBank.quiz_id == quiz_id
            )
        )
    )


def available_difficulty_counts(
    bank_ids: list[int],
    session: Session,
) -> dict[str, int]:
    return dict(
        session.execute(
            select(Question.difficulty, func.count(Question.id))
            .where(Question.question_bank_id.in_(bank_ids))
            .group_by(Question.difficulty)
        ).all()
    )


def difficulty_counts_for_banks(
    payload: Quiz | QuizCreate,
    bank_ids: list[int],
    session: Session,
) -> dict[str, int]:
    available = available_difficulty_counts(bank_ids, session)
    requested = difficulty_counts(payload)
    unavailable = [
        difficulty
        for difficulty, count in requested.items()
        if count > available.get(difficulty, 0)
    ]
    if unavailable:
        raise InsufficientQuestionsError()
    return requested


class QuestionDrawPool:
    """The candidate questions for one quiz, loaded once per launch.

    Every student in a launch draws from the same pool, so reading it once
    keeps a launch at a constant number of queries instead of a handful per
    student per attempt.
    """

    def __init__(self, requested: dict[str, int], candidates: dict[str, list[int]]):
        self.requested = requested
        self.candidates = candidates

    @property
    def possible_combination_count(self) -> int:
        total = 1
        for difficulty, count in self.requested.items():
            total *= comb(len(self.candidates.get(difficulty, ())), count)
        return total

    def draw(self) -> list[int]:
        selected_ids: list[int] = []
        for difficulty, count in self.requested.items():
            if count > 0:
                selected_ids.extend(
                    randomizer.sample(self.candidates[difficulty], count)
                )
        randomizer.shuffle(selected_ids)
        return selected_ids


def question_draw_pool(quiz: Quiz, session: Session) -> QuestionDrawPool:
    bank_ids = quiz_bank_ids(quiz.id, session)
    requested = difficulty_counts_for_banks(quiz, bank_ids, session)
    candidates = {
        difficulty: list(
            session.scalars(
                select(Question.id).where(
                    Question.question_bank_id.in_(bank_ids),
                    Question.difficulty == difficulty,
                )
            )
        )
        for difficulty, count in requested.items()
        if count > 0
    }
    return QuestionDrawPool(requested, candidates)


def draw_question_ids(quiz: Quiz, session: Session) -> list[int]:
    return question_draw_pool(quiz, session).draw()


def draw_unique_question_ids(
    pool: QuestionDrawPool,
    used_draws: set[tuple[int, ...]],
) -> list[int]:
    # Once every distinct combination is taken, retrying can only fail, so stop
    # searching and let students share a draw.
    if used_draws and len(used_draws) >= pool.possible_combination_count:
        return pool.draw()

    for _ in range(200):
        question_ids = pool.draw()
        signature = tuple(sorted(question_ids))
        if signature not in used_draws:
            used_draws.add(signature)
            return question_ids
    # If the banks contain only one possible combination, every student still
    # receives an independent draw even though the resulting sets must match.
    return pool.draw()


def draw_training_question_ids(bank_id: int, session: Session) -> list[int]:
    question_ids = list(
        session.scalars(select(Question.id).where(Question.question_bank_id == bank_id))
    )
    randomizer.shuffle(question_ids)
    return question_ids[:MAX_TRAINING_QUESTIONS]
