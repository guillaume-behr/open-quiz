"""Unit tests for helpers that do not need a running application."""

import asyncio
import importlib
import json
import logging
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select

import app.audit
import app.config
from app.config import (
    Settings,
    get_settings,
    reject_predictable_secret,
    secure_private_file,
    validate_optional_public_url,
)
from app.database import postgres_url
from app.images import InvalidImage, normalize_image
from app.live_quiz import LiveQuizHub, websocket_origin_allowed
from app.middleware import RequestBodyLimitMiddleware
from app.question_responses import load_question_records
from app.schemas import (
    GradeLevelCreate,
    ProblemReportCreate,
    QuestionBankCreate,
    QuestionChoiceCreate,
    QuestionCreate,
    QuizCreate,
    StudentAccountCreate,
    StudentAccountUpdate,
    StudentClassCreate,
    TrainingQuestionBankSelection,
)
from app.security import create_access_token
from app.services.grading import compute_final_scores, decoded_answer_data
from app.student_accounts import owned_student_account

from support import (
    ADMIN_PASSWORD,
    JWT_SECRET,
    STUDENT_CREDENTIAL_ENCRYPTION_KEY,
    TOTP_ENCRYPTION_KEY,
    VALID_PNG,
    settings_for,
)

SETTINGS_VALUES: dict[str, Any] = {
    "database_url": "postgresql+psycopg://user:a-long-enough-password@localhost/db",
    "jwt_secret": JWT_SECRET,
    "totp_encryption_key": TOTP_ENCRYPTION_KEY,
    "student_credential_encryption_key": STUDENT_CREDENTIAL_ENCRYPTION_KEY,
    "admin_username": "root-admin",
    "admin_password": ADMIN_PASSWORD,
    "frontend_origin": "http://localhost:5173",
    "environment": "test",
}


def make_settings(**overrides: Any) -> Settings:
    return Settings(**{**SETTINGS_VALUES, **overrides})


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"totp_encryption_key": "short"},
            "TOTP_ENCRYPTION_KEY must contain at least 32",
        ),
        (
            {"totp_encryption_key": "replace-with-a-long-random-totp-key"},
            "TOTP_ENCRYPTION_KEY is still set",
        ),
        (
            {"student_credential_encryption_key": "short"},
            "STUDENT_CREDENTIAL_ENCRYPTION_KEY must contain at least 32",
        ),
        (
            {
                "student_credential_encryption_key": "replace-with-a-long-student-credential-key"
            },
            "STUDENT_CREDENTIAL_ENCRYPTION_KEY is still set",
        ),
        (
            {"student_credential_encryption_key": JWT_SECRET},
            "must be distinct from other secrets",
        ),
        ({"admin_password": "short"}, "at least 16 characters"),
        ({"admin_password": "x" * 257}, "at most 256 characters"),
        ({"access_token_minutes": 0}, "ACCESS_TOKEN_MINUTES"),
        ({"refresh_token_days": 31}, "REFRESH_TOKEN_DAYS"),
        ({"login_attempts": 2}, "LOGIN_ATTEMPTS"),
        ({"login_window_seconds": 59}, "LOGIN_WINDOW_SECONDS"),
        ({"global_login_attempts": 49}, "GLOBAL_LOGIN_ATTEMPTS"),
        ({"global_login_window_seconds": 9}, "GLOBAL_LOGIN_WINDOW_SECONDS"),
        ({"quiz_result_retention_days": 0}, "QUIZ_RESULT_RETENTION_DAYS"),
        ({"training_result_retention_days": 0}, "TRAINING_RESULT_RETENTION_DAYS"),
        ({"abandoned_session_retention_days": 91}, "ABANDONED_SESSION_RETENTION"),
        ({"problem_report_attempts": 0}, "PROBLEM_REPORT_ATTEMPTS"),
        ({"problem_report_window_seconds": 59}, "PROBLEM_REPORT_WINDOW_SECONDS"),
        ({"problem_report_retention_days": 366}, "PROBLEM_REPORT_RETENTION_DAYS"),
        ({"max_request_body_bytes": 1023}, "MAX_REQUEST_BODY_BYTES"),
        ({"frontend_origin": "ftp://example.org"}, "must be an HTTP(S) origin"),
        (
            {"frontend_origin": "https://user:secret@example.org"},
            "must not contain credentials",
        ),
        ({"frontend_origin": "https://example.org:99999"}, "invalid port"),
        ({"frontend_origin": "https://example.org/"}, "trailing slash"),
        ({"environment": "staging"}, "APP_ENV"),
        ({"database_url": "sqlite:///quiz.db"}, "DATABASE_URL must use PostgreSQL"),
    ],
)
def test_settings_reject_invalid_values(overrides: dict[str, Any], message) -> None:
    with pytest.raises(
        ValueError, match=message.replace("(", r"\(").replace(")", r"\)")
    ):
        make_settings(**overrides)


@pytest.mark.parametrize(
    ("value", "environment", "message"),
    [
        ("https://example.org/\x07", "test", "control characters"),
        ("javascript:alert(1)", "test", "absolute HTTP"),
        ("https://user:secret@example.org", "test", "credentials"),
        ("https://example.org:70000", "test", "invalid port"),
        ("http://example.org", "production", "must use HTTPS"),
    ],
)
def test_optional_public_urls_are_validated(
    value: str, environment: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_optional_public_url("ACCESSIBILITY_SCHEME_URL", value, environment)


def test_optional_public_urls_accept_https_in_production() -> None:
    validate_optional_public_url("NAME", "https://example.org/plan", "production")
    settings = make_settings(
        accessibility_scheme_url="https://example.org/scheme",
        accessibility_action_plan_url="http://example.org/plan",
    )
    assert settings.accessibility_action_plan_url == "http://example.org/plan"


def test_repeated_secrets_are_rejected() -> None:
    with pytest.raises(ValueError, match="repeated pattern"):
        reject_predictable_secret(
            "SECRET", "abcdefghijkl" * 4, minimum_unique_characters=10
        )


def test_securing_a_private_file_reports_permission_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "secret"
    private.write_text("value", encoding="utf-8")

    def refuse(self: Path, mode: int) -> None:
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(Path, "chmod", refuse)
    with pytest.raises(RuntimeError, match="Unable to secure private file"):
        secure_private_file(private)


def test_settings_are_read_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.config, "ENV_FILE", tmp_path / ".env")
    environment = {
        "DATABASE_URL": SETTINGS_VALUES["database_url"],
        "APP_ENV": "test",
        "FRONTEND_ORIGIN": "https://quiz.example.org",
        "ACCESS_TOKEN_MINUTES": "7",
        "ACCESSIBILITY_CONTACT": "access@example.org",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = get_settings()

    assert settings.frontend_origin == "https://quiz.example.org"
    assert settings.access_token_minutes == 7
    assert settings.accessibility_contact == "access@example.org"
    assert settings.cookie_secure is False

    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        get_settings()


@pytest.mark.parametrize(
    ("url", "password", "message"),
    [
        ("mysql://user:a-long-enough-password@localhost/db", None, "PostgreSQL"),
        (
            "postgresql+asyncpg://user:a-long-enough-password@localhost/db",
            None,
            "Psycopg driver",
        ),
        ("postgresql://user@localhost/db", None, "POSTGRES_PASSWORD must be set"),
        ("postgresql://user:short@localhost/db", None, "at least 16 characters"),
        (
            "postgresql://user:replace-with-a-database-password@localhost/db",
            None,
            "non-example value",
        ),
    ],
)
def test_database_urls_must_use_a_strong_postgres_password(
    url: str,
    password: str | None,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValueError, match=message):
        postgres_url(url)


def test_database_url_reads_a_missing_password_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-long-enough-password")
    url = postgres_url("postgresql://user@localhost/db")
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "a-long-enough-password"


def test_audit_logger_keeps_an_existing_handler() -> None:
    logger = logging.getLogger("open_quiz.audit")
    handlers = list(logger.handlers)
    importlib.reload(app.audit)
    assert logger.handlers == handlers


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


@pytest.mark.parametrize("stored", [None, "not json", "[1, 2]"])
def test_unreadable_answer_payloads_are_treated_as_empty(stored) -> None:
    assert decoded_answer_data(SimpleNamespace(answer_data=stored)) == {}


class _ScriptedSession:
    def __init__(self, *results: list[Any]) -> None:
        self._results = list(results)

    def scalars(self, _statement: object) -> list[Any]:
        return self._results.pop(0)


def test_final_scores_handle_deleted_and_ungraded_written_questions() -> None:
    deleted = SimpleNamespace(
        question_id=1, answer_data="{}", score=3.0, is_graded=False
    )
    ungraded = SimpleNamespace(
        question_id=2, answer_data="{}", score=4.0, is_graded=False
    )
    graded = SimpleNamespace(question_id=2, answer_data="{}", score=4.0, is_graded=True)
    written = SimpleNamespace(id=2, answer_mode="written")
    session = _ScriptedSession([deleted, ungraded, graded], [], [written])

    compute_final_scores(SimpleNamespace(id=1, allow_negative_points=False), session)

    assert (deleted.score, deleted.is_graded) == (0, True)
    assert (ungraded.score, ungraded.is_graded) == (0, False)
    assert (graded.score, graded.is_graded) == (4.0, True)


def test_final_scores_without_answers_do_not_load_choices() -> None:
    session = _ScriptedSession([], [])
    compute_final_scores(SimpleNamespace(id=1, allow_negative_points=False), session)
    assert session._results == []


def test_loading_no_question_records_skips_the_database() -> None:
    assert load_question_records([], session=None) == ({}, {})


def test_missing_student_account_is_not_found() -> None:
    session = SimpleNamespace(scalar=lambda _statement: None)
    with pytest.raises(HTTPException) as error:
        owned_student_account(1, 2, session)
    assert error.value.status_code == 404


def test_normalized_image_must_fit_the_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.images.MAX_IMAGE_BYTES", len(VALID_PNG))
    monkeypatch.setattr(
        Image.Image,
        "save",
        lambda self, output, **_: output.write(b"x" * (len(VALID_PNG) + 1)),
    )
    with pytest.raises(InvalidImage, match="trop volumineuse"):
        normalize_image(VALID_PNG, "image/png")


def test_access_tokens_never_outlive_their_session() -> None:
    from time import time

    session_expires_at = int(time()) + 30
    token = create_access_token(
        1, JWT_SECRET, 15, "version", session_expires_at=session_expires_at
    )
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    assert payload["exp"] == session_expires_at
    unbounded = jwt.decode(
        create_access_token(1, JWT_SECRET, 15, "version"),
        JWT_SECRET,
        algorithms=["HS256"],
    )
    assert unbounded["exp"] > session_expires_at


def test_body_limit_ignores_non_body_messages() -> None:
    incoming = iter(
        [
            {"type": "http.disconnect"},
            {"type": "http.request", "body": b"{}", "more_body": False},
        ]
    )
    received: list[str] = []

    async def receive() -> dict[str, Any]:
        return next(incoming)

    async def send(message: dict[str, Any]) -> None:
        received.append(message["type"])

    async def downstream(scope, receive, send) -> None:
        received.append((await receive())["type"])
        received.append((await receive())["type"])

    middleware = RequestBodyLimitMiddleware(
        downstream, default_limit=1024, session_factory=None
    )
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "path": "/api/x", "headers": []},
            receive,
            send,
        )
    )
    assert received == ["http.disconnect", "http.request"]


def valid_question(**overrides: Any) -> dict[str, Any]:
    return {
        "prompt": "Pick one",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [
            {"label": "Right", "is_correct": True},
            {"label": "Wrong", "is_correct": False},
        ],
        **overrides,
    }


def counts(easy: int) -> dict[str, int]:
    return {
        "easy_question_count": easy,
        "medium_question_count": 0,
        "hard_question_count": 0,
    }


def written_question(**overrides: Any) -> dict[str, Any]:
    return valid_question(
        **{
            "answer_mode": "written",
            "choices": [{"label": "Answer", "is_correct": True}],
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("model", "payload", "message"),
    [
        (ProblemReportCreate, {"message": "  a    ", "page_path": "/"}, "5 car"),
        (GradeLevelCreate, {"name": "   "}, "niveau"),
        (StudentAccountCreate, {"first_name": " ", "last_name": "B"}, "nom"),
        (
            StudentAccountUpdate,
            {"identifier": "pupil", "display_name": "  "},
            "nom",
        ),
        (StudentClassCreate, {"name": " ", "grade_level": "5e"}, "vide"),
        (QuestionBankCreate, {"grade_level": "5e", "chapter": "  "}, "vide"),
        (
            TrainingQuestionBankSelection,
            {
                "question_banks": [
                    {"question_bank_id": 1, "question_count": 1},
                    {"question_bank_id": 1, "question_count": 2},
                ]
            },
            "une fois",
        ),
        (
            TrainingQuestionBankSelection,
            {
                "question_banks": [{"question_bank_id": 1, "question_count": 1}],
                "question_bank_ids": [2],
            },
            "un seul format",
        ),
        (TrainingQuestionBankSelection, {"question_bank_ids": [0]}, "invalides"),
        (QuestionChoiceCreate, {"label": "A", "code_language": "python"}, "ensemble"),
        (QuestionCreate, valid_question(prompt="  "), "vide"),
        (
            QuestionCreate,
            valid_question(choices=[{"label": "Only", "is_correct": True}]),
            "deux propositions",
        ),
        (
            QuestionCreate,
            written_question(
                choices=[
                    {"label": "A", "is_correct": True},
                    {"label": "B", "is_correct": False},
                ]
            ),
            "réponse attendue",
        ),
        (
            QuestionCreate,
            written_question(answer_mode_disclosed=False),
            "masqué",
        ),
        (QuestionCreate, valid_question(response_language="python"), "langage"),
        (QuestionCreate, valid_question(allow_code_execution=True), "exécution"),
        (
            QuestionCreate,
            written_question(allow_code_execution=True, response_language="sql"),
            "format Python",
        ),
        (
            QuestionCreate,
            valid_question(
                choices=[
                    {"label": "A", "is_correct": False},
                    {"label": "B", "is_correct": False},
                ]
            ),
            "au moins une bonne",
        ),
        (
            QuestionCreate,
            valid_question(
                choices=[
                    {"label": "A", "is_correct": True},
                    {"label": "B", "is_correct": True},
                ]
            ),
            "seule bonne",
        ),
        (QuestionCreate, valid_question(code_content="print(1)"), "ensemble"),
        (
            QuizCreate,
            {"title": "   ", "question_bank_ids": [1], **counts(1)},
            "titre",
        ),
        (
            QuizCreate,
            {"title": "Quiz", "question_bank_ids": [1], **counts(0)},
            "au moins une question",
        ),
        (
            QuizCreate,
            {
                "title": "Quiz",
                "question_bank_ids": [1],
                "easy_question_count": 100,
                "medium_question_count": 100,
                "hard_question_count": 1,
            },
            "plus de 200",
        ),
        (
            QuizCreate,
            {"title": "Quiz", "question_bank_ids": [1, 1], **counts(1)},
            "une fois",
        ),
    ],
)
def test_schemas_reject_invalid_input(model, payload, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload)


def test_questions_accept_a_python_code_execution_answer() -> None:
    question = QuestionCreate.model_validate(
        written_question(
            allow_code_execution=True,
            response_language="python",
            code_language="python",
            code_content="print(1)\r\n",
        )
    )
    assert question.code_content == "print(1)\n"
    assert (
        StudentAccountUpdate(
            identifier="pupil", display_name="Pupil", password=None
        ).password
        is None
    )
    assert TrainingQuestionBankSelection.model_validate(
        {"question_bank_ids": [1, 2]}
    ).question_bank_ids == [1, 2]


def test_reset_two_factor_script_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    settings = settings_for(tmp_path / "reset-script")
    monkeypatch.setattr(app.config, "get_settings", lambda: settings)
    script = Path(__file__).resolve().parent.parent / "scripts/reset_two_factor.py"

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

    from app.database import build_session_factory
    from app.models import User

    with build_session_factory(settings.database_url)() as session:
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
        app.audit, "audit_event", lambda event, **_: events.append(event)
    )
    monkeypatch.setattr("sys.argv", ["reset_two_factor.py", "reset.me", "--yes"])
    runpy.run_path(str(script), run_name="__main__")
    assert events == ["security.two_factor_reset_by_script"]


def test_rotate_local_secrets_replaces_secrets_and_revokes_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import scripts.rotate_local_secrets as rotation
    from app.database import build_session_factory
    from app.models import RefreshSession, User

    settings = settings_for(tmp_path / "rotate-secrets")
    session_factory = build_session_factory(settings.database_url)
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
    assert rotated[1].startswith("JWT_SECRET=") and rotated[1] != "JWT_SECRET=old"
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

    def closed(code: int) -> ConnectionClosed:
        return ConnectionClosed(Close(code, "closed"), None)

    sockets = [
        _FakeWebSocket(closed(1008)),
        _FakeWebSocket(closed(1011)),
        _FakeWebSocket(None),
    ]
    monkeypatch.setattr(smoke, "connect", lambda *_, **__: sockets.pop(0))
    asyncio.run(smoke.check_websocket_proxy())
    with pytest.raises(RuntimeError, match="Unexpected WebSocket close code"):
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
