"""The command-line scripts: 2FA reset, secret rotation and the network smoke check."""

import asyncio
import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

import app.core.audit
import app.core.config

from support import settings_for


def test_reset_two_factor_script_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    settings = settings_for(tmp_path / "reset-script")
    monkeypatch.setattr(app.core.config, "get_settings", lambda: settings)
    script = Path(__file__).resolve().parent.parent / "scripts/reset_two_factor.py"

    from app.models import User

    from support import session_factory_for

    # The script does not migrate: the application did when it started.
    session_factory = session_factory_for(settings.database_url)
    monkeypatch.setattr("sys.argv", ["reset_two_factor.py", "nobody"])
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    with pytest.raises(SystemExit) as aborted:
        runpy.run_path(str(script), run_name="__main__")
    assert aborted.value.code == 1
    assert "Aborted." in capsys.readouterr().err

    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    with pytest.raises(SystemExit) as missing:
        runpy.run_path(str(script), run_name="__main__")
    assert missing.value.code == 2
    assert "user not found" in capsys.readouterr().err

    with session_factory() as session:
        session.add(
            User(
                username="reset.me",
                display_name="Reset Me",
                password_hash="unused",
            )
        )
        session.commit()
    events: list[str] = []
    monkeypatch.setattr(
        app.core.audit, "audit_event", lambda event, **_: events.append(event)
    )
    monkeypatch.setattr("sys.argv", ["reset_two_factor.py", "reset.me", "--yes"])
    runpy.run_path(str(script), run_name="__main__")
    assert events == ["security.two_factor_reset_by_script"]


def test_rotate_local_secrets_replaces_secrets_and_revokes_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import scripts.rotate_local_secrets as rotation
    from app.models import RefreshSession, User

    from support import session_factory_for

    settings = settings_for(tmp_path / "rotate-secrets")
    session_factory = session_factory_for(settings.database_url)
    with session_factory() as session:
        user = User(username="teacher", display_name="T", password_hash="unused")
        session.add(user)
        session.flush()
        session.add(RefreshSession(token_hash="hash", user_id=user.id, expires_at=1))
        session.commit()

    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nJWT_SECRET=old\nAPP_ENV=test\n", encoding="utf-8")
    monkeypatch.setattr(rotation, "ENV_FILE", env_file)
    monkeypatch.setattr(rotation, "get_settings", lambda: settings)

    rotation.rotate()

    rotated = env_file.read_text(encoding="utf-8").splitlines()
    assert rotated[0] == "# comment"
    assert rotated[1].startswith("JWT_SECRET=")
    assert rotated[1] != "JWT_SECRET=old"
    assert rotated[2] == "APP_ENV=test"
    assert rotated[3].startswith("ADMIN_PASSWORD=")
    backups = list(tmp_path.glob(".env.*.bak"))
    assert [backup.read_text(encoding="utf-8") for backup in backups] == [
        "# comment\nJWT_SECRET=old\nAPP_ENV=test\n"
    ]
    assert "Secrets rotated" in capsys.readouterr().out
    with session_factory() as session:
        assert session.scalar(select(RefreshSession.revoked_at)) is not None


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self._payload


class _FakeWebSocket:
    def __init__(self, error: Exception | None) -> None:
        self.error = error
        self.sent: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if self.error is not None:
            raise self.error
        return "unexpected"


def test_container_network_smoke_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    from websockets.exceptions import ConnectionClosed
    from websockets.frames import Close

    import scripts.container_network_smoke as smoke

    requests: list[Any] = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _FakeResponse(responses.pop(0))

    responses: list[object] = [{"status": "ok"}, {"status": "down"}]
    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    smoke.check_http_proxy()
    assert requests[0].get_header("X-forwarded-proto") == "https"
    with pytest.raises(RuntimeError, match="Unexpected health response"):
        smoke.check_http_proxy()

    def closed(code: int | None) -> ConnectionClosed:
        frame = None if code is None else Close(code, "closed")
        return ConnectionClosed(frame, None)

    sockets = [
        _FakeWebSocket(closed(1008)),
        _FakeWebSocket(closed(1011)),
        _FakeWebSocket(closed(None)),
        _FakeWebSocket(None),
    ]
    monkeypatch.setattr(smoke, "connect", lambda *_, **__: sockets.pop(0))
    asyncio.run(smoke.check_websocket_proxy())
    with pytest.raises(RuntimeError, match="Unexpected WebSocket close code: 1011"):
        asyncio.run(smoke.check_websocket_proxy())
    with pytest.raises(RuntimeError, match="Unexpected WebSocket close code: None"):
        asyncio.run(smoke.check_websocket_proxy())
    with pytest.raises(RuntimeError, match="were not rejected"):
        asyncio.run(smoke.check_websocket_proxy())

    calls: list[str] = []
    monkeypatch.setattr(smoke, "check_http_proxy", lambda: calls.append("http"))

    async def websocket_check() -> None:
        calls.append("websocket")

    monkeypatch.setattr(smoke, "check_websocket_proxy", websocket_check)
    smoke.main()
    assert calls == ["http", "websocket"]
