"""Live updates reach the sockets of every worker, not only the publisher's."""

import asyncio
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import psycopg
import pytest

from app.live import relay as live_relay
from app.live.hub import LiveQuizHub, websocket_origin_allowed
from app.live.relay import PostgresLiveRelay, relay_channel
from app.routers.quizzes import live
from scripts import live_relay_benchmark

from support import (
    FRONTEND_ORIGIN,
    database_url_for,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
    wait_until,
)


def conninfo_for(database: Path) -> str:
    return database_url_for(database).replace("postgresql+psycopg://", "postgresql://")


def test_a_relay_delivers_other_processes_notifications(tmp_path: Path) -> None:
    conninfo = conninfo_for(tmp_path / "relay")
    first_received: list[str] = []
    second_received: list[str] = []
    first = PostgresLiveRelay(conninfo, first_received.append)
    second = PostgresLiveRelay(conninfo, second_received.append)
    for relay in (first, second):
        relay.start()
    try:
        assert first.listening.wait(5)
        assert second.listening.wait(5)
        first.send("quiz-session:7")
        assert wait_until(lambda: second_received == ["quiz-session:7"])
        # Its own notification is not delivered twice: the hub already did.
        # Notifications arrive in commit order, so had it been delivered it
        # would come before this one from the other process.
        second.send("quiz-session:8")
        assert wait_until(lambda: first_received != [])
        assert first_received == ["quiz-session:8"]
    finally:
        for relay in (first, second):
            relay.stop()


def test_deployments_on_other_databases_do_not_share_a_channel(tmp_path: Path) -> None:
    assert relay_channel(conninfo_for(tmp_path / "a")) != relay_channel(
        conninfo_for(tmp_path / "b")
    )


def test_a_failed_notification_is_logged_and_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = PostgresLiveRelay(conninfo_for(tmp_path / "relay-send"), lambda _: None)
    logged: list[str] = []
    monkeypatch.setattr(live_relay.logger, "exception", logged.append)
    real_connect = psycopg.connect
    attempts = iter([psycopg.OperationalError("database is down")])

    def flaky_connect(*arguments, **options):
        failure = next(attempts, None)
        if failure is not None:
            raise failure
        return real_connect(*arguments, **options)

    monkeypatch.setattr(live_relay.psycopg, "connect", flaky_connect)
    # What the sender thread runs for each queued topic.
    relay._notify("quiz-session:1")
    assert logged == ["Live relay could not notify the other workers"]
    relay._notify("quiz-session:1")
    assert logged == ["Live relay could not notify the other workers"]
    relay.stop()


def test_publishing_never_waits_for_an_unresponsive_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = PostgresLiveRelay(conninfo_for(tmp_path / "relay-hang"), lambda _: None)
    release = Event()
    connecting: list[dict[str, object]] = []

    def hanging_connect(*_arguments, **options):
        connecting.append(options)
        release.wait(10)
        raise psycopg.OperationalError("timed out")

    monkeypatch.setattr(live_relay.psycopg, "connect", hanging_connect)
    monkeypatch.setattr(live_relay.logger, "exception", lambda *_: None)
    relay._sender = Thread(target=relay._send_pending, daemon=True)
    relay._sender.start()
    try:
        for _ in range(3):
            relay.send("quiz-session:9")
        # The request thread got here while the sender is stuck connecting.
        assert wait_until(lambda: len(connecting) == 1)
        assert connecting[0]["connect_timeout"] == live_relay.CONNECT_TIMEOUT_SECONDS
    finally:
        release.set()
        relay.stop()
    # Three sends of one topic while the first was in flight: sent once more.
    assert len(connecting) <= 2


def test_the_listener_reconnects_after_losing_its_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live_relay, "RECONNECT_SECONDS", 0.01)
    logged: list[str] = []
    monkeypatch.setattr(live_relay.logger, "exception", logged.append)
    conninfo = conninfo_for(tmp_path / "relay-reconnect")
    received: list[str] = []
    listener = PostgresLiveRelay(conninfo, received.append)
    sender = PostgresLiveRelay(conninfo, lambda _: None)
    listener.start()
    sender.start()
    try:
        assert listener.listening.wait(5)
        with psycopg.connect(conninfo, autocommit=True) as admin:
            # Only this listener's connection: tests running in parallel
            # hold listeners of their own.
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE query = %s AND pid <> pg_backend_pid()",
                (f'LISTEN "{relay_channel(conninfo)}"',),
            )
        assert wait_until(
            lambda: "Live relay lost its connection; reconnecting" in logged
        )

        # A notification sent while the listener reconnects is lost, by
        # design: send until one arrives over the new connection.
        def delivered() -> bool:
            sender.send("quiz-session:3")
            return "quiz-session:3" in received

        assert wait_until(delivered)
    finally:
        listener.stop()
        sender.stop()


def test_a_change_through_one_worker_wakes_another_workers_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two apps on one database stand for two Uvicorn workers."""
    # Without the relay, only this periodic reconciliation would catch up.
    monkeypatch.setattr(live, "LIVE_TEACHER_RECONCILIATION_SECONDS", 3600)
    settings = settings_for(tmp_path / "two-workers")
    with make_client(settings) as first, make_client(settings) as second:
        environment = exam_environment(first)
        launched, _ = launch_and_join(first, environment)
        assert second.app.state.live_quiz_hub is not first.app.state.live_quiz_hub
        token = environment["teacher_headers"]["Authorization"].removeprefix("Bearer ")
        with second.websocket_connect(
            f"/api/quizzes/live/teacher/sessions/{launched['id']}",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as socket:
            socket.send_json({"token": token})
            assert socket.receive_json()["data"]["status"] == "waiting"
            first.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            )
            update = socket.receive_json()
            assert update["data"]["status"] == "in_progress"


def test_the_relay_benchmark_reports_latencies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_relay_benchmark.main(
        ["--subscribers", "4", "--sessions", "2", "--rounds", "3"]
    )
    assert "3 publications to 2 sockets each: median" in capsys.readouterr().out


def test_live_hub_tolerates_closed_loops_and_pending_updates() -> None:
    hub = LiveQuizHub()

    async def scenario() -> None:
        async with hub.subscribe("topic") as first, hub.subscribe("topic"):
            hub.publish("topic")
            hub.publish("topic")
            await asyncio.sleep(0)
            assert first.qsize() == 1
        assert "topic" not in hub._subscribers

    asyncio.run(scenario())

    async def closed_loop_subscription() -> None:
        async with hub.subscribe("closed"):
            loop = asyncio.get_running_loop()
            subscriber = next(iter(hub._subscribers["closed"]))
            object.__setattr__(subscriber, "loop", _ClosedLoop())
            hub.publish("closed")
            object.__setattr__(subscriber, "loop", loop)

    asyncio.run(closed_loop_subscription())

    async def topic_removed_during_subscription() -> None:
        async with hub.subscribe("removed"):
            hub._subscribers.pop("removed")

    asyncio.run(topic_removed_during_subscription())
    hub.end_authentication()
    assert hub._pending_authentications == 0


class _ClosedLoop:
    def call_soon_threadsafe(self, *_: object) -> None:
        raise RuntimeError("Event loop is closed")


@pytest.mark.parametrize(
    ("origin", "environment", "allowed"),
    [
        ("http://localhost:5173/", "test", True),
        (None, "development", False),
        ("http://localhost:4173", "development", True),
        ("http://127.0.0.1:4173", "development", True),
        ("http://evil.example:4173", "development", False),
        ("http://localhost:4173/path", "development", False),
        ("http://user@localhost:4173", "development", False),
        ("http://localhost:4173", "test", False),
    ],
)
def test_websocket_origins_follow_the_environment(
    origin: str | None, environment: str, allowed: bool
) -> None:
    headers = {} if origin is None else {"origin": origin}
    websocket = SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    frontend_origin="http://localhost:5173",
                    environment=environment,
                )
            )
        ),
    )
    assert websocket_origin_allowed(websocket) is allowed
