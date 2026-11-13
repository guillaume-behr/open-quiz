"""Live quiz updates over WebSocket, for teachers and students.

Each socket authenticates with its first message, then receives a fresh
snapshot whenever LiveQuizHub publishes a change on its topic, on a
periodic reconciliation, and a heartbeat while idle.
"""

from asyncio import Queue, to_thread, wait_for
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
from app.enums import SessionStatus
from app.live_quiz import (
    LiveSocketLimitError,
    active_quiz_sessions_topic,
    makeup_sessions_topic,
    participant_topic,
    quiz_session_topic,
    student_session_topic,
    websocket_origin_allowed,
)
from app.models import (
    Quiz,
    QuizSession,
    User,
)
from app.participants import authenticated_participant, participant_token_hash
from app.student_state import student_state_response
from app.teacher_session_responses import (
    active_makeup_session_responses,
    active_session_responses,
    session_response,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])

LIVE_HEARTBEAT_SECONDS = 25
# PostgreSQL NOTIFY carries every change to every worker; the reconciliation
# is only a safety net for a lost notification.
LIVE_TEACHER_RECONCILIATION_SECONDS = 30


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


async def close_over_limit(websocket: WebSocket) -> None:
    """Turn away a socket beyond what one account may hold on a feed."""
    await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)


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
    *,
    reconcile_after: float,
) -> bool:
    """Wait for a published update or the next reconciliation.

    Returns whether an update arrived. A session's deadline needs no wake-up
    of its own: the expiry loop finishes the session and publishes the change.
    """
    try:
        await wait_for(
            queue.get(), timeout=min(LIVE_HEARTBEAT_SECONDS, reconcile_after)
        )
    except TimeoutError:
        return False
    return True


def live_teacher_active_sessions_snapshot(
    websocket: WebSocket,
    professor_id: int,
) -> list[dict[str, object]] | None:
    with websocket.app.state.session_factory() as session:
        professor = session.get(User, professor_id)
        if professor is None or not professor.is_active:
            return None
        sessions = active_session_responses(professor, session)
    return [item.model_dump(mode="json") for item in sessions]


def live_teacher_session_snapshot(
    websocket: WebSocket,
    professor_id: int,
    session_id: int,
) -> tuple[dict[str, object] | None, bool]:
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
            return None, False
        quiz_session, quiz = row
        state = session_response(quiz_session, quiz, session)
    return state.model_dump(mode="json"), state.status == SessionStatus.FINISHED


def without_clock(value: object) -> object:
    """A snapshot without its server_now stamps, to tell whether it changed.

    Every state carries the time it was built at, so two snapshots of an
    unchanged session always differ by that alone: the feed must not resend
    them for it.
    """
    if isinstance(value, dict):
        return {
            key: without_clock(item)
            for key, item in value.items()
            if key != "server_now"
        }
    if isinstance(value, list):
        return [without_clock(item) for item in value]
    return value


def live_participant_id(
    websocket: WebSocket,
    join_code: str,
    token: str,
) -> int | None:
    """The participant a token opens in this session, or None."""
    with websocket.app.state.session_factory() as session:
        try:
            _, _, participant = authenticated_participant(
                join_code, token, websocket, session
            )
        except HTTPException:
            return None
    return participant.id


def live_student_session_snapshot(
    websocket: WebSocket,
    join_code: str,
    token: str,
) -> tuple[dict[str, object], bool] | None:
    with websocket.app.state.session_factory() as session:
        try:
            quiz_session, quiz, participant = authenticated_participant(
                join_code, token, websocket, session
            )
        except HTTPException:
            return None
        state = student_state_response(quiz_session, quiz, participant, session)
    return state.model_dump(mode="json"), state.status == SessionStatus.FINISHED


def live_makeup_sessions_snapshot(
    websocket: WebSocket,
    professor_id: int,
) -> list[dict[str, object]] | None:
    with websocket.app.state.session_factory() as session:
        professor = session.get(User, professor_id)
        if professor is None or not professor.is_active:
            return None
        sessions = active_makeup_session_responses(professor, session)
    return [item.model_dump(mode="json") for item in sessions]


@dataclass(frozen=True)
class LiveSnapshot:
    """The message a feed sends when it changed, and whether it is the last."""

    message: dict[str, object]
    terminal: bool = False


async def run_live_feed(
    websocket: WebSocket,
    *,
    topic: str,
    principal: str,
    authorize: Callable[[], Awaitable[bool]],
    snapshot: Callable[[], Awaitable[LiveSnapshot | None]],
    reconcile_after: float,
    also: tuple[str, ...] = (),
    authorize_on_reconcile: bool = True,
) -> None:
    """Follow a topic and send each changed snapshot until the socket ends.

    ``authorize`` tells whether the socket's credentials still hold: it is
    checked before every heartbeat and, with ``authorize_on_reconcile``, at
    each reconciliation. A snapshot of None refuses the socket.
    """
    hub = websocket.app.state.live_quiz_hub
    try:
        async with hub.subscribe(topic, principal, also=also) as updates:
            heartbeat = LiveHeartbeat()
            last_message: dict[str, object] | None = None
            # Checked again at each reconciliation, not on every update: the
            # update itself only triggers a snapshot of the subscriber's data.
            updated = True
            while True:
                if authorize_on_reconcile and not updated and not await authorize():
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                current = await snapshot()
                if current is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                if without_clock(current.message) != without_clock(last_message):
                    await websocket.send_json(current.message)
                    heartbeat.record_send()
                    last_message = current.message
                if current.terminal:
                    await websocket.close()
                    return
                updated = await wait_for_live_update(
                    updates, reconcile_after=reconcile_after
                )
                if heartbeat.is_due():
                    if not await authorize():
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    await websocket.send_json({"type": "ping"})
                    heartbeat.record_send()
    except LiveSocketLimitError:
        await close_over_limit(websocket)
    except WebSocketDisconnect, RuntimeError:
        return


async def run_teacher_feed(
    websocket: WebSocket,
    topic: Callable[[int], str],
    snapshot: Callable[[int], Awaitable[LiveSnapshot | None]],
) -> None:
    """A teacher feed: authenticate the professor, then follow their topic."""
    token = await accept_live_socket(websocket)
    if token is None:
        return
    professor_id = await async_live_professor_id(websocket, token)
    if professor_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async def authorize() -> bool:
        return await async_live_professor_id(websocket, token) == professor_id

    async def professor_snapshot() -> LiveSnapshot | None:
        return await snapshot(professor_id)

    await run_live_feed(
        websocket,
        topic=topic(professor_id),
        principal=f"professor:{professor_id}",
        authorize=authorize,
        snapshot=professor_snapshot,
        reconcile_after=LIVE_TEACHER_RECONCILIATION_SECONDS,
    )


@router.websocket("/live/teacher/sessions")
async def live_teacher_active_quiz_sessions(websocket: WebSocket) -> None:
    async def snapshot(professor_id: int) -> LiveSnapshot | None:
        sessions = await to_thread(
            live_teacher_active_sessions_snapshot, websocket, professor_id
        )
        if sessions is None:
            return None
        return LiveSnapshot({"type": "active_sessions", "data": sessions})

    await run_teacher_feed(websocket, active_quiz_sessions_topic, snapshot)


@router.websocket("/live/teacher/sessions/{session_id}")
async def live_teacher_quiz_session(
    websocket: WebSocket,
    session_id: int,
) -> None:
    async def snapshot(professor_id: int) -> LiveSnapshot:
        state, terminal = await to_thread(
            live_teacher_session_snapshot, websocket, professor_id, session_id
        )
        if state is None:
            return LiveSnapshot({"type": "deleted"}, terminal=True)
        return LiveSnapshot({"type": "session", "data": state}, terminal=terminal)

    await run_teacher_feed(
        websocket, lambda _professor_id: quiz_session_topic(session_id), snapshot
    )


@router.websocket("/live/student/sessions/{join_code}")
async def live_student_quiz_session(
    websocket: WebSocket,
    join_code: str,
) -> None:
    token = await accept_live_socket(websocket)
    if token is None:
        return
    normalized_code = join_code.strip().upper()
    participant_id = await to_thread(
        live_participant_id,
        websocket,
        normalized_code,
        token,
    )
    if participant_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async def authorize() -> bool:
        return (
            await to_thread(live_participant_id, websocket, normalized_code, token)
            == participant_id
        )

    async def snapshot() -> LiveSnapshot | None:
        current = await to_thread(
            live_student_session_snapshot, websocket, normalized_code, token
        )
        if current is None:
            return None
        state, terminal = current
        return LiveSnapshot({"type": "session", "data": state}, terminal=terminal)

    await run_live_feed(
        websocket,
        topic=student_session_topic(normalized_code),
        principal=f"participant:{participant_token_hash(token)}",
        also=(participant_topic(participant_id),),
        authorize=authorize,
        snapshot=snapshot,
        reconcile_after=LIVE_HEARTBEAT_SECONDS,
        # Every snapshot authenticates the participant again.
        authorize_on_reconcile=False,
    )


@router.websocket("/live/teacher/makeup-sessions")
async def live_teacher_makeup_sessions(websocket: WebSocket) -> None:
    async def snapshot(professor_id: int) -> LiveSnapshot | None:
        sessions = await to_thread(
            live_makeup_sessions_snapshot, websocket, professor_id
        )
        if sessions is None:
            return None
        return LiveSnapshot({"type": "makeup_sessions", "data": sessions})

    await run_teacher_feed(websocket, makeup_sessions_topic, snapshot)
