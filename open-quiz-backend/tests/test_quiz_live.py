"""Live quiz WebSocket paths outside the main flows."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import status
from sqlalchemy import update
from starlette.websockets import WebSocketDisconnect

from app.models import QuizSession
from app.routers import live, quizzes

from support import (
    FRONTEND_ORIGIN,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)

TEACHER_SESSIONS = "/api/quizzes/live/teacher/sessions"
TEACHER_MAKEUPS = "/api/quizzes/live/teacher/makeup-sessions"


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(live, "LIVE_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(live, "LIVE_TEACHER_RECONCILIATION_SECONDS", 0.05)
    # Every round ends with a keepalive, so token checks happen in a fixed order.
    monkeypatch.setattr(live.LiveHeartbeat, "is_due", lambda self: True)
    with make_client(settings_for(tmp_path / "live")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        environment["teacher_token"] = environment["teacher_headers"][
            "Authorization"
        ].removeprefix("Bearer ")
        yield environment


def connect(client, path: str):
    return client.websocket_connect(path, headers={"Origin": FRONTEND_ORIGIN})


def assert_closed(socket, code: int = status.WS_1008_POLICY_VIOLATION) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            socket.receive_json()
    assert closed.value.code == code


def professor_ids(sequence: list[int | None]):
    """Answer successive token checks from a script, then keep the last value."""

    async def scripted(websocket, token) -> int | None:
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return scripted


@pytest.mark.parametrize(
    "path",
    [
        TEACHER_SESSIONS,
        f"{TEACHER_SESSIONS}/1",
        "/api/quizzes/live/student/sessions/ABCDEF",
        TEACHER_MAKEUPS,
    ],
)
def test_live_sockets_reject_malformed_credentials(environment, path: str) -> None:
    client = environment["client"]
    for frame in ("not json", '{"token": ""}', "[1, 2]", '{"token": "invalid"}'):
        with connect(client, path) as socket:
            socket.send_text(frame)
            assert_closed(socket)


def test_live_sockets_ask_clients_to_retry_when_saturated(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    monkeypatch.setattr(
        client.app.state.live_quiz_hub, "begin_authentication", lambda: False
    )
    with connect(client, TEACHER_SESSIONS) as socket:
        assert_closed(socket, status.WS_1013_TRY_AGAIN_LATER)


@pytest.mark.parametrize("path", [TEACHER_SESSIONS, TEACHER_MAKEUPS])
def test_teacher_feeds_stream_pings_until_revoked(
    environment, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    client = environment["client"]
    with connect(client, path) as socket:
        socket.send_json({"token": environment["teacher_token"]})
        first = socket.receive_json()
        assert first["type"] in {"active_sessions", "makeup_sessions"}
        assert first["data"] == []
        assert socket.receive_json() == {"type": "ping"}

    me = client.get("/api/users/me", headers=environment["teacher_headers"]).json()
    # Revoked between the snapshot and the keepalive.
    monkeypatch.setattr(
        live, "async_live_professor_id", professor_ids([me["id"], me["id"], None])
    )
    with connect(client, path) as socket:
        socket.send_json({"token": environment["teacher_token"]})
        socket.receive_json()
        assert_closed(socket)

    # Revoked before the next snapshot.
    monkeypatch.setattr(
        live, "async_live_professor_id", professor_ids([me["id"], None])
    )
    with connect(client, path) as socket:
        socket.send_json({"token": environment["teacher_token"]})
        assert_closed(socket)

    # Deactivated while the snapshot is being built.
    monkeypatch.setattr(live, "async_live_professor_id", professor_ids([me["id"]]))
    monkeypatch.setattr(
        live,
        "live_teacher_active_sessions_snapshot",
        lambda *_: (None, None),
    )
    monkeypatch.setattr(live, "live_makeup_sessions_snapshot", lambda *_: None)
    with connect(client, path) as socket:
        socket.send_json({"token": environment["teacher_token"]})
        assert_closed(socket)


def test_teacher_session_feed_reports_deletion_and_completion(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    token = {"token": environment["teacher_token"]}

    with connect(client, f"{TEACHER_SESSIONS}/999999") as socket:
        socket.send_json(token)
        assert socket.receive_json() == {"type": "deleted"}
        assert_closed(socket, status.WS_1000_NORMAL_CLOSURE)

    launched, _ = launch_and_join(client, environment)
    path = f"{TEACHER_SESSIONS}/{launched['id']}"
    with connect(client, path) as socket:
        socket.send_json(token)
        assert socket.receive_json()["type"] == "session"
        assert socket.receive_json() == {"type": "ping"}

    me = client.get("/api/users/me", headers=environment["teacher_headers"]).json()
    monkeypatch.setattr(
        live, "async_live_professor_id", professor_ids([me["id"], me["id"], None])
    )
    with connect(client, path) as socket:
        socket.send_json(token)
        socket.receive_json()
        assert_closed(socket)
    monkeypatch.setattr(
        live, "async_live_professor_id", professor_ids([me["id"], None])
    )
    with connect(client, path) as socket:
        socket.send_json(token)
        assert_closed(socket)
    monkeypatch.undo()

    client.post(
        f"/api/quizzes/sessions/{launched['id']}/start",
        headers=environment["teacher_headers"],
    )
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        session.commit()
    with connect(client, path) as socket:
        socket.send_json(token)
        final = socket.receive_json()
        assert final["data"]["status"] == "finished"
        assert_closed(socket, status.WS_1000_NORMAL_CLOSURE)


def test_student_feed_follows_its_participation(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    launched, participant_headers = launch_and_join(client, environment)
    path = f"/api/quizzes/live/student/sessions/{launched['join_code']}"
    token = {"token": participant_headers["X-Quiz-Token"]}

    with connect(client, path) as socket:
        socket.send_json(token)
        assert socket.receive_json()["type"] == "session"
        assert socket.receive_json() == {"type": "ping"}

    checks = [True, False]
    monkeypatch.setattr(
        live,
        "live_participant_is_authenticated",
        lambda *_: checks.pop(0) if len(checks) > 1 else checks[0],
    )
    with connect(client, path) as socket:
        socket.send_json(token)
        socket.receive_json()
        assert_closed(socket)

    monkeypatch.setattr(live, "live_participant_is_authenticated", lambda *_: True)
    monkeypatch.setattr(live, "live_student_session_snapshot", lambda *_: None)
    with connect(client, path) as socket:
        socket.send_json(token)
        assert_closed(socket)
    monkeypatch.undo()

    client.post(
        f"/api/quizzes/sessions/{launched['id']}/start",
        headers=environment["teacher_headers"],
    )
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        session.commit()
    with connect(client, path) as socket:
        socket.send_json(token)
        final = socket.receive_json()
        assert final["data"]["status"] == "finished"
        assert_closed(socket, status.WS_1000_NORMAL_CLOSURE)


def test_live_snapshots_handle_missing_records(environment) -> None:
    client = environment["client"]
    websocket = SimpleNamespace(app=client.app)
    assert live.live_teacher_active_sessions_snapshot(websocket, 999999) == (
        None,
        None,
    )
    assert live.live_makeup_sessions_snapshot(websocket, 999999) is None
    assert live.live_student_session_snapshot(websocket, "ABCDEF", "bad") is None
    assert not live.live_participant_is_authenticated(websocket, "ABCDEF", "bad")


class _ScalarSession:
    def __init__(self, *values: Any) -> None:
        self.values = list(values)

    def scalar(self, _statement: object) -> Any:
        return self.values.pop(0)


def test_quiz_updates_skip_owners_that_no_longer_exist(environment) -> None:
    client = environment["client"]
    published: list[str] = []
    hub = SimpleNamespace(publish=published.append)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(live_quiz_hub=hub))
    )
    quiz_session = SimpleNamespace(
        id=1, quiz_id=1, join_code="ABCDEF", makeup_session_id=2
    )

    quizzes.publish_quiz_update(request, quiz_session, _ScalarSession(None, None))

    assert published == ["quiz-session:1", "student-session:ABCDEF"]
    assert client is not None
