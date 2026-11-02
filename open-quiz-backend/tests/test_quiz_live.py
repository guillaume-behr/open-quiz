"""Live quiz WebSockets for teachers and students."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import status
from sqlalchemy import update
from starlette.websockets import WebSocketDisconnect

from app.live_quiz import LiveQuizHub
from app.models import (
    QuizSession,
)
from app.routers import live, quizzes
from app.routers import live as live_router

from support import (
    FRONTEND_ORIGIN,
    assert_student_exam_payload_hides_answers,
    exam_environment,
    expire_due_sessions,
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


def receive_until_closed(socket) -> None:
    while True:
        socket.receive_json()


def assert_closed(socket, code: int = status.WS_1008_POLICY_VIOLATION) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        receive_until_closed(socket)
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
        lambda *_: None,
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
        # Reading the expired session does not finish it: the expiry loop does,
        # and the feed pushes the change.
        assert socket.receive_json()["data"]["status"] == "in_progress"
        expire_due_sessions(client)
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
        # Reading the expired session does not finish it: the expiry loop does,
        # and the feed pushes the change.
        assert socket.receive_json()["data"]["status"] == "in_progress"
        expire_due_sessions(client)
        final = socket.receive_json()
        assert final["data"]["status"] == "finished"
        assert_closed(socket, status.WS_1000_NORMAL_CLOSURE)


def test_live_snapshots_handle_missing_records(environment) -> None:
    client = environment["client"]
    websocket = SimpleNamespace(app=client.app)
    assert live.live_teacher_active_sessions_snapshot(websocket, 999999) is None
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


def test_live_quiz_websockets_push_session_transitions(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "live-quiz.db")) as client:
        environment = exam_environment(client)
        launched, participant_headers = launch_and_join(client, environment)
        teacher_token = environment["teacher_headers"]["Authorization"].removeprefix(
            "Bearer "
        )
        participant_token = participant_headers["X-Quiz-Token"]

        with client.websocket_connect(
            f"/api/quizzes/live/teacher/sessions/{launched['id']}",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as teacher_socket:
            teacher_socket.send_json({"token": teacher_token})
            teacher_state = teacher_socket.receive_json()
            assert teacher_state["type"] == "session"
            assert teacher_state["data"]["status"] == "waiting"
            assert teacher_state["data"]["participant_count"] == 1

            with client.websocket_connect(
                f"/api/quizzes/live/student/sessions/{launched['join_code']}",
                headers={"Origin": FRONTEND_ORIGIN},
            ) as student_socket:
                student_socket.send_json({"token": participant_token})
                student_state = student_socket.receive_json()
                assert student_state["type"] == "session"
                assert student_state["data"]["status"] == "waiting"

                started = client.post(
                    f"/api/quizzes/sessions/{launched['id']}/start",
                    headers=environment["teacher_headers"],
                )
                assert started.status_code == 200

                assert teacher_socket.receive_json()["data"]["status"] == "in_progress"
                pushed_student_state = student_socket.receive_json()["data"]
                assert pushed_student_state["status"] == "in_progress"
                assert pushed_student_state["question"] is not None
                assert_student_exam_payload_hides_answers(pushed_student_state)


def test_live_teacher_websockets_push_student_progress(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "live-quiz-progress.db")) as client:
        environment = exam_environment(client)
        bank_id = environment["question"]["question_bank_id"]
        second_question = client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=environment["teacher_headers"],
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Two plus two?",
                        "points": 2,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {"label": "Four", "is_correct": True, "points": 2},
                            {"label": "Five", "is_correct": False, "points": 0},
                        ],
                    }
                )
            },
        )
        assert second_question.status_code == status.HTTP_201_CREATED
        quiz = environment["quiz"]
        updated_quiz = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": quiz["title"],
                "source_language": quiz["source_language"],
                "question_bank_ids": [bank_id],
                "duration_seconds": quiz["duration_seconds"],
                "allow_previous_questions": quiz["allow_previous_questions"],
                "allow_negative_points": quiz["allow_negative_points"],
                "same_questions_for_all": quiz["same_questions_for_all"],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert updated_quiz.status_code == status.HTTP_200_OK
        launched, participant_headers = launch_and_join(client, environment)
        teacher_token = environment["teacher_headers"]["Authorization"].removeprefix(
            "Bearer "
        )

        with (
            client.websocket_connect(
                "/api/quizzes/live/teacher/sessions",
                headers={"Origin": FRONTEND_ORIGIN},
            ) as sessions_socket,
            client.websocket_connect(
                f"/api/quizzes/live/teacher/sessions/{launched['id']}",
                headers={"Origin": FRONTEND_ORIGIN},
            ) as session_socket,
        ):
            sessions_socket.send_json({"token": teacher_token})
            session_socket.send_json({"token": teacher_token})
            sessions_socket.receive_json()
            session_socket.receive_json()

            started = client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            )
            assert started.status_code == status.HTTP_200_OK
            sessions_socket.receive_json()
            session_socket.receive_json()

            student_state_url = f"/api/quizzes/student/sessions/{launched['join_code']}"
            student_state = client.get(
                student_state_url,
                headers=participant_headers,
            ).json()
            question = student_state["question"]
            answer_payload = (
                {"written_answer": "Student response"}
                if question["answer_mode"] == "written"
                else {"selected_choice_ids": [question["choices"][0]["id"]]}
            )
            submitted = client.post(
                f"{student_state_url}/answer",
                headers=participant_headers,
                json=answer_payload,
            )
            assert submitted.status_code == status.HTTP_200_OK

            session_update = session_socket.receive_json()
            assert session_update["type"] == "session"
            assert session_update["data"]["participants"][0]["answered_count"] == 1

            sessions_update = sessions_socket.receive_json()
            assert sessions_update["type"] == "active_sessions"
            assert sessions_update["data"][0]["participants"][0]["answered_count"] == 1


def test_live_teacher_session_pushes_student_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings_for(tmp_path / "live-student-join.db")) as client:
        environment = exam_environment(client)
        launched = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/launch",
            headers=environment["teacher_headers"],
            json={"class_id": environment["student_class"]["id"]},
        )
        assert launched.status_code == status.HTTP_201_CREATED
        launched_session = launched.json()
        teacher_token = environment["teacher_headers"]["Authorization"].removeprefix(
            "Bearer "
        )
        monkeypatch.setattr(
            "app.routers.live.LIVE_TEACHER_RECONCILIATION_SECONDS",
            0.01,
        )

        with client.websocket_connect(
            f"/api/quizzes/live/teacher/sessions/{launched_session['id']}",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as teacher_socket:
            teacher_socket.send_json({"token": teacher_token})
            initial = teacher_socket.receive_json()
            assert initial["type"] == "session"
            assert initial["data"]["participants"] == []

            # Simulate a notification handled by another worker. The teacher
            # socket must still reconcile its snapshot from the shared DB.
            monkeypatch.setattr(
                client.app.state.live_quiz_hub,
                "publish",
                lambda _topic: None,
            )
            joined = client.post(
                "/api/quizzes/join",
                headers=environment["student_headers"],
                json={"join_code": launched_session["join_code"]},
            )
            assert joined.status_code == status.HTTP_201_CREATED

            pushed = teacher_socket.receive_json()
            assert pushed["type"] == "session"
            assert pushed["data"]["participant_count"] == 1
            assert [
                participant["student_identifier"]
                for participant in pushed["data"]["participants"]
            ] == [environment["account"]["identifier"]]


def test_live_teacher_session_list_pushes_launch_and_removal(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "live-session-list.db")) as client:
        environment = exam_environment(client)
        teacher_token = environment["teacher_headers"]["Authorization"].removeprefix(
            "Bearer "
        )

        with client.websocket_connect(
            "/api/quizzes/live/teacher/sessions",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as socket:
            socket.send_json({"token": teacher_token})
            initial = socket.receive_json()
            assert initial == {"type": "active_sessions", "data": []}

            launched = client.post(
                f"/api/quizzes/{environment['quiz']['id']}/launch",
                headers=environment["teacher_headers"],
                json={"class_id": environment["student_class"]["id"]},
            )
            assert launched.status_code == status.HTTP_201_CREATED
            launched_session = launched.json()
            pushed = socket.receive_json()
            assert pushed["type"] == "active_sessions"
            assert [item["id"] for item in pushed["data"]] == [launched_session["id"]]

            cancelled = client.post(
                f"/api/quizzes/sessions/{launched_session['id']}/cancel",
                headers=environment["teacher_headers"],
            )
            assert cancelled.status_code == status.HTTP_204_NO_CONTENT
            assert socket.receive_json() == {
                "type": "active_sessions",
                "data": [],
            }


def test_live_quiz_websocket_rejects_untrusted_origin_and_token(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "live-quiz-auth.db")) as client:
        environment = exam_environment(client)
        launched, _ = launch_and_join(client, environment)
        path = f"/api/quizzes/live/teacher/sessions/{launched['id']}"

        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                path,
                headers={"Origin": "https://untrusted.example"},
            ),
        ):
            pass

        with client.websocket_connect(
            path,
            headers={"Origin": FRONTEND_ORIGIN},
        ) as socket:
            socket.send_json({"token": "invalid-token"})
            with pytest.raises(WebSocketDisconnect) as rejected:
                socket.receive_json()
            assert rejected.value.code == status.WS_1008_POLICY_VIOLATION


def test_live_socket_authentication_gate_is_bounded() -> None:
    hub = LiveQuizHub(max_pending_authentications=2)

    assert hub.begin_authentication()
    assert hub.begin_authentication()
    assert not hub.begin_authentication()

    hub.end_authentication()
    assert hub.begin_authentication()


def test_idle_live_socket_still_receives_a_keepalive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every live endpoint reconciles on a timer, so a quiet socket must ping.

    Without it an idle connection puts nothing on the wire, and a proxy that
    drops it leaves the dashboard stale behind a close the client never sees.
    """
    monkeypatch.setattr(live_router, "LIVE_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(live_router, "LIVE_TEACHER_RECONCILIATION_SECONDS", 0.1)
    with make_client(settings_for(tmp_path / "live-heartbeat.db")) as client:
        environment = exam_environment(client)
        teacher_token = environment["teacher_headers"]["Authorization"].removeprefix(
            "Bearer "
        )
        with client.websocket_connect(
            "/api/quizzes/live/teacher/sessions",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as socket:
            socket.send_json({"token": teacher_token})
            assert socket.receive_json() == {"type": "active_sessions", "data": []}
            # Nothing changes from here on, so only a keepalive can arrive.
            assert socket.receive_json() == {"type": "ping"}
