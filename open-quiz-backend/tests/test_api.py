from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.routers.auth import REFRESH_COOKIE
from main import create_app

JWT_SECRET = "test-secret-that-is-at-least-32-bytes-long"
ADMIN_PASSWORD = "a-strong-test-password"


def settings_for(database: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{database.as_posix()}",
        "jwt_secret": JWT_SECRET,
        "admin_username": "root-admin",
        "admin_password": ADMIN_PASSWORD,
        "frontend_origin": "http://localhost:5173",
        "access_token_minutes": 5,
        "environment": "test",
    }
    values.update(overrides)
    return Settings(**values)


def login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "root-admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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

        teacher_login = client.post(
            "/api/auth/login",
            json={"username": "teacher.one", "password": "another-strong-password"},
        )
        teacher_headers = {
            "Authorization": f"Bearer {teacher_login.json()['access_token']}"
        }
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
