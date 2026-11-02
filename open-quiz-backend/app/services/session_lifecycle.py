"""Session lifecycle: when a quiz session ends and what ending it does.

A session finishes when its time runs out or when no present participant can
still answer; finishing an exam computes its final scores. Before an exam
opens, running trainings on its banks are discarded, since training answers
reveal the correction; a student's unfinished trainings and a whole makeup
session can be discarded the same way.
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.database import affected_rows
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    MakeupSessionSelection,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    Student,
    StudentAccount,
    User,
)
from app.quiz_session_records import (
    delete_quiz_session_records,
    release_join_codes,
)
from app.services.grading import (
    compute_final_scores,
)
from app.session_status import ACTIVE_SESSION_STATUSES


def as_utc(value: datetime) -> datetime:
    """Read a naive timestamp, as legacy rows may hold, as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def quiz_ends_at(quiz_session: QuizSession, quiz: Quiz) -> datetime | None:
    started_at = quiz_session.started_at
    if started_at is None:
        return None
    started_at = as_utc(started_at)
    paused_duration = quiz_session.paused_duration_seconds or 0
    if quiz_session.status == "paused" and quiz_session.paused_at is not None:
        paused_at = as_utc(quiz_session.paused_at)
        paused_duration += ceil(max(0, (datetime.now(UTC) - paused_at).total_seconds()))
    duration_seconds = quiz_session.duration_seconds
    if duration_seconds is None:
        duration_seconds = quiz.duration_seconds
    return started_at + timedelta(seconds=duration_seconds + paused_duration)


def answer_review_enabled(quiz_session: QuizSession, quiz: Quiz) -> bool:
    """Whether participants must confirm their answers before finishing.

    Only exams offer the final review step, and a running session keeps the
    option it was launched with even if the quiz is edited afterwards.
    """
    if quiz.mode != "exam":
        return False
    if quiz_session.allow_answer_review is not None:
        return quiz_session.allow_answer_review
    return quiz.allow_answer_review


def expire_quiz_session(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: Session,
) -> None:
    ends_at = quiz_ends_at(quiz_session, quiz)
    if (
        quiz_session.status == "in_progress"
        and ends_at is not None
        and datetime.now(UTC) >= ends_at
    ):
        transition = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status == "in_progress",
            )
            .values(status="finished")
            .execution_options(synchronize_session=False)
        )
        if affected_rows(transition) != 1:
            session.rollback()
            session.refresh(quiz_session)
            return
        session.refresh(quiz_session)
        for participant in session.scalars(
            select(QuizParticipant).where(QuizParticipant.session_id == quiz_session.id)
        ):
            participant.current_position = None
        if quiz.mode == "exam":
            compute_final_scores(quiz_session, session)
        session.commit()


def finish_when_nobody_can_answer(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: Session,
) -> None:
    """End a running session once no present participant can still answer.

    A participant who left keeps their position so that rejoining resumes
    where they stopped, but they must not hold the session open: the teacher
    no longer sees them among the participants either. Submitting the last
    answer and being the last to leave both empty that set, so both paths
    call this.

    A session where nobody ever answered is left running: there is nothing to
    grade, and finishing it would deny the rejoin its students still need.
    """
    if quiz_session.status != "in_progress":
        return
    answered = session.scalar(
        select(QuizAnswer.id).where(QuizAnswer.session_id == quiz_session.id).limit(1)
    )
    if answered is None:
        return
    still_working: ColumnElement[bool] = QuizParticipant.current_position.is_not(None)
    if answer_review_enabled(quiz_session, quiz):
        # The last answer no longer ends the session on its own: a participant
        # reviewing their answers still has to confirm them.
        still_working = or_(still_working, QuizParticipant.submitted_at.is_(None))
    unfinished_count = session.scalar(
        select(func.count(QuizParticipant.id)).where(
            QuizParticipant.session_id == quiz_session.id,
            still_working,
            QuizParticipant.left_at.is_(None),
        )
    )
    if unfinished_count:
        return
    transition = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == "in_progress",
        )
        .values(status="finished")
        .execution_options(synchronize_session=False)
    )
    if affected_rows(transition) == 1:
        quiz_session.status = "finished"
        if quiz.mode == "exam":
            compute_final_scores(quiz_session, session)


def expire_owned_quiz_sessions(
    professor: User,
    session: Session,
) -> None:
    rows = list(
        session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.status == "in_progress",
            )
        )
    )
    for quiz_session, quiz in rows:
        expire_quiz_session(quiz_session, quiz, session)


def delete_makeup_session_records(
    makeup_session_id: int,
    session: Session,
) -> None:
    child_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                QuizSession.makeup_session_id == makeup_session_id
            )
        )
    )
    delete_quiz_session_records(child_ids, session)
    makeup_join_code = session.scalar(
        select(MakeupSession.join_code).where(MakeupSession.id == makeup_session_id)
    )
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.session_id == makeup_session_id
        )
    )
    session.execute(
        delete(MakeupSessionQuiz).where(
            MakeupSessionQuiz.session_id == makeup_session_id
        )
    )
    session.execute(delete(MakeupSession).where(MakeupSession.id == makeup_session_id))
    release_join_codes([makeup_join_code] if makeup_join_code else [], session)


def discard_previous_training_sessions(
    student: StudentAccount,
    membership: Student,
    session: Session,
) -> None:
    session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                Quiz.owner_id == student.owner_id,
                Quiz.mode == "training",
                QuizSession.status != "finished",
                or_(
                    QuizParticipant.student_id == membership.id,
                    QuizParticipant.student_identifier == student.identifier,
                ),
            )
        )
    )
    delete_quiz_session_records(session_ids, session)


def discard_active_training_sessions(
    student_ids: Iterable[int] | Select,
    bank_ids: Iterable[int],
    session: Session,
) -> None:
    """Remove running trainings on an exam's banks before the exam opens.

    Training answers reveal the expected answer, so a training session left
    open on one of the exam's banks would let its student consult the
    correction while sitting the exam.
    """
    active_training_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                QuizParticipant.student_id.in_(student_ids),
                QuizSession.training_question_bank_id.in_(bank_ids),
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
    )
    delete_quiz_session_records(active_training_ids, session)


def active_exam_bank_ids_for_class(class_id: int, session: Session) -> set[int]:
    return set(
        session.scalars(
            select(QuizQuestionBank.question_bank_id)
            .join(
                QuizSession,
                QuizSession.quiz_id == QuizQuestionBank.quiz_id,
            )
            .where(
                QuizSession.class_id == class_id,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
    )
