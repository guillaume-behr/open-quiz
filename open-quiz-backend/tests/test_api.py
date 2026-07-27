import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from time import sleep, time
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
FRONTEND_ORIGIN = "http://localhost:5173"


def settings_for(database: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{database.as_posix()}",
        "jwt_secret": JWT_SECRET,
        "totp_encryption_key": TOTP_ENCRYPTION_KEY,
        "admin_username": "root-admin",
        "admin_password": ADMIN_PASSWORD,
        "frontend_origin": FRONTEND_ORIGIN,
        "access_token_minutes": 5,
        "environment": "test",
    }
    values.update(overrides)
    return Settings(**values)


def make_client(settings: Settings) -> TestClient:
    return TestClient(
        create_app(settings),
        headers={"Origin": FRONTEND_ORIGIN},
    )


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
    with make_client(settings_for(tmp_path / "test.db")) as client:
        headers = login_admin(client)
        assert client.get("/api/quizzes", headers=headers).status_code == 403

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

        professor_login = client.post(
            "/api/auth/login",
            json={
                "username": "root-admin",
                "password": ADMIN_PASSWORD,
                "audience": "professor",
            },
        )
        assert professor_login.status_code == 403

        admin_login = client.post(
            "/api/auth/login",
            json={
                "username": "teacher.one",
                "password": "another-strong-password",
                "audience": "admin",
            },
        )
        assert admin_login.status_code == 403

        first_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": " 5e ", "chapter": " Les   fractions "},
        )
        assert first_bank.status_code == 201
        assert first_bank.json()["grade_level"] == "5e"
        assert first_bank.json()["chapter"] == "Les fractions"

        second_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Calcul littéral"},
        )
        assert second_bank.status_code == 201

        question_banks = client.get(
            "/api/question-banks",
            headers=teacher_headers,
        )
        assert question_banks.status_code == 200
        assert [
            (bank["grade_level"], bank["chapter"])
            for bank in question_banks.json()
        ] == [("4e", "Calcul littéral"), ("5e", "Les fractions")]

        duplicate = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "5e", "chapter": "Les fractions"},
        )
        assert duplicate.status_code == 409
        assert (
            client.get("/api/question-banks", headers=headers).status_code == 403
        )

        question_payload = {
            "prompt": "Quelle fraction est égale à un demi ?",
            "difficulty": "easy",
            "answer_mode": "single",
            "answer_mode_disclosed": False,
            "correction_mode": "automatic",
            "code_language": "python",
            "code_content": "def half(value):\n    return value / 2",
            "choices": [
                {
                    "label": "1/2",
                    "is_correct": True,
                    "points": 2.5,
                    "image": {
                        "content_type": "image/png",
                        "data_base64": "iVBORw0KGgoAY2hvaWNlLWltYWdl",
                    },
                    "code_language": "python",
                    "code_content": "print(1 / 2)",
                },
                {"label": "1/3", "is_correct": False, "points": -0.5},
            ],
        }
        created_question = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_payload)},
            files={
                "image": (
                    "fraction.png",
                    b"\x89PNG\r\n\x1a\nquestion-image",
                    "image/png",
                )
            },
        )
        assert created_question.status_code == 201
        question = created_question.json()
        assert question["has_image"] is True
        assert question["answer_mode_disclosed"] is False
        assert question["code_language"] == "python"
        assert "return value / 2" in question["code_content"]
        assert [choice["is_correct"] for choice in question["choices"]] == [
            True,
            False,
        ]
        assert [choice["points"] for choice in question["choices"]] == [2.5, -0.5]
        assert question["choices"][0]["has_image"] is True
        assert question["choices"][0]["code_language"] == "python"
        assert question["choices"][0]["code_content"] == "print(1 / 2)"
        bank_with_question = next(
            bank
            for bank in client.get(
                "/api/question-banks",
                headers=teacher_headers,
            ).json()
            if bank["id"] == first_bank.json()["id"]
        )
        assert bank_with_question["question_count"] == 1

        listed_questions = client.get(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
        )
        assert listed_questions.status_code == 200
        assert listed_questions.json()[0]["prompt"] == question_payload["prompt"]

        image = client.get(
            f"/api/question-banks/questions/{question['id']}/image",
            headers=teacher_headers,
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG")
        choice_image = client.get(
            f"/api/question-banks/choices/{question['choices'][0]['id']}/image",
            headers=teacher_headers,
        )
        assert choice_image.status_code == 200
        assert choice_image.headers["content-type"] == "image/png"
        assert choice_image.content.startswith(b"\x89PNG")

        invalid_automatic_question = {
            **question_payload,
            "choices": [
                {"label": "1/2", "is_correct": False},
                {"label": "1/3", "is_correct": False},
            ],
        }
        invalid_question = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(invalid_automatic_question)},
        )
        assert invalid_question.status_code == 422

        invalid_points_question = {
            **question_payload,
            "choices": [
                {"label": "1/2", "is_correct": True, "points": 1},
                {"label": "1/3", "is_correct": False, "points": 1},
            ],
        }
        invalid_points = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(invalid_points_question)},
        )
        assert invalid_points.status_code == 422

        invalid_manual_question = {
            **question_payload,
            "correction_mode": "manual",
        }
        invalid_manual = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(invalid_manual_question)},
        )
        assert invalid_manual.status_code == 422

        exported = client.get(
            f"/api/question-banks/{first_bank.json()['id']}/export",
            headers=teacher_headers,
        )
        assert exported.status_code == 200
        assert "attachment;" in exported.headers["content-disposition"]
        assert exported.text.startswith('{\n  "version": 1,')
        assert '"prompt": "Quelle fraction' in exported.text
        exported_batch = exported.json()
        assert exported_batch["version"] == 1
        assert exported_batch["question_bank"] == {
            "grade_level": "5e",
            "chapter": "Les fractions",
        }
        assert exported_batch["questions"][0]["image"]["content_type"] == "image/png"
        assert exported_batch["questions"][0]["code_language"] == "python"
        assert exported_batch["questions"][0]["choices"][0]["points"] == 2.5
        assert exported_batch["questions"][0]["choices"][0]["image"] is not None
        assert (
            exported_batch["questions"][0]["choices"][0]["code_content"]
            == "print(1 / 2)"
        )

        exported_batch["question_bank"] = {
            "grade_level": "3e",
            "chapter": "Fractions importées",
        }
        imported = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=exported_batch,
        )
        assert imported.status_code == 201
        imported_payload = imported.json()
        assert imported_payload["question_bank"]["grade_level"] == "3e"
        assert imported_payload["question_bank"]["chapter"] == "Fractions importées"
        assert imported_payload["question_bank"]["question_count"] == 1
        assert len(imported_payload["questions"]) == 1
        assert imported_payload["questions"][0]["prompt"] == question_payload["prompt"]
        assert imported_payload["questions"][0]["has_image"] is True
        assert imported_payload["questions"][0]["choices"][0]["has_image"] is True
        assert (
            imported_payload["questions"][0]["choices"][0]["code_language"]
            == "python"
        )

        duplicate_import = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=exported_batch,
        )
        assert duplicate_import.status_code == 409

        legacy_batch = json.loads(json.dumps(exported_batch))
        legacy_batch["question_bank"] = {
            "grade_level": "2de",
            "chapter": "Import sans points",
        }
        for imported_question in legacy_batch["questions"]:
            for choice in imported_question["choices"]:
                choice.pop("points")
        legacy_import = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=legacy_batch,
        )
        assert legacy_import.status_code == 201
        assert [
            choice["points"]
            for choice in legacy_import.json()["questions"][0]["choices"]
        ] == [1, 0]

        empty_import = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json={
                "version": 1,
                "question_bank": {
                    "grade_level": "6e",
                    "chapter": "Banque vide",
                },
                "questions": [],
            },
        )
        assert empty_import.status_code == 201
        assert empty_import.json()["question_bank"]["question_count"] == 0
        assert empty_import.json()["questions"] == []

        example = client.get(
            "/api/question-banks/example",
            headers=teacher_headers,
        )
        assert example.status_code == 200
        assert example.text.startswith('{\n  "version": 1,')
        assert '"prompt": "Quelle est la capitale' in example.text
        example_batch = example.json()
        assert example_batch["version"] == 1
        assert {
            (item["answer_mode"], item["correction_mode"])
            for item in example_batch["questions"]
        } == {
            ("single", "automatic"),
            ("multiple", "automatic"),
            ("single", "manual"),
            ("multiple", "manual"),
        }
        assert any(item["image"] for item in example_batch["questions"])
        assert any(item["code_content"] for item in example_batch["questions"])
        assert any(
            choice["image"]
            for item in example_batch["questions"]
            for choice in item["choices"]
        )
        assert any(
            choice["code_content"]
            for item in example_batch["questions"]
            for choice in item["choices"]
        )

        updated_payload = {
            **question_payload,
            "prompt": "Quelle fraction représente exactement la moitié ?",
            "difficulty": "medium",
            "code_language": "javascript",
            "code_content": "const half = (value) => value / 2;",
            "remove_image": True,
            "choices": [
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][0]["id"],
                    "image": None,
                },
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][1]["id"],
                },
            ],
        }
        updated = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(updated_payload)},
        )
        assert updated.status_code == 200
        assert updated.json()["prompt"] == updated_payload["prompt"]
        assert updated.json()["difficulty"] == "medium"
        assert updated.json()["code_language"] == "javascript"
        assert updated.json()["has_image"] is False
        updated_choice = updated.json()["choices"][0]
        assert updated_choice["has_image"] is True
        assert updated_choice["code_content"] == "print(1 / 2)"
        assert (
            client.get(
                f"/api/question-banks/choices/{updated_choice['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/question-banks/questions/{question['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 404
        )


def test_existing_question_choices_gain_points_column(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-question-choices.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            """
            CREATE TABLE question_choices (
                id INTEGER PRIMARY KEY,
                question_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL DEFAULT 0,
                position INTEGER NOT NULL
            )
            """
        )

    create_app(settings_for(database_path))

    with sqlite3.connect(database_path) as database:
        columns = {
            row[1]
            for row in database.execute("PRAGMA table_info(question_choices)")
        }
    assert {
        "points",
        "image_data",
        "image_content_type",
        "code_language",
        "code_content",
    }.issubset(columns)


def test_refresh_rotates_cookie_and_logout_revokes_it(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    with make_client(settings_for(database_path)) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        first_refresh = client.cookies.get(REFRESH_COOKIE)
        assert first_refresh

        with sqlite3.connect(database_path) as database:
            created_at, first_expires_at = database.execute(
                "SELECT created_at, expires_at FROM refresh_sessions"
            ).fetchone()
        assert created_at is not None
        assert first_expires_at is not None

        refreshed = client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        second_refresh = client.cookies.get(REFRESH_COOKIE)
        assert second_refresh and second_refresh != first_refresh
        with sqlite3.connect(database_path) as database:
            second_expires_at = database.execute(
                "SELECT expires_at FROM refresh_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        assert second_expires_at == first_expires_at

        client.cookies.set(REFRESH_COOKIE, first_refresh, path="/api/auth")
        assert client.post("/api/auth/refresh").status_code == 401

        client.cookies.set(REFRESH_COOKIE, second_refresh, path="/api/auth")
        assert client.post("/api/auth/refresh").status_code == 401

        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        next_code = pyotp.TOTP(secret).at(time() + 30)
        assert (
            client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": challenge["challenge_token"],
                    "code": next_code,
                },
            ).status_code
            == 200
        )
        assert client.post("/api/auth/logout").status_code == 204
        assert client.post("/api/auth/refresh").status_code == 401


def test_later_login_requires_two_factor_code(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
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


def test_new_device_requires_two_factor_while_known_device_is_restored(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "test.db")
    with make_client(app_settings) as known_device:
        complete_first_login(known_device, "root-admin", ADMIN_PASSWORD)
        assert known_device.post("/api/auth/refresh").status_code == 200

    with make_client(app_settings) as new_device:
        login_response = new_device.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert login_response.status_code == 200
        assert login_response.json()["status"] == "verification_required"


def test_two_factor_recovery_requires_new_setup(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    app_settings = settings_for(database)
    with make_client(app_settings) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)

    assert reset("root-admin", app_settings)

    with make_client(app_settings) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert login_response.json()["status"] == "setup_required"


def test_login_rate_limit_and_origin_check(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    with make_client(app_settings) as client:
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

    with make_client(app_settings) as client:
        still_limited = client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "incorrect-password"},
        )
        assert still_limited.status_code == 429

    with TestClient(create_app(settings_for(tmp_path / "origin.db"))) as client:
        missing = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert missing.status_code == 403
        rejected = client.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert rejected.status_code == 403


def test_development_accepts_local_vite_origin_on_another_port(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(
        tmp_path / "development.db",
        environment="development",
    )
    with TestClient(
        create_app(app_settings),
        headers={"Origin": "http://localhost:5174"},
    ) as client:
        accepted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert accepted.status_code == 200

    with TestClient(
        create_app(app_settings),
        headers={"Origin": "http://attacker.example"},
    ) as client:
        rejected = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert rejected.status_code == 403


def test_login_rate_limit_reserves_concurrent_attempts_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(tmp_path / "test.db", login_attempts=3)
    barrier = Barrier(8)

    def slow_invalid_password(_: str, __: str) -> bool:
        sleep(0.1)
        return False

    monkeypatch.setattr(
        "app.routers.auth.verify_password",
        slow_invalid_password,
    )

    with make_client(app_settings) as client:
        def attempt_login() -> int:
            barrier.wait()
            return client.post(
                "/api/auth/login",
                json={"username": "unknown", "password": "incorrect-password"},
            ).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(attempt_login) for _ in range(8)]
            statuses = [future.result() for future in futures]

    assert statuses.count(401) <= 3
    assert statuses.count(429) >= 5


def test_admin_routes_require_authentication(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        assert client.get("/api/admin/users").status_code == 401


def test_environment_password_rotation_updates_existing_admin(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with make_client(settings_for(database)) as client:
        access_headers, _ = complete_first_login(
            client,
            "root-admin",
            ADMIN_PASSWORD,
        )
        previous_refresh = client.cookies.get(REFRESH_COOKIE)

    rotated = settings_for(
        database,
        admin_password="a-different-strong-password",
    )
    with make_client(rotated) as client:
        assert client.get("/api/users/me", headers=access_headers).status_code == 401
        client.cookies.set(REFRESH_COOKIE, previous_refresh, path="/api/auth")
        assert client.post("/api/auth/refresh").status_code == 401
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


def test_environment_admin_rename_moves_managed_account(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with make_client(settings_for(database)) as client:
        headers, secret = complete_first_login(
            client,
            "root-admin",
            ADMIN_PASSWORD,
        )
        original = client.get("/api/users/me", headers=headers).json()

    renamed = settings_for(database, admin_username="renamed-admin")
    with make_client(renamed) as client:
        old_login = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        new_login = client.post(
            "/api/auth/login",
            json={"username": "renamed-admin", "password": ADMIN_PASSWORD},
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": new_login.json()["challenge_token"],
                "code": pyotp.TOTP(secret).at(time() + 30),
            },
        )
        renamed_user = client.get(
            "/api/users/me",
            headers={
                "Authorization": f"Bearer {verified.json()['access_token']}"
            },
        ).json()
        assert renamed_user["id"] == original["id"]
        assert renamed_user["username"] == "renamed-admin"


def test_two_factor_code_and_challenge_are_consumed_atomically(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert client.post("/api/auth/logout").status_code == 204
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()["challenge_token"]
        code = pyotp.TOTP(secret).at(time() + 30)
        barrier = Barrier(2)

        def verify() -> int:
            barrier.wait()
            return client.post(
                "/api/auth/2fa/verify",
                json={"challenge_token": challenge, "code": code},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(
                future.result()
                for future in (pool.submit(verify), pool.submit(verify))
            )
        assert statuses == [200, 401]


def test_request_size_and_authenticated_cache_controls(tmp_path: Path) -> None:
    app_settings = settings_for(tmp_path / "test.db", max_request_body_bytes=1024)
    with make_client(app_settings) as client:
        oversized = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": "x" * 2048},
        )
        assert oversized.status_code == 413
        assert oversized.headers["cache-control"] == "no-store"

        chunked = client.post(
            "/api/auth/login",
            content=(b"x" * 600 for _ in range(2)),
            headers={"Content-Type": "application/json"},
        )
        assert chunked.status_code == 413
        assert chunked.headers["cache-control"] == "no-store"

        headers = login_admin(client)
        users = client.get("/api/admin/users", headers=headers)
        assert users.status_code == 200
        assert users.headers["cache-control"] == "no-store"


def test_rejects_weak_or_insecure_production_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings_for(tmp_path / "weak.db", jwt_secret="short")

    with pytest.raises(ValueError, match="HTTPS"):
        settings_for(
            tmp_path / "production.db",
            environment="production",
        )
