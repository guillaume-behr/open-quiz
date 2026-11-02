"""Live updates reach the sockets of every worker, not only the publisher's."""

import time
from pathlib import Path

import psycopg
import pytest

from app import live_relay
from app.live_relay import PostgresLiveRelay, relay_channel
from app.routers import live
from scripts import live_relay_benchmark

from support import (
    FRONTEND_ORIGIN,
    database_url_for,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)


def conninfo_for(database: Path) -> str:
    return database_url_for(database).replace("postgresql+psycopg://", "postgresql://")


def wait_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


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
        time.sleep(0.2)
        assert first_received == []
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
    relay.send("quiz-session:1")
    assert logged == ["Live relay could not notify the other workers"]
    relay.send("quiz-session:1")
    assert logged == ["Live relay could not notify the other workers"]
    relay.stop()


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
    try:
        assert listener.listening.wait(5)
        with psycopg.connect(conninfo, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE query LIKE 'LISTEN %%' AND pid <> pg_backend_pid()"
            )
        assert wait_until(
            lambda: "Live relay lost its connection; reconnecting" in logged
        )
        assert wait_until(listener.listening.is_set)
        sender.send("quiz-session:3")
        assert wait_until(lambda: received == ["quiz-session:3"])
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
