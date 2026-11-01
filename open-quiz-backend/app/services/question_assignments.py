"""Question assignments: which questions a participant answers, in which order.

A session either gives every participant the same questions
(QuizSessionQuestion) or draws them per participant
(QuizSessionStudentQuestion), keyed by student and by student identifier,
which still matches when no student is linked to the participant. These
functions resolve that ordering and the participant's position in it.
"""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)


def session_question_ids(
    quiz_session: QuizSession,
    session: Session,
    participant: QuizParticipant,
) -> list[int]:
    if participant.student_id is not None:
        personalized_ids = list(
            session.scalars(
                select(QuizSessionStudentQuestion.question_id)
                .where(
                    QuizSessionStudentQuestion.session_id == quiz_session.id,
                    QuizSessionStudentQuestion.student_id == participant.student_id,
                )
                .order_by(QuizSessionStudentQuestion.position)
            )
        )
        if personalized_ids:
            return personalized_ids
    personalized_ids = list(
        session.scalars(
            select(QuizSessionStudentQuestion.question_id)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_identifier
                == participant.student_identifier,
            )
            .order_by(QuizSessionStudentQuestion.position)
        )
    )
    if personalized_ids:
        return personalized_ids
    return list(
        session.scalars(
            select(QuizSessionQuestion.question_id)
            .where(QuizSessionQuestion.session_id == quiz_session.id)
            .order_by(QuizSessionQuestion.position)
        )
    )


def load_session_question_assignments(
    session_ids: list[int],
    session: Session,
) -> tuple[
    dict[int, list[int]],
    dict[tuple[int, int], list[int]],
    dict[tuple[int, str], list[int]],
]:
    """Load common and personalized question ordering for several sessions."""
    common_by_session: dict[int, list[int]] = defaultdict(list)
    for session_id, question_id in session.execute(
        select(
            QuizSessionQuestion.session_id,
            QuizSessionQuestion.question_id,
        )
        .where(QuizSessionQuestion.session_id.in_(session_ids))
        .order_by(QuizSessionQuestion.session_id, QuizSessionQuestion.position)
    ):
        common_by_session[session_id].append(question_id)

    personalized_by_student: dict[tuple[int, int], list[int]] = defaultdict(list)
    personalized_by_identifier: dict[tuple[int, str], list[int]] = defaultdict(list)
    for session_id, student_id, student_identifier, question_id in session.execute(
        select(
            QuizSessionStudentQuestion.session_id,
            QuizSessionStudentQuestion.student_id,
            QuizSessionStudentQuestion.student_identifier,
            QuizSessionStudentQuestion.question_id,
        )
        .where(QuizSessionStudentQuestion.session_id.in_(session_ids))
        .order_by(
            QuizSessionStudentQuestion.session_id,
            QuizSessionStudentQuestion.student_identifier,
            QuizSessionStudentQuestion.position,
        )
    ):
        if student_id is not None:
            personalized_by_student[(session_id, student_id)].append(question_id)
        personalized_by_identifier[(session_id, student_identifier)].append(question_id)
    return (
        common_by_session,
        personalized_by_student,
        personalized_by_identifier,
    )


def assigned_question_ids(
    session_id: int,
    student_id: int | None,
    student_identifier: str,
    common_by_session: dict[int, list[int]],
    personalized_by_student: dict[tuple[int, int], list[int]],
    personalized_by_identifier: dict[tuple[int, str], list[int]],
) -> list[int]:
    personalized_ids = (
        personalized_by_student.get((session_id, student_id), [])
        if student_id is not None
        else []
    )
    return personalized_ids or personalized_by_identifier.get(
        (session_id, student_identifier), common_by_session[session_id]
    )


def current_question_id(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: Session,
) -> int | None:
    if (
        quiz_session.status not in ("in_progress", "paused")
        or participant.current_position is None
    ):
        return None
    question_ids = session_question_ids(quiz_session, session, participant)
    if participant.current_position >= len(question_ids):
        return None
    return question_ids[participant.current_position]


def last_answered_question_id(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: Session,
) -> int | None:
    """The final question once a participant has answered everything.

    A concurrent duplicate of the last answer can reach the server after the
    winning request already advanced the participant past it, and even after
    it finished the whole session (finish_when_nobody_can_answer runs in the
    same transaction). The caller uses this to recognise that submission
    instead of rejecting it outright.
    """
    if (
        quiz_session.status not in ("in_progress", "finished")
        or participant.current_position is not None
    ):
        return None
    question_ids = session_question_ids(quiz_session, session, participant)
    return question_ids[-1] if question_ids else None


def session_question_count(quiz_session: QuizSession, session: Session) -> int:
    common_count = session.scalar(
        select(func.count(QuizSessionQuestion.question_id)).where(
            QuizSessionQuestion.session_id == quiz_session.id
        )
    )
    if common_count:
        return common_count
    personalized_count = session.scalar(
        select(func.count(QuizSessionStudentQuestion.question_id))
        .where(QuizSessionStudentQuestion.session_id == quiz_session.id)
        .group_by(QuizSessionStudentQuestion.student_identifier)
        .limit(1)
    )
    return personalized_count or 0


def accessible_question_positions(
    question_ids: list[int],
    answered_question_ids: set[int],
    current_position: int | None,
) -> set[int]:
    """Positions a participant may reach: answered ones, the next, the current."""
    positions = {
        position
        for position, question_id in enumerate(question_ids)
        if question_id in answered_question_ids
    }
    if positions:
        next_position = max(positions) + 1
        if next_position < len(question_ids):
            positions.add(next_position)
    if current_position is not None:
        positions.add(current_position)
    return positions
