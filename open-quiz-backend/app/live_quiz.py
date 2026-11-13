from asyncio import AbstractEventLoop, Queue, get_running_loop
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlparse

from fastapi import WebSocket

from app.config import app_settings

# One person following one feed from a few tabs is ordinary; past that, the
# sockets are refused. Each one holds a connection of the server's shared
# limit for as long as it stays open, so without a bound a single account
# could take them all from a class in the middle of an exam.
MAX_LIVE_SOCKETS_PER_FEED = 4


class LiveSocketLimitError(Exception):
    """This account already follows this feed from too many sockets."""


@dataclass(frozen=True)
class _Subscriber:
    loop: AbstractEventLoop
    queue: Queue[None]


class LiveQuizHub:
    """Thread-safe in-process fan-out for live quiz state changes.

    A relay (app/live_relay.py) carries each publication to the other worker
    processes, which deliver it to their own sockets with publish_local().
    """

    def __init__(
        self,
        max_pending_authentications: int = 64,
        max_sockets_per_feed: int = MAX_LIVE_SOCKETS_PER_FEED,
    ) -> None:
        self._lock = Lock()
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)
        # Open sockets per (topic, principal), in this worker process.
        self._sockets: dict[tuple[str, str], int] = defaultdict(int)
        self._max_sockets_per_feed = max_sockets_per_feed
        self._pending_authentications = 0
        self._max_pending_authentications = max_pending_authentications
        self._relay: Callable[[str], None] | None = None

    def attach_relay(self, relay: Callable[[str], None]) -> None:
        self._relay = relay

    def begin_authentication(self) -> bool:
        with self._lock:
            if self._pending_authentications >= self._max_pending_authentications:
                return False
            self._pending_authentications += 1
            return True

    def end_authentication(self) -> None:
        with self._lock:
            self._pending_authentications = max(0, self._pending_authentications - 1)

    @asynccontextmanager
    async def subscribe(
        self,
        topic: str,
        principal: str | None = None,
        *,
        also: tuple[str, ...] = (),
    ) -> AsyncIterator[Queue[None]]:
        """Follow a topic, and the ``also`` ones, until the block exits.

        ``principal`` names who holds the socket; LiveSocketLimitError is
        raised when they already follow this topic from too many.
        """
        topics = (topic, *also)
        subscriber = _Subscriber(get_running_loop(), Queue(maxsize=1))
        feed = (topic, principal) if principal is not None else None
        with self._lock:
            if feed is not None:
                if self._sockets[feed] >= self._max_sockets_per_feed:
                    raise LiveSocketLimitError
                self._sockets[feed] += 1
            for followed in topics:
                self._subscribers[followed].add(subscriber)
        try:
            yield subscriber.queue
        finally:
            with self._lock:
                for followed in topics:
                    subscribers = self._subscribers.get(followed)
                    if subscribers is not None:
                        subscribers.discard(subscriber)
                        if not subscribers:
                            self._subscribers.pop(followed, None)
                if feed is not None:
                    self._sockets[feed] -= 1
                    if not self._sockets[feed]:
                        del self._sockets[feed]

    def publish(self, topic: str) -> None:
        self.publish_local(topic)
        if self._relay is not None:
            self._relay(topic)

    def publish_local(self, topic: str) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(topic, ()))
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(
                    self._offer_update, subscriber.queue
                )
            except RuntimeError:
                # The event loop may close between copying and notifying the
                # subscriber during application shutdown.
                continue

    @staticmethod
    def _offer_update(queue: Queue[None]) -> None:
        if queue.empty():
            queue.put_nowait(None)


def websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    settings = app_settings(websocket)
    expected = settings.frontend_origin.rstrip("/")
    if origin is not None and origin.rstrip("/") == expected:
        return True
    if origin is None or settings.environment != "development":
        return False
    parsed = urlparse(origin)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.path in {"", "/"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def quiz_session_topic(session_id: int) -> str:
    return f"quiz-session:{session_id}"


def active_quiz_sessions_topic(owner_id: int) -> str:
    return f"active-quiz-sessions:{owner_id}"


def student_session_topic(join_code: str) -> str:
    return f"student-session:{join_code.strip().upper()}"


def participant_topic(participant_id: int) -> str:
    """Changes only that participant's own exam view shows."""
    return f"quiz-participant:{participant_id}"


def makeup_sessions_topic(owner_id: int) -> str:
    return f"makeup-sessions:{owner_id}"
