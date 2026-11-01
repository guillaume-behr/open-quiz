"""Live quiz updates over WebSocket, for teachers and students.

Each socket authenticates with its first message, then receives a fresh
snapshot whenever LiveQuizHub publishes a change on its topic, on a
periodic reconciliation, and a heartbeat while idle.
"""

from asyncio import Queue, to_thread, wait_for
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select

from app.dependencies import authenticated_user_from_token
from app.live_quiz import (
    active_quiz_sessions_topic,
    makeup_sessions_topic,
    quiz_session_topic,
    student_session_topic,
    websocket_origin_allowed,
)
from app.models import (
    Quiz,
    QuizSession,
    User,
)
from app.routers.makeup import list_makeup_sessions
from app.routers.quizzes import (
    active_session_responses,
    authenticated_participant,
    publish_quiz_update,
    session_response,
    student_state_response,
)
from app.services.session_lifecycle import (
    as_utc,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])

LIVE_HEARTBEAT_SECONDS = 25
LIVE_TEACHER_RECONCILIATION_SECONDS = 2


async def accept_live_socket(websocket: WebSocket) -> str | None:
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    hub = websocket.app.state.live_quiz_hub
    if not hub.begin_authentication():
        await websocket.accept()
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return None
    try:
        await websocket.accept()
        try:
            credentials = await wait_for(websocket.receive_json(), timeout=5)
        except TimeoutError, WebSocketDisconnect, ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
    finally:
        hub.end_authentication()
    token = credentials.get("token") if isinstance(credentials, dict) else None
    if not isinstance(token, str) or not token or len(token) > 2048:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return token


def authenticated_live_professor_id(websocket: WebSocket, token: str) -> int | None:
    with websocket.app.state.session_factory() as session:
        professor = authenticated_user_from_token(websocket, token, session)
        if professor is None or professor.is_admin:
            return None
        return professor.id


async def async_live_professor_id(websocket: WebSocket, token: str) -> int | None:
    return await to_thread(authenticated_live_professor_id, websocket, token)


class LiveHeartbeat:
    """Track how long a live socket has gone without sending anything.

    Every live endpoint reconciles on a timer but only sends a snapshot that
    changed. Left at that, an idle socket puts no bytes on the wire at all: a
    proxy or a NAT that drops it leaves the page silently stale, because the
    client only reconnects on a close it never sees.
    """

    def __init__(self, interval: float | None = None) -> None:
        self.interval = LIVE_HEARTBEAT_SECONDS if interval is None else interval
        self.last_sent_at = monotonic()

    def record_send(self) -> None:
        self.last_sent_at = monotonic()

    def is_due(self) -> bool:
        return monotonic() - self.last_sent_at >= self.interval


async def wait_for_live_update(
    queue: Queue[None],
    ends_at: datetime | None,
    *,
    reconcile_after: float,
) -> None:
    """Wait for a published update, the next reconciliation, or the deadline."""
    timeout = min(LIVE_HEARTBEAT_SECONDS, reconcile_after)
    if ends_at is not None:
        remaining = max(0, (as_utc(ends_at) - datetime.now(UTC)).total_seconds())
        timeout = min(timeout, remaining)
    with suppress(TimeoutError):
        await wait_for(queue.get(), timeout=timeout)


def live_teacher_active_sessions_snapshot(
    websocket: WebSocket,
    professor_id: int,
) -> tuple[list[dict[str, object]] | None, datetime | None]:
    with websocket.app.state.session_factory() as session:
        professor = session.get(User, professor_id)
        if professor is None or not professor.is_active:
            return None, None
        sessions = active_session_responses(professor, session)
    next_ends_at = min(
        (
            item.ends_at
            for item in sessions
            if item.status == "in_progress" and item.ends_at is not None
        ),
        default=None,
    )
    return [item.model_dump(mode="json") for item in sessions], next_ends_at


def live_teacher_session_snapshot(
    websocket: WebSocket,
    professor_id: int,
    session_id: int,
) -> tuple[dict[str, object] | None, datetime | None, bool]:
    with websocket.app.state.session_factory() as session:
        row = session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.id == session_id,
                Quiz.owner_id == professor_id,
            )
        ).first()
        if row is None:
            return None, None, False
        quiz_session, quiz = row
        previous_status = quiz_session.status
        state = session_response(quiz_session, quiz, session)
        if quiz_session.status != previous_status:
            publish_quiz_update(websocket, quiz_session, session)
    return (
        state.model_dump(mode="json"),
        state.ends_at if state.status == "in_progress" else None,
        state.status in {"finished", "cancelled"},
    )


def live_participant_is_authenticated(
    websocket: WebSocket,
    join_code: str,
    token: str,
) -> bool:
    with websocket.app.state.session_factory() as session:
        try:
            authenticated_participant(join_code, token, websocket, session)
        except HTTPException:
            return False
    return True


def live_student_session_snapshot(
    websocket: WebSocket,
    join_code: str,
    token: str,
) -> tuple[dict[str, object], datetime | None, bool] | None:
    with websocket.app.state.session_factory() as session:
        try:
            quiz_session, quiz, participant = authenticated_participant(
                join_code, token, websocket, session
            )
        except HTTPException:
            return None
        previous_status = quiz_session.status
        state = student_state_response(quiz_session, quiz, participant, session)
        if quiz_session.status != previous_status:
            publish_quiz_update(websocket, quiz_session, session)
    return (
        state.model_dump(mode="json"),
        state.ends_at if state.status == "in_progress" else None,
        state.status in {"finished", "cancelled"},
    )


def live_makeup_sessions_snapshot(
    websocket: WebSocket,
    professor_id: int,
) -> list[dict[str, object]] | None:
    with websocket.app.state.session_factory() as session:
        professor = session.get(User, professor_id)
        if professor is None or not professor.is_active:
            return None
        sessions = list_makeup_sessions(professor, session)
    return [item.model_dump(mode="json") for item in sessions]


@router.websocket("/live/teacher/sessions")
async def live_teacher_active_quiz_sessions(websocket: WebSocket) -> None:
    token = await accept_live_socket(websocket)
    if token is None:
        return
    professor_id = await async_live_professor_id(websocket, token)
    if professor_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    topic = active_quiz_sessions_topic(professor_id)
    hub = websocket.app.state.live_quiz_hub
    try:
        async with hub.subscribe(topic) as updates:
            heartbeat = LiveHeartbeat()
            next_ends_at: datetime | None = None
            last_sessions: list[dict[str, object]] | None = None
            while True:
                if await async_live_professor_id(websocket, token) != professor_id:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                sessions, next_ends_at = await to_thread(
                    live_teacher_active_sessions_snapshot,
                    websocket,
                    professor_id,
                )
                if sessions is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                if sessions != last_sessions:
                    await websocket.send_json(
                        {
                            "type": "active_sessions",
                            "data": sessions,
                        }
                    )
                    heartbeat.record_send()
                    last_sessions = sessions
                await wait_for_live_update(
                    updates,
                    next_ends_at,
                    reconcile_after=LIVE_TEACHER_RECONCILIATION_SECONDS,
                )
                if heartbeat.is_due():
                    if await async_live_professor_id(websocket, token) != professor_id:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    await websocket.send_json({"type": "ping"})
                    heartbeat.record_send()
    except WebSocketDisconnect, RuntimeError:
        return


@router.websocket("/live/teacher/sessions/{session_id}")
async def live_teacher_quiz_session(
    websocket: WebSocket,
    session_id: int,
) -> None:
    token = await accept_live_socket(websocket)
    if token is None:
        return
    professor_id = await async_live_professor_id(websocket, token)
    if professor_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    topic = quiz_session_topic(session_id)
    hub = websocket.app.state.live_quiz_hub
    try:
        async with hub.subscribe(topic) as updates:
            heartbeat = LiveHeartbeat()
            ends_at: datetime | None = None
            last_state: dict[str, object] | None = None
            while True:
                if await async_live_professor_id(websocket, token) != professor_id:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                state, ends_at, terminal = await to_thread(
                    live_teacher_session_snapshot,
                    websocket,
                    professor_id,
                    session_id,
                )
                if state is None:
                    await websocket.send_json({"type": "deleted"})
                    await websocket.close()
                    return
                if state != last_state:
                    await websocket.send_json({"type": "session", "data": state})
                    heartbeat.record_send()
                    last_state = state
                if terminal:
                    await websocket.close()
                    return
                await wait_for_live_update(
                    updates,
                    ends_at,
                    reconcile_after=LIVE_TEACHER_RECONCILIATION_SECONDS,
                )
                if heartbeat.is_due():
                    if await async_live_professor_id(websocket, token) != professor_id:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    await websocket.send_json({"type": "ping"})
                    heartbeat.record_send()
    except WebSocketDisconnect, RuntimeError:
        return


@router.websocket("/live/student/sessions/{join_code}")
async def live_student_quiz_session(
    websocket: WebSocket,
    join_code: str,
) -> None:
    token = await accept_live_socket(websocket)
    if token is None:
        return
    normalized_code = join_code.strip().upper()
    if not await to_thread(
        live_participant_is_authenticated,
        websocket,
        normalized_code,
        token,
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    topic = student_session_topic(normalized_code)
    hub = websocket.app.state.live_quiz_hub
    try:
        async with hub.subscribe(topic) as updates:
            heartbeat = LiveHeartbeat()
            ends_at: datetime | None = None
            last_state: dict[str, object] | None = None
            while True:
                snapshot = await to_thread(
                    live_student_session_snapshot,
                    websocket,
                    normalized_code,
                    token,
                )
                if snapshot is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                state, ends_at, terminal = snapshot
                if state != last_state:
                    await websocket.send_json({"type": "session", "data": state})
                    heartbeat.record_send()
                    last_state = state
                if terminal:
                    await websocket.close()
                    return
                await wait_for_live_update(
                    updates,
                    ends_at,
                    reconcile_after=LIVE_HEARTBEAT_SECONDS,
                )
                if heartbeat.is_due():
                    if not await to_thread(
                        live_participant_is_authenticated,
                        websocket,
                        normalized_code,
                        token,
                    ):
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    await websocket.send_json({"type": "ping"})
                    heartbeat.record_send()
    except WebSocketDisconnect, RuntimeError:
        return


@router.websocket("/live/teacher/makeup-sessions")
async def live_teacher_makeup_sessions(websocket: WebSocket) -> None:
    token = await accept_live_socket(websocket)
    if token is None:
        return
    professor_id = await async_live_professor_id(websocket, token)
    if professor_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    topic = makeup_sessions_topic(professor_id)
    hub = websocket.app.state.live_quiz_hub
    try:
        async with hub.subscribe(topic) as updates:
            heartbeat = LiveHeartbeat()
            last_sessions: list[dict[str, object]] | None = None
            while True:
                if await async_live_professor_id(websocket, token) != professor_id:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                sessions = await to_thread(
                    live_makeup_sessions_snapshot,
                    websocket,
                    professor_id,
                )
                if sessions is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                if sessions != last_sessions:
                    await websocket.send_json(
                        {
                            "type": "makeup_sessions",
                            "data": sessions,
                        }
                    )
                    heartbeat.record_send()
                    last_sessions = sessions
                await wait_for_live_update(
                    updates,
                    None,
                    reconcile_after=LIVE_TEACHER_RECONCILIATION_SECONDS,
                )
                if heartbeat.is_due():
                    if await async_live_professor_id(websocket, token) != professor_id:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    await websocket.send_json({"type": "ping"})
                    heartbeat.record_send()
    except WebSocketDisconnect, RuntimeError:
        return
