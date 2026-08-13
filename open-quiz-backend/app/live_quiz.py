from asyncio import AbstractEventLoop, Queue, get_running_loop
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlparse

from fastapi import WebSocket


@dataclass(frozen=True)
class _Subscriber:
    loop: AbstractEventLoop
    queue: Queue[None]


class LiveQuizHub:
    """Thread-safe in-process fan-out for live quiz state changes."""

    def __init__(self, max_pending_authentications: int = 64) -> None:
        self._lock = Lock()
        self._subscribers: dict[str, set[_Subscriber]] = defaultdict(set)
        self._pending_authentications = 0
        self._max_pending_authentications = max_pending_authentications

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
    async def subscribe(self, topic: str) -> AsyncIterator[Queue[None]]:
        subscriber = _Subscriber(get_running_loop(), Queue(maxsize=1))
        with self._lock:
            self._subscribers[topic].add(subscriber)
        try:
            yield subscriber.queue
        finally:
            with self._lock:
                subscribers = self._subscribers.get(topic)
                if subscribers is not None:
                    subscribers.discard(subscriber)
                    if not subscribers:
                        self._subscribers.pop(topic, None)

    def publish(self, topic: str) -> None:
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
    settings = websocket.app.state.settings
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


def makeup_sessions_topic(owner_id: int) -> str:
    return f"makeup-sessions:{owner_id}"
