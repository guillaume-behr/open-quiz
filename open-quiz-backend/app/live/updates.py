"""Publish quiz changes to the live views of teachers and students."""

from sqlalchemy import select
from starlette.requests import HTTPConnection

from app.core.dependencies import DbSession
from app.enums import SessionStatus
from app.live.hub import (
    LiveQuizHub,
    active_quiz_sessions_topic,
    makeup_sessions_topic,
    participant_topic,
    quiz_session_topic,
    student_session_topic,
)
from app.models import (
    MakeupSession,
    Quiz,
    QuizParticipant,
    QuizSession,
)


def publish_quiz_update(
    request: HTTPConnection,
    quiz_session: QuizSession,
    session: DbSession,
    *,
    active_sessions_changed: bool = True,
    makeup_sessions_changed: bool = True,
    participant: QuizParticipant | None = None,
) -> None:
    publish_session_change(
        request.app.state.live_quiz_hub,
        quiz_session,
        session,
        active_sessions_changed=active_sessions_changed,
        makeup_sessions_changed=makeup_sessions_changed,
        participant=participant,
    )


def publish_session_change(
    hub: LiveQuizHub,
    quiz_session: QuizSession,
    session: DbSession,
    *,
    active_sessions_changed: bool = True,
    makeup_sessions_changed: bool = True,
    participant: QuizParticipant | None = None,
) -> None:
    """Notify every live view a change of this session concerns.

    A change to one ``participant`` only (an answer, navigation, a violation,
    the hand-in) wakes that student's socket, not the whole class's, unless
    it finished the session: the last answer or hand-in ends the exam for
    every classmate still waiting on it.
    """
    hub.publish(quiz_session_topic(quiz_session.id))
    if participant is not None:
        hub.publish(participant_topic(participant.id))
    if participant is None or quiz_session.status == SessionStatus.FINISHED:
        hub.publish(student_session_topic(quiz_session.join_code))
    if active_sessions_changed:
        owner_id = session.scalar(
            select(Quiz.owner_id).where(Quiz.id == quiz_session.quiz_id)
        )
        if owner_id is not None:
            hub.publish(active_quiz_sessions_topic(owner_id))
    if makeup_sessions_changed and quiz_session.makeup_session_id is not None:
        makeup_owner_id = session.scalar(
            select(MakeupSession.owner_id).where(
                MakeupSession.id == quiz_session.makeup_session_id
            )
        )
        if makeup_owner_id is not None:
            hub.publish(makeup_sessions_topic(makeup_owner_id))


def publish_quiz_topics(
    request: HTTPConnection, session_id: int, join_code: str
) -> None:
    hub = request.app.state.live_quiz_hub
    hub.publish(quiz_session_topic(session_id))
    hub.publish(student_session_topic(join_code))


def publish_makeup_update(request: HTTPConnection, owner_id: int) -> None:
    request.app.state.live_quiz_hub.publish(makeup_sessions_topic(owner_id))


def publish_active_quiz_sessions_update(request: HTTPConnection, owner_id: int) -> None:
    request.app.state.live_quiz_hub.publish(active_quiz_sessions_topic(owner_id))
