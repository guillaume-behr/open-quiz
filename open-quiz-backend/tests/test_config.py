"""Configuration and HTTP safeguards: settings, secrets, request limits and headers."""

import asyncio
import json
import os
import stat
import tomllib
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

import main
from app.config import secure_private_file, write_private_file
from app.database import postgres_url
from app.middleware import LARGE_QUESTION_BODY_BYTES, RequestBodyLimitMiddleware
from main import create_app

from support import (
    FRONTEND_ORIGIN,
    JWT_SECRET,
    TEST_CLIENT_BACKEND_OPTIONS,
    exam_environment,
    login_admin,
    make_client,
    settings_for,
)


def test_health_checks_database_readiness(tmp_path: Path) -> None:
    database = tmp_path / "health"
    with make_client(settings_for(database)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_rate_limit_expiration_has_a_supporting_index(tmp_path: Path) -> None:
    database = tmp_path / "rate-limit-index"
    settings = settings_for(database)
    with make_client(settings):
        pass

    engine = create_engine(postgres_url(settings.database_url))
    try:
        indexes = {
            index["name"] for index in inspect(engine).get_indexes("login_rate_limits")
        }
    finally:
        engine.dispose()
    assert "ix_login_rate_limits_window_started_at" in indexes


def test_cors_allows_class_training_update_preflight(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "cors.db")) as client:
        response = client.options(
            "/api/quizzes/training/classes/1/question-banks",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_private_file_permissions_are_restricted(tmp_path: Path) -> None:
    private_file = tmp_path / ".env"
    private_file.write_text("SECRET=value\n", encoding="utf-8")
    private_file.chmod(0o644)

    secure_private_file(private_file)

    if os.name == "posix":
        assert private_file.stat().st_mode & 0o077 == 0


def test_public_information_describes_instance_settings(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "public-information.db",
        legal_host_name="Test host",
        legal_host_address="Test host address",
        legal_host_phone="+33 1 23 45 67 89",
        privacy_controller_name="Test controller",
        accessibility_contact="Accessibility contact",
        refresh_token_days=9,
        quiz_result_retention_days=120,
        training_result_retention_days=45,
    )
    with make_client(settings) as client:
        response = client.get("/api/public-information")

    assert response.status_code == 200
    assert "publisher" not in response.json()
    assert response.json()["host"] == {
        "name": "Test host",
        "address": "Test host address",
        "phone": "+33 1 23 45 67 89",
    }
    assert response.json()["privacy"]["controller_name"] == "Test controller"
    assert response.json()["privacy"]["quiz_result_retention_days"] == 120
    assert response.json()["privacy"]["training_result_retention_days"] == 45
    assert response.json()["cookies"]["authentication_max_age_days"] == 9
    assert response.json()["accessibility"]["contact"] == "Accessibility contact"
    assert response.headers["cache-control"] == "no-store"


def test_production_allows_missing_public_information(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "missing-public-information.db",
        frontend_origin="https://quiz.example.test",
        environment="production",
    )

    assert settings.legal_host_name == ""
    assert settings.privacy_controller_name == ""
    missing = main.warn_missing_public_information(settings)
    assert "PRIVACY_CONTROLLER_NAME" in missing
    assert "LEGAL_HOST_NAME" in missing
    # The legal notice calls the host incomplete without a phone number.
    assert "LEGAL_HOST_PHONE" in missing
    # Optional for the software, whatever the operator's own situation asks.
    assert "PRIVACY_DPO_CONTACT" not in missing
    assert "ACCESSIBILITY_CONTACT" not in missing


def test_development_does_not_warn_about_public_information(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "development-public-information.db")

    assert main.warn_missing_public_information(settings) == []


def test_request_size_and_authenticated_cache_controls(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", max_request_body_bytes=1024)
    with make_client(app_settings) as client:
        oversized = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": "x" * 2048},
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"]["code"] == "REQUEST_BODY_TOO_LARGE"
        assert oversized.headers["cache-control"] == "no-store"

        gated_upload = client.post(
            "/api/question-banks/import",
            content=b"x" * 2048,
            headers={"Content-Type": "application/json"},
        )
        assert gated_upload.status_code == 401
        assert gated_upload.headers["cache-control"] == "no-store"
        assert gated_upload.headers["access-control-allow-origin"] == FRONTEND_ORIGIN

        headers = login_admin(client)
        admin_upload = client.post(
            "/api/question-banks/import",
            headers=headers,
            content=b"x" * 2048,
        )
        assert admin_upload.status_code == 403
        users = client.get("/api/admin/users", headers=headers)
        assert users.status_code == 200
        assert users.headers["cache-control"] == "no-store"


def test_streamed_request_body_is_limited_without_buffering() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"x" * 600, "more_body": True},
            {"type": "http.request", "body": b"x" * 600, "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(incoming)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body", False):
                return

    middleware = RequestBodyLimitMiddleware(
        downstream,
        default_limit=1024,
        session_factory=None,
    )
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": [],
            },
            receive,
            send,
        )
    )

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 413


def test_elevated_body_limit_only_matches_large_question_routes() -> None:
    assert LARGE_QUESTION_BODY_BYTES >= 64 * 1024 * 1024 * 4 // 3

    elevated_paths = (
        "/api/question-banks/import",
        "/api/question-banks/12/questions",
        "/api/question-banks/questions/34/update",
    )
    for path in elevated_paths:
        assert RequestBodyLimitMiddleware._uses_elevated_limit(
            {"type": "http", "method": "POST", "path": path}
        )

    regular_paths = (
        "/api/question-banks/12/update",
        "/api/question-banks-extra/import",
        "/api/question-banks/questions/not-an-id/update",
    )
    for path in regular_paths:
        assert not RequestBodyLimitMiddleware._uses_elevated_limit(
            {"type": "http", "method": "POST", "path": path}
        )


def test_production_redirects_to_https_before_body_authentication(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(
        tmp_path / "https-first.db",
        environment="production",
        frontend_origin="https://quiz.example.test",
    )
    with TestClient(
        create_app(app_settings),
        follow_redirects=False,
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
        response = client.post(
            "/api/question-banks/import",
            content=b"x" * 2048,
        )

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_rejects_weak_or_insecure_production_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ADMIN_USERNAME"):
        settings_for(tmp_path / "long-admin-username.db", admin_username="a" * 81)

    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        settings_for(tmp_path / "long-admin-password.db", admin_password="aB1-" * 65)

    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings_for(tmp_path / "weak.db", jwt_secret="short")

    with pytest.raises(ValueError, match="must be distinct"):
        settings_for(
            tmp_path / "reused-secret.db",
            totp_encryption_key=JWT_SECRET,
        )

    with pytest.raises(ValueError, match="character variety"):
        settings_for(
            tmp_path / "predictable-secret.db",
            jwt_secret="a" * 64,
        )

    with pytest.raises(ValueError, match="repeated pattern"):
        settings_for(
            tmp_path / "repeated-secret.db",
            jwt_secret="0123456789abcdef" * 4,
        )

    with pytest.raises(ValueError, match="HTTPS"):
        settings_for(
            tmp_path / "production.db",
            environment="production",
        )

    with pytest.raises(ValueError, match="credentials"):
        settings_for(
            tmp_path / "credential-origin.db",
            frontend_origin="https://user:password@example.com",
        )

    with pytest.raises(ValueError, match="trailing slash"):
        settings_for(
            tmp_path / "trailing-slash-origin.db",
            frontend_origin="https://example.com/",
        )

    with pytest.raises(ValueError, match="invalid port"):
        settings_for(
            tmp_path / "invalid-port-origin.db",
            frontend_origin="https://example.com:not-a-port",
        )

    with pytest.raises(ValueError, match="ACCESSIBILITY_SCHEME_URL"):
        settings_for(
            tmp_path / "unsafe-accessibility-url.db",
            accessibility_scheme_url="javascript:alert(document.cookie)",
        )

    with pytest.raises(ValueError, match="HTTPS"):
        settings_for(
            tmp_path / "insecure-accessibility-url.db",
            environment="production",
            frontend_origin="https://quiz.example.test",
            accessibility_action_plan_url="http://example.test/action-plan",
        )


@pytest.mark.parametrize(
    ("setting_name", "value", "expected_message"),
    [
        ("global_login_attempts", 49, "GLOBAL_LOGIN_ATTEMPTS"),
        ("global_login_window_seconds", 9, "GLOBAL_LOGIN_WINDOW_SECONDS"),
        ("quiz_join_attempts", 4, "QUIZ_JOIN_ATTEMPTS"),
        ("quiz_participant_attempts", 29, "QUIZ_PARTICIPANT_ATTEMPTS"),
        ("quiz_violation_attempts", 4, "QUIZ_VIOLATION_ATTEMPTS"),
        ("quiz_rate_window_seconds", 9, "QUIZ_RATE_WINDOW_SECONDS"),
    ],
)
def test_rejects_unsafe_quiz_rate_limit_configuration(
    tmp_path: Path,
    setting_name: str,
    value: int,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        settings_for(
            tmp_path / f"{setting_name}.db",
            **{setting_name: value},
        )


def test_the_version_has_one_source_per_package() -> None:
    """Each package states its version once, and the two must not drift.

    The API reads pyproject.toml and the footer receives package.json's
    version at build time. A release that bumps only one of them ships an API
    reporting one version and an interface built as another.
    """
    repository = Path(__file__).resolve().parent.parent.parent
    frontend_root = repository / "open-quiz-frontend"
    backend = tomllib.loads(
        (repository / "open-quiz-backend" / "pyproject.toml").read_text()
    )["project"]["version"]
    frontend = json.loads((frontend_root / "package.json").read_text())["version"]
    assert backend == frontend, f"pyproject {backend}, package.json {frontend}"
    assert main.app.version == backend
    layout = (frontend_root / "src" / "layouts" / "main-layout.tsx").read_text()
    assert '"app-version", { version: __APP_VERSION__ }' in layout
    vite_config = (frontend_root / "vite.config.ts").read_text()
    assert "__APP_VERSION__: JSON.stringify(version)" in vite_config


def test_secret_files_are_never_readable_by_other_accounts(tmp_path: Path) -> None:
    """Rotation copies every current secret into a backup beside .env.

    Restricting the file after creating it leaves it exposed for as long as
    the write takes, with the process umask deciding who may read it. On a
    shared host that is every local account, so the mode has to be set when
    the file is created.
    """
    previous_umask = os.umask(0o022)
    try:
        secret_file = tmp_path / ".env.1234.bak"
        write_private_file(secret_file, "JWT_SECRET=a-real-secret\n")
    finally:
        os.umask(previous_umask)

    assert secret_file.read_text() == "JWT_SECRET=a-real-secret\n"
    mode = stat.S_IMODE(secret_file.stat().st_mode)
    assert not mode & 0o077, f"secret file is readable by others: {oct(mode)}"

    # An existing path is never silently overwritten.
    with pytest.raises(FileExistsError):
        write_private_file(secret_file, "other")


@pytest.mark.parametrize("content_length", ["not-a-number", "-1", "12.5", ""])
def test_a_malformed_content_length_is_rejected(content_length: str) -> None:
    """The body limit is decided from this header before anything is read.

    A value the middleware cannot compare must be refused outright rather than
    fall through to an unbounded read.
    """
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def downstream(scope, receive, send) -> None:
        raise AssertionError("the request must not reach the application")

    middleware = RequestBodyLimitMiddleware(
        downstream,
        default_limit=1024,
        session_factory=None,
    )
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": [(b"content-length", content_length.encode())],
            },
            receive,
            send,
        )
    )

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 400


@pytest.mark.parametrize(
    ("setting_name", "message"),
    [
        ("jwt_secret", "JWT_SECRET"),
        ("totp_encryption_key", "TOTP_ENCRYPTION_KEY"),
        ("student_credential_encryption_key", "STUDENT_CREDENTIAL_ENCRYPTION_KEY"),
        ("admin_password", "ADMIN_PASSWORD"),
    ],
)
def test_startup_refuses_the_example_secrets(
    tmp_path: Path, setting_name: str, message: str
) -> None:
    """The shipped .env examples must never boot an instance as written.

    install.sh replaces them and the shell helper greps for the marker, but a
    hand-edited file that keeps one placeholder has to fail here rather than
    run a public instance on a published secret.
    """
    placeholder = "replace-with-a-value-that-is-long-enough-to-pass-length-checks"

    with pytest.raises(ValueError, match=f"{message} is still set to its example"):
        settings_for(tmp_path / "example-secret.db", **{setting_name: placeholder})


def test_student_tokens_default_to_two_hours_and_reject_shorter_lifetimes(
    tmp_path: Path,
) -> None:
    for hours in (1, 13):
        with pytest.raises(ValueError, match="STUDENT_ACCESS_TOKEN_HOURS"):
            settings_for(
                tmp_path / "student-token-bounds.db",
                student_access_token_hours=hours,
            )

    for overrides, expected_hours in (({}, 2), ({"student_access_token_hours": 5}, 5)):
        settings = settings_for(
            tmp_path / f"student-token-{expected_hours}h.db", **overrides
        )
        with make_client(settings) as client:
            environment = exam_environment(client)
            token = environment["student_headers"]["Authorization"].split()[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        assert payload["exp"] - payload["iat"] == expected_hours * 3600
