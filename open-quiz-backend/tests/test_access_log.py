"""Request logs, which never carry personal data."""

import json
from pathlib import Path

import pytest

from app import access_log
from app.access_log import route_template

from support import make_client, settings_for


def test_each_request_is_logged_without_address_or_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[str] = []
    monkeypatch.setattr(access_log.access_logger, "info", logged.append)
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
