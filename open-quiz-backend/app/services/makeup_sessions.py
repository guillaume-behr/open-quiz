"""Make-up sessions: their state machine, and each student's choice of quiz.

The teacher offers some of the quizzes the class has finished; each student
joins with the code, picks one of them and answers it in a child QuizSession
of their own.
"""

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil

from fastapi import Request, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.database import affected_rows
from app.core.errors import ApiError, ErrorCode
from app.enums import SessionStatus
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    MakeupSessionSelection,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
)
from app.schemas.quizzes import MakeupQuizSelection
from app.services.participants import enforce_public_rate_limit, generate_join_code
from app.services.question_draws import draw_unique_question_ids, question_draw_pool
from app.services.session_lifecycle import delete_makeup_session_records, finish_session


class MakeupAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    FINISH = "finish"
    CANCEL = "cancel"


# The statuses each action accepts, and the one it leads to. A paused make-up
# can be finished directly: resuming it first would restart every clock.
MAKEUP_TRANSITIONS: dict[
    MakeupAction, tuple[tuple[SessionStatus, ...], SessionStatus]
] = {
    MakeupAction.START: ((SessionStatus.WAITING,), SessionStatus.IN_PROGRESS),
    MakeupAction.PAUSE: ((SessionStatus.IN_PROGRESS,), SessionStatus.PAUSED),
    MakeupAction.RESUME: ((SessionStatus.PAUSED,), SessionStatus.IN_PROGRESS),
    MakeupAction.FINISH: (
        (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED),
        SessionStatus.FINISHED,
    ),
}


# Cancelling deletes the make-up session instead of changing its status.
CANCELLABLE_STATUSES = (SessionStatus.WAITING,)


def class_finished_quiz_ids(
    student_class_id: int, owner_id: int, session: Session
) -> set[int]:
    """Quizzes for which the class already completed an exam session."""
    return set(
        session.scalars(
            select(QuizSession.quiz_id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == owner_id,
                QuizSession.class_id == student_class_id,
                QuizSession.status == SessionStatus.FINISHED,
            )
        )
    )


def apply_makeup_action(
    child: QuizSession,
    quiz: Quiz,
    action: MakeupAction,
    now: datetime,
    session: Session,
) -> None:
    """Carry a makeup action over to one student's quiz session.

    Pausing and resuming only apply if the child is still in the status they
    were checked against, so a child that finished meanwhile stays finished.
    """
    if action == MakeupAction.START:
        if child.status != SessionStatus.WAITING:
            return
        child.status = SessionStatus.IN_PROGRESS
        child.started_at = now
        for participant in session.scalars(
            select(QuizParticipant).where(QuizParticipant.session_id == child.id)
        ):
            participant.current_position = 0
    elif action == MakeupAction.PAUSE:
        if child.status != SessionStatus.IN_PROGRESS:
            return
        session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == child.id,
                QuizSession.status == SessionStatus.IN_PROGRESS,
            )
            .values(status=SessionStatus.PAUSED, paused_at=now)
            .execution_options(synchronize_session=False)
        )
        session.refresh(child)
    elif action == MakeupAction.RESUME:
        if child.status != SessionStatus.PAUSED or child.paused_at is None:
            return
        session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == child.id,
                QuizSession.status == SessionStatus.PAUSED,
                QuizSession.paused_at == child.paused_at,
            )
            .values(
                status=SessionStatus.IN_PROGRESS,
                paused_at=None,
                paused_duration_seconds=(child.paused_duration_seconds or 0)
                + ceil(max(0, (now - child.paused_at).total_seconds())),
            )
            .execution_options(synchronize_session=False)
        )
        session.refresh(child)
    else:  # finish
        finish_session(
            child,
            quiz,
            session,
            from_statuses=(SessionStatus.IN_PROGRESS, SessionStatus.PAUSED),
        )


def chosen_makeup_quiz(
    join_code: str,
    payload: MakeupQuizSelection,
    account: StudentAccount,
    request: Request,
    session: Session,
) -> tuple[MakeupSession, Student, Quiz]:
    """The open makeup session, the student's place in it and the quiz chosen."""
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == join_code.strip().upper(),
            MakeupSession.status == SessionStatus.WAITING,
        )
    )
    if makeup is None:
        enforce_public_rate_limit(
            request,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_SELECTION_CLOSED,
            "Ce rattrapage n’accepte plus de choix",
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    quiz = session.scalar(
        select(Quiz)
        .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
        .where(
            MakeupSessionQuiz.session_id == makeup.id,
            Quiz.id == payload.quiz_id,
        )
    )
    existing = session.scalar(
        select(QuizSession.id)
        .join(QuizParticipant, QuizParticipant.session_id == QuizSession.id)
        .where(
            QuizSession.makeup_session_id == makeup.id,
            QuizParticipant.student_id == (membership.id if membership else -1),
        )
    )
    if membership is None or quiz is None or existing is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_SELECTION_INVALID,
            "Sélection de quiz invalide",
        )
    return makeup, membership, quiz


def student_makeup_child(
    makeup: MakeupSession, account: StudentAccount, session: Session
) -> QuizSession | None:
    """The quiz session a student account chose in a make-up, if any."""
    return session.scalar(
        select(QuizSession)
        .join(QuizParticipant, QuizParticipant.session_id == QuizSession.id)
        .join(Student, Student.id == QuizParticipant.student_id)
        .where(
            QuizSession.makeup_session_id == makeup.id,
            Student.account_id == account.id,
            Student.class_id == makeup.class_id,
        )
        .limit(1)
    )


def claim_makeup_selection(
    makeup: MakeupSession, membership: Student, session: Session
) -> None:
    """Record the student's one choice, refusing a second or a late one."""
    waiting = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == SessionStatus.WAITING,
        )
        .values(status=SessionStatus.WAITING)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(waiting) != 1:
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_SELECTION_CLOSED,
            "Ce rattrapage n’accepte plus de choix",
        )
    claimed_student_id = session.scalar(
        insert(MakeupSessionSelection)
        .values(session_id=makeup.id, student_id=membership.id)
        .on_conflict_do_nothing(
            index_elements=[
                MakeupSessionSelection.session_id,
                MakeupSessionSelection.student_id,
            ]
        )
        .returning(MakeupSessionSelection.student_id)
    )
    if claimed_student_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_SELECTION_INVALID,
            "Sélection de quiz invalide",
        )


def makeup_child_session(
    makeup: MakeupSession, quiz: Quiz, session: Session
) -> QuizSession:
    """The student's own session of the quiz they chose."""
    child = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_answer_review=quiz.allow_answer_review,
        show_provisional_grades=quiz.show_provisional_grades,
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=False,
        class_id=makeup.class_id,
        class_name=makeup.class_name,
        join_code=generate_join_code(session),
        status=SessionStatus.WAITING,
        makeup_session_id=makeup.id,
    )
    session.add(child)
    session.flush()
    return child


def draw_makeup_questions(
    child: QuizSession,
    makeup: MakeupSession,
    quiz: Quiz,
    membership: Student,
    session: Session,
) -> None:
    """Draw questions no other student of this makeup got for the same quiz."""
    existing_draw_rows = list(
        session.execute(
            select(
                QuizSessionStudentQuestion.session_id,
                QuizSessionStudentQuestion.question_id,
            )
            .join(
                QuizSession,
                QuizSession.id == QuizSessionStudentQuestion.session_id,
            )
            .where(
                QuizSession.makeup_session_id == makeup.id,
                QuizSession.quiz_id == quiz.id,
            )
        )
    )
    questions_by_session: dict[int, list[int]] = defaultdict(list)
    for existing_session_id, question_id in existing_draw_rows:
        questions_by_session[existing_session_id].append(question_id)
    used_draws = {
        tuple(sorted(question_ids)) for question_ids in questions_by_session.values()
    }
    question_ids = draw_unique_question_ids(
        question_draw_pool(quiz, session), used_draws
    )
    session.add_all(
        QuizSessionStudentQuestion(
            session_id=child.id,
            student_id=membership.id,
            student_identifier=membership.identifier,
            question_id=question_id,
            position=position,
        )
        for position, question_id in enumerate(question_ids)
    )


def delete_unanswered_makeup_session(makeup: MakeupSession, session: Session) -> None:
    """Delete a makeup session nobody has answered in yet."""
    has_answers = (
        session.scalar(
            select(QuizAnswer.id)
            .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
            .where(QuizSession.makeup_session_id == makeup.id)
            .limit(1)
        )
        is not None
    )
    if has_answers:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_HAS_ANSWERS,
            "Impossible d’annuler ce rattrapage car des réponses ont déjà "
            "été enregistrées",
        )
    delete_makeup_session_records(makeup.id, session)


def transition_makeup_session(
    makeup: MakeupSession,
    action: MakeupAction,
    session: Session,
) -> list[QuizSession]:
    """Move the make-up session and its students' sessions on, uncommitted.

    Returns the students' sessions, whose live views the caller updates once
    committed.
    """
    expected, target = MAKEUP_TRANSITIONS[action]
    transition = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status.in_(expected),
        )
        .values(status=target)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(transition) != 1:
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_ACTION_NOT_ALLOWED,
            "Action impossible pour cette session",
        )
    makeup.status = target
    children = [
        (child, quiz)
        for child, quiz in session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(QuizSession.makeup_session_id == makeup.id)
        )
    ]
    if action == MakeupAction.START and not children:
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.MAKEUP_NO_SELECTION,
            "Au moins un élève doit choisir un quiz avant le démarrage",
        )
    now = datetime.now(UTC)
    for child, quiz in children:
        apply_makeup_action(child, quiz, action, now, session)
    return [child for child, _ in children]
