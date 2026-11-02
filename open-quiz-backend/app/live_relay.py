"""Relay live quiz notifications between API worker processes.

LiveQuizHub only reaches the WebSockets of its own process. With several
Uvicorn workers, a change made through one worker must also wake the sockets
held by the others: every publication is sent as a PostgreSQL NOTIFY, and each
process LISTENs and hands what the others sent to its local hub. Nothing but
the database is needed.

A notification sent while a listener reconnects is lost; the live feeds'
periodic reconciliation still brings their sockets up to date.
"""

import logging
from collections.abc import Callable
from hashlib import sha256
from threading import Event, Lock, Thread
from uuid import uuid4

import psycopg
from psycopg import sql

logger = logging.getLogger("open_quiz")

LISTEN_POLL_SECONDS = 0.5
RECONNECT_SECONDS = 1.0


def relay_channel(conninfo: str) -> str:
    """The channel of one deployment: every worker on a database shares it."""
    return f"open_quiz_live_{sha256(conninfo.encode()).hexdigest()[:16]}"


class PostgresLiveRelay:
    def __init__(self, conninfo: str, deliver: Callable[[str], None]) -> None:
        self._conninfo = conninfo
        self._deliver = deliver
        self._channel = relay_channel(conninfo)
        # Tells this process's own notifications apart: its hub has already
        # delivered them locally.
        self._origin = uuid4().hex
        self._send_lock = Lock()
        self._send_connection: psycopg.Connection | None = None
        self._stopping = Event()
        self.listening = Event()
        self._thread: Thread | None = None

    def send(self, topic: str) -> None:
        payload = f"{self._origin} {topic}"
        with self._send_lock:
            try:
                if self._send_connection is None or self._send_connection.closed:
                    self._send_connection = psycopg.connect(
                        self._conninfo, autocommit=True
                    )
                self._send_connection.execute(
                    "SELECT pg_notify(%s, %s)", (self._channel, payload)
                )
            except psycopg.Error:
                # Local sockets were already notified; the other workers'
                # reconciliation catches up.
                logger.exception("Live relay could not notify the other workers")
                self._close_send_connection()

    def start(self) -> None:
        self._thread = Thread(target=self._listen, name="live-relay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        with self._send_lock:
            self._close_send_connection()

    def _close_send_connection(self) -> None:
        if self._send_connection is not None:
            self._send_connection.close()
            self._send_connection = None

    def _listen(self) -> None:
        while not self._stopping.is_set():
            try:
                with psycopg.connect(self._conninfo, autocommit=True) as connection:
                    connection.execute(
                        sql.SQL("LISTEN {}").format(sql.Identifier(self._channel))
                    )
                    self.listening.set()
                    while not self._stopping.is_set():
                        for notification in connection.notifies(
                            timeout=LISTEN_POLL_SECONDS
                        ):
                            origin, _, topic = notification.payload.partition(" ")
                            if origin != self._origin:
                                self._deliver(topic)
            except psycopg.Error:
                logger.exception("Live relay lost its connection; reconnecting")
            self.listening.clear()
            self._stopping.wait(RECONNECT_SECONDS)
