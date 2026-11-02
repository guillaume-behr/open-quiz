"""Operational metrics and request logs, which never carry personal data."""

import json
from pathlib import Path

import pytest

from app import metrics
from app.config import boolean_environment
from app.metrics import route_template

from support import (
    FRONTEND_ORIGIN,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)


def sample(text: str, name: str, **labels: str) -> float:
    """One sample of the Prometheus text format; 0 for a series not seen yet.

    The metrics belong to the process, so earlier tests may have moved them:
    tests compare a value before and after what they do.
    """
    rendered = ",".join(f'{key}="{value}"' for key, value in labels.items())
    prefix = f"{name}{{{rendered}}} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0


def test_metrics_are_off_by_default(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "metrics-off")) as client:
        assert client.get("/metrics").status_code == 404


def test_metrics_describe_requests_by_route_template(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "metrics-on", metrics_enabled=True)
    with make_client(settings) as client:
        environment = exam_environment(client)
        launched, _ = launch_and_join(client, environment)
        requests_before = sample(
            client.get("/metrics").text,
            "open_quiz_http_requests_total",
            method="GET",
            route="/api/quizzes/sessions/{session_id}",
            status="200",
        )
        client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        )
        exposed = client.get("/metrics")
        assert exposed.status_code == 200
        assert exposed.headers["content-type"].startswith("text/plain")
        text = exposed.text
        assert (
            sample(
                text,
                "open_quiz_http_requests_total",
                method="GET",
                route="/api/quizzes/sessions/{session_id}",
                status="200",
            )
            == requests_before + 1
        )
        # The session's join code and id appear in no label.
        assert launched["join_code"] not in text
        assert f"/sessions/{launched['id']}" not in text
        assert sample(text, "open_quiz_database_connections", state="open") >= 1
        assert "open_quiz_retention_duration_seconds_count" in text


def test_metrics_count_rate_limit_rejections(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "metrics-limits", metrics_enabled=True, problem_report_attempts=1
    )
    with make_client(settings) as client:
        report = {"message": "The timer is wrong", "page_path": "/"}
        assert client.post("/api/problem-reports", json=report).status_code == 201
        before = sample(
            client.get("/metrics").text,
            "open_quiz_rate_limit_rejections_total",
            limiter="problem-report",
        )
        assert client.post("/api/problem-reports", json=report).status_code == 429
        assert (
            sample(
                client.get("/metrics").text,
                "open_quiz_rate_limit_rejections_total",
                limiter="problem-report",
            )
            == before + 1
        )


def test_open_websockets_are_counted_by_feed(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "metrics-sockets", metrics_enabled=True)
    with make_client(settings) as client:
        environment = exam_environment(client)
        token = environment["teacher_headers"]["Authorization"].removeprefix("Bearer ")

        def open_teacher_feeds() -> float:
            return sample(
                client.get("/metrics").text,
                "open_quiz_websockets_active",
                feed="teacher_sessions",
            )

        with client.websocket_connect(
            "/api/quizzes/live/teacher/sessions",
            headers={"Origin": FRONTEND_ORIGIN},
        ) as socket:
            socket.send_json({"token": token})
            socket.receive_json()
            assert open_teacher_feeds() == 1
        assert open_teacher_feeds() == 0


def test_each_request_is_logged_without_address_or_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[str] = []
    monkeypatch.setattr(metrics.access_logger, "info", logged.append)
    with make_client(settings_for(tmp_path / "access-log")) as client:
        client.get("/api/quizzes/student/sessions/ABC123")
        client.get("/api/no-such-route")
    entries = [json.loads(line) for line in logged]
    assert {
        "event": "http.request",
        "method": "GET",
        "route": "/api/quizzes/student/sessions/{join_code}",
        "status": 401,
    }.items() <= entries[-2].items()
    assert entries[-1]["route"] == "unmatched"
    assert entries[-1]["status"] == 404
    for entry in entries:
        assert set(entry) == {"event", "method", "route", "status", "duration_ms"}
        assert "ABC123" not in json.dumps(entry)
        assert "testclient" not in json.dumps(entry)


def test_a_scope_without_a_route_is_labelled_unmatched() -> None:
    assert route_template({}) == "unmatched"


def test_metrics_enabled_must_be_a_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METRICS_ENABLED", "TRUE")
    assert boolean_environment("METRICS_ENABLED") is True
    monkeypatch.delenv("METRICS_ENABLED")
    assert boolean_environment("METRICS_ENABLED") is False
    monkeypatch.setenv("METRICS_ENABLED", "yes")
    with pytest.raises(ValueError, match="METRICS_ENABLED must be true or false"):
        boolean_environment("METRICS_ENABLED")
