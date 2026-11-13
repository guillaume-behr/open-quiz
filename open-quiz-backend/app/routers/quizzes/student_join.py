"""Student participation: joining a quiz session, reading it and leaving it.

A student joins with a join code and receives a participant token; with it
they read the session state and leave. A student who lost their token takes
their participation back by joining again.
"""

from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit_event
from app.core.database import affected_rows
from app.core.dependencies import DbSession, current_student
from app.domain.session_status import ACTIVE_SESSION_STATUSES
from app.enums import QuizMode, SessionStatus
from app.live.updates import publish_quiz_update
from app.models import (
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
)
from app.responses.student_sessions import student_state_response
from app.schemas import QuizJoin, StudentQuizJoinResponse, StudentQuizStateResponse
from app.services.participants import (
    SESSION_RESUMED_VIOLATION,
    CurrentParticipant,
    participant_token_hash,
    reject_quiz_join,
)
from app.services.session_lifecycle import (
    finish_when_nobody_can_answer,
    lock_for_participant_write,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def joinable_session(
    payload: QuizJoin,
    account: StudentAccount,
    request: Request,
    session: Session,
) -> tuple[QuizSession, Quiz, Student, str]:
    """The exam a student joins, their place in its class, and its rate subject.

    Every refusal looks the same and counts against the join limit, so the
    answers never tell an unknown code from a session of another class.
    """
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == payload.join_code, Quiz.mode == QuizMode.EXAM)
    ).first()
    if row is None:
        reject_quiz_join(request, f"join:unknown:{account.id}")
    quiz_session, quiz = row
    join_subject = f"join:session:{quiz_session.id}"
    if quiz_session.class_id is None:
        reject_quiz_join(request, join_subject)
    student = session.scalar(
        select(Student).where(
            Student.class_id == quiz_session.class_id,
            Student.account_id == account.id,
        )
    )
    if student is None:
        reject_quiz_join(request, join_subject)
    if quiz_session.same_questions_for_all is False:
        assigned_question_id = session.scalar(
            select(QuizSessionStudentQuestion.question_id)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .limit(1)
        )
        if assigned_question_id is None:
            reject_quiz_join(request, join_subject)
        session.execute(
            update(QuizSessionStudentQuestion)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .values(student_identifier=student.identifier)
        )
    return quiz_session, quiz, student, join_subject


def rejoin_quiz(
    quiz_session: QuizSession,
    quiz: Quiz,
    existing: QuizParticipant,
    student: Student,
    join_subject: str,
    request: Request,
    session: Session,
) -> StudentQuizJoinResponse:
    """Reconnect a participant who left, on a new token."""
    if quiz_session.status not in {
        SessionStatus.WAITING,
        SessionStatus.IN_PROGRESS,
        SessionStatus.PAUSED,
    }:
        reject_quiz_join(request, join_subject)
    if existing.left_at is None:
        return resume_participation(
            quiz_session, quiz, existing, student, join_subject, request, session
        )
    participant_token = token_urlsafe(32)
    active_session = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .values(status=QuizSession.status)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(active_session) != 1:
        session.rollback()
        reject_quiz_join(request, join_subject)
    # Starting a session places only present participants on their first
    # question. Someone who left the waiting room and comes back after the
    # start has no position, which reads as "finished" everywhere: they
    # would see no question and could never answer.
    resume_position = existing.current_position
    if (
        resume_position is None
        and quiz_session.status != SessionStatus.WAITING
        and existing.submitted_at is None
        and session.scalar(
            select(QuizAnswer.id)
            .where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == existing.id,
            )
            .limit(1)
        )
        is None
    ):
        resume_position = 0
    reconnected = session.execute(
        update(QuizParticipant)
        .where(
            QuizParticipant.id == existing.id,
            QuizParticipant.left_at.is_not(None),
        )
        .values(
            access_token_hash=participant_token_hash(participant_token),
            left_at=None,
            current_position=resume_position,
            student_identifier=student.identifier,
            student_display_name=student.display_name,
        )
        .execution_options(synchronize_session=False)
    )
    if affected_rows(reconnected) != 1:
        session.rollback()
        reject_quiz_join(request, join_subject)
    session.commit()
    session.refresh(existing)
    publish_quiz_update(request, quiz_session, session)
    state = student_state_response(quiz_session, quiz, existing, session)
    return StudentQuizJoinResponse(
        **state.model_dump(), participant_token=participant_token
    )


def resume_participation(
    quiz_session: QuizSession,
    quiz: Quiz,
    existing: QuizParticipant,
    student: Student,
    join_subject: str,
    request: Request,
    session: Session,
) -> StudentQuizJoinResponse:
    """Hand a new token to a student still in the session who lost theirs.

    A crashed tab, a closed window or another device loses the token kept in
    the browser. The student account is authenticated, so it takes its own
    participation back: same row, answers and position. The previous token
    stops working at once, so one account never sits the exam in two places,
    and its tab is told why. Once the exam has started, the teacher sees the
    takeover as a monitoring alert.
    """
    participant_token = token_urlsafe(32)
    resumed_values: dict[str, object] = {
        "access_token_hash": participant_token_hash(participant_token),
        "replaced_token_hash": existing.access_token_hash,
        "student_identifier": student.identifier,
        "student_display_name": student.display_name,
    }
    reported = quiz_session.status != SessionStatus.WAITING
    if reported:
        resumed_values |= {
            "violation_count": QuizParticipant.violation_count + 1,
            "last_violation_type": SESSION_RESUMED_VIOLATION,
            "last_violation_at": datetime.now(UTC),
        }
    resumed = session.execute(
        update(QuizParticipant)
        .where(
            QuizParticipant.id == existing.id,
            QuizParticipant.left_at.is_(None),
            QuizParticipant.access_token_hash == existing.access_token_hash,
        )
        .values(**resumed_values)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(resumed) != 1:
        session.rollback()
        reject_quiz_join(request, join_subject)
    session.commit()
    session.refresh(existing)
    audit_event(
        "quiz.participation_resumed",
        session_id=quiz_session.id,
        participant_id=existing.id,
        reported=reported,
    )
    publish_quiz_update(request, quiz_session, session)
    state = student_state_response(quiz_session, quiz, existing, session)
    return StudentQuizJoinResponse(
        **state.model_dump(), participant_token=participant_token
    )


def first_join(
    quiz_session: QuizSession,
    quiz: Quiz,
    student: Student,
    join_subject: str,
    request: Request,
    session: Session,
) -> StudentQuizJoinResponse:
    """Add a student to a waiting room they have not entered yet."""
    if quiz_session.status != SessionStatus.WAITING:
        reject_quiz_join(request, join_subject)
    waiting = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == SessionStatus.WAITING,
        )
        .values(status=SessionStatus.WAITING)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(waiting) != 1:
        session.rollback()
        reject_quiz_join(request, join_subject)
    participant_token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_id=student.id,
        student_identifier=student.identifier,
        student_display_name=student.display_name,
        access_token_hash=participant_token_hash(participant_token),
    )
    session.add(participant)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        reject_quiz_join(request, join_subject)
    publish_quiz_update(request, quiz_session, session)
    state = student_state_response(quiz_session, quiz, participant, session)
    return StudentQuizJoinResponse(
        **state.model_dump(),
        participant_token=participant_token,
    )


@router.post(
    "/join",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_quiz(
    payload: QuizJoin,
    request: Request,
    session: DbSession,
    account: Annotated[StudentAccount, Depends(current_student)],
) -> StudentQuizJoinResponse:
    quiz_session, quiz, student, join_subject = joinable_session(
        payload, account, request, session
    )
    existing = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.student_id == student.id,
        )
    )
    if existing is not None:
        return rejoin_quiz(
            quiz_session, quiz, existing, student, join_subject, request, session
        )
    return first_join(quiz_session, quiz, student, join_subject, request, session)


@router.post(
    "/student/sessions/{join_code}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_student_quiz(
    context: CurrentParticipant,
    request: Request,
    session: DbSession,
) -> Response:
    quiz_session, quiz, participant = (
        context.session,
        context.quiz,
        context.participant,
    )
    lock_for_participant_write(quiz_session, participant, session)
    participant.left_at = datetime.now(UTC)
    participant.access_token_hash = None
    session.flush()
    finish_when_nobody_can_answer(quiz_session, quiz, session)
    session.commit()
    publish_quiz_update(request, quiz_session, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/student/sessions/{join_code}",
    response_model=StudentQuizStateResponse,
)
def get_student_quiz_state(
    context: CurrentParticipant,
    session: DbSession,
) -> StudentQuizStateResponse:
    return student_state_response(
        context.session, context.quiz, context.participant, session
    )
