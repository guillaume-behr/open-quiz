from pathlib import Path
from time import time
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.routers.auth import REFRESH_COOKIE
from main import create_app
from scripts.reset_two_factor import reset

JWT_SECRET = "test-secret-that-is-at-least-32-bytes-long"
TOTP_ENCRYPTION_KEY = "test-totp-key-that-is-at-least-32-bytes"
ADMIN_PASSWORD = "a-strong-test-password"


def settings_for(database: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{database.as_posix()}",
        "jwt_secret": JWT_SECRET,
        "totp_encryption_key": TOTP_ENCRYPTION_KEY,
        "admin_username": "root-admin",
        "admin_password": ADMIN_PASSWORD,
        "frontend_origin": "http://localhost:5173",
        "access_token_minutes": 5,
        "environment": "test",
    }
    values.update(overrides)
    return Settings(**values)


def complete_first_login(
    client: TestClient,
    username: str,
    password: str,
) -> tuple[dict[str, str], str]:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    challenge = response.json()
    assert challenge["status"] == "setup_required"
    assert "access_token" not in challenge
    assert challenge["provisioning_uri"].startswith("otpauth://totp/")
    secret = challenge["secret"]
    valid_code = pyotp.TOTP(secret).now()
    invalid_code = "000000" if valid_code != "000000" else "111111"

    invalid = client.post(
        "/api/auth/2fa/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": invalid_code,
        },
    )
    assert invalid.status_code == 401

    verified = client.post(
        "/api/auth/2fa/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": valid_code,
        },
    )
    assert verified.status_code == 200
    cookie = verified.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    return (
        {"Authorization": f"Bearer {verified.json()['access_token']}"},
        secret,
    )


def login_admin(client: TestClient) -> dict[str, str]:
    headers, _ = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
    return headers


def test_admin_can_login_and_create_professor(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path / "test.db"))) as client:
        headers = login_admin(client)
        created = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.one",
                "display_name": "Teacher One",
                "password": "another-strong-password",
            },
        )
        assert created.status_code == 201
        assert created.json()["username"] == "teacher.one"
        assert created.json()["is_admin"] is False
        assert "password" not in created.json()

        duplicate = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.one",
                "display_name": "Another",
                "password": "another-strong-password",
            },
        )
        assert duplicate.status_code == 409

        teacher_headers, _ = complete_first_login(
            client,
            "teacher.one",
            "another-strong-password",
        )
        assert client.get("/api/users/me", headers=teacher_headers).status_code == 200
        assert client.get("/api/quizzes", headers=teacher_headers).json() == []
        assert (
            client.get("/api/admin/users", headers=teacher_headers).status_code == 403
        )


def test_refresh_rotates_cookie_and_logout_revokes_it(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path / "test.db"))) as client:
        login_admin(client)
        first_refresh = client.cookies.get(REFRESH_COOKIE)
        assert first_refresh

        refreshed = client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        second_refresh = client.cookies.get(REFRESH_COOKIE)
        assert second_refresh and second_refresh != first_refresh

        client.cookies.set(REFRESH_COOKIE, first_refresh, path="/api/auth")
        assert client.post("/api/auth/refresh").status_code == 401

        client.cookies.set(REFRESH_COOKIE, second_refresh, path="/api/auth")
        assert client.post("/api/auth/logout").status_code == 204
        assert client.post("/api/auth/refresh").status_code == 401


def test_later_login_requires_two_factor_code(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path / "test.db"))) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert client.post("/api/auth/logout").status_code == 204

        login_response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        challenge = login_response.json()
        assert challenge["status"] == "verification_required"
        assert challenge["secret"] is None
        assert challenge["provisioning_uri"] is None

        next_code = pyotp.TOTP(secret).at(time() + 30)
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": next_code,
            },
        )
        assert verified.status_code == 200

        replayed = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": next_code,
            },
        )
        assert replayed.status_code == 401


def test_two_factor_recovery_requires_new_setup(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    app_settings = settings_for(database)
    with TestClient(create_app(app_settings)) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)

    assert reset("root-admin", app_settings)

    with TestClient(create_app(app_settings)) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert login_response.json()["status"] == "setup_required"


def test_login_rate_limit_and_origin_check(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    with TestClient(create_app(app_settings)) as client:
        for _ in range(3):
            response = client.post(
                "/api/auth/login",
                json={"username": "unknown", "password": "incorrect-password"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "incorrect-password"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0

    with TestClient(create_app(settings_for(tmp_path / "origin.db"))) as client:
        rejected = client.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert rejected.status_code == 403


def test_admin_routes_require_authentication(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path / "test.db"))) as client:
        assert client.get("/api/admin/users").status_code == 401


def test_environment_password_rotation_updates_existing_admin(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with TestClient(create_app(settings_for(database))):
        pass

    rotated = settings_for(
        database,
        admin_password="a-different-strong-password",
    )
    with TestClient(create_app(rotated)) as client:
        old_login = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        new_login = client.post(
            "/api/auth/login",
            json={
                "username": "root-admin",
                "password": "a-different-strong-password",
            },
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200


def test_rejects_weak_or_insecure_production_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings_for(tmp_path / "weak.db", jwt_secret="short")

    with pytest.raises(ValueError, match="HTTPS"):
        settings_for(
            tmp_path / "production.db",
            environment="production",
        )
