import json
import sqlite3
from base64 import b64decode, b64encode
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
VALID_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


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


def test_health_checks_database_readiness(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "health.db")) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_public_quiz_join_is_rate_limited(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "quiz-rate-limit.db",
        quiz_join_attempts=5,
        quiz_rate_window_seconds=60,
    )
    with make_client(settings) as client:
        payload = {
            "join_code": "ABC123",
            "student_identifier": "student",
        }
        for _ in range(5):
            response = client.post("/api/quizzes/join", json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "Impossible de rejoindre ce quiz"

        limited = client.post("/api/quizzes/join", json=payload)
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0
        different_student = client.post(
            "/api/quizzes/join",
            json={
                "join_code": "ABC123",
                "student_identifier": "another-student",
            },
        )
        assert different_student.status_code == 403


def test_invalid_participant_tokens_are_rate_limited_independently(
    tmp_path: Path,
) -> None:
    settings = settings_for(
        tmp_path / "participant-auth-rate-limit.db",
        quiz_join_attempts=5,
        quiz_rate_window_seconds=60,
    )
    endpoint = "/api/quizzes/student/sessions/ABC123"
    with make_client(settings) as client:
        for _ in range(5):
            response = client.get(
                endpoint,
                headers={"X-Quiz-Token": "invalid-token"},
            )
            assert response.status_code == 401

        limited = client.get(
            endpoint,
            headers={"X-Quiz-Token": "invalid-token"},
        )
        assert limited.status_code == 429

        different_token = client.get(
            endpoint,
            headers={"X-Quiz-Token": "another-invalid-token"},
        )
        assert different_token.status_code == 401


def test_expired_public_quiz_rate_limits_are_removed(tmp_path: Path) -> None:
    database = tmp_path / "quiz-rate-limit-cleanup.db"
    with make_client(settings_for(database)) as client:
        first = client.post(
            "/api/quizzes/join",
            json={"join_code": "ABC123", "student_identifier": "student"},
        )
        assert first.status_code == 403

        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE login_rate_limits SET window_started_at = 0 "
                "WHERE limiter_key LIKE 'quiz-join:%'"
            )
            connection.commit()

        second = client.post(
            "/api/quizzes/join",
            json={"join_code": "XYZ789", "student_identifier": "student"},
        )
        assert second.status_code == 403

        with sqlite3.connect(database) as connection:
            public_limit_count = connection.execute(
                "SELECT COUNT(*) FROM login_rate_limits "
                "WHERE limiter_key LIKE 'quiz-join:%'"
            ).fetchone()[0]
        assert public_limit_count == 1


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

        created_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": " 5e   B ", "grade_level": " 5e "},
        )
        assert created_class.status_code == 201
        student_class = created_class.json()
        assert student_class["name"] == "5e B"
        assert student_class["grade_level"] == "5e"
        assert student_class["students"] == []
        assert student_class["completed_quiz_count"] == 0
        assert (
            client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": "5e B", "grade_level": "5e"},
            ).status_code
            == 409
        )

        created_student = client.post(
            f"/api/classes/{student_class['id']}/students",
            headers=teacher_headers,
            json={
                "display_name": " Martin   G. ",
            },
        )
        assert created_student.status_code == 201
        student = created_student.json()
        assert student["identifier"] == "martin.g"
        assert student["display_name"] == "Martin G."
        generated_duplicate = client.post(
            f"/api/classes/{student_class['id']}/students",
            headers=teacher_headers,
            json={"display_name": "Martin G."},
        )
        assert generated_duplicate.status_code == 201
        assert generated_duplicate.json()["identifier"] == "martin.g2"
        assert (
            client.delete(
                f"/api/classes/students/{generated_duplicate.json()['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        updated_class = client.post(
            f"/api/classes/{student_class['id']}/update",
            headers=teacher_headers,
            json={"name": "5e B", "grade_level": "Cinquième"},
        )
        assert updated_class.status_code == 200
        assert updated_class.json()["grade_level"] == "Cinquième"
        updated_student_record = client.post(
            f"/api/classes/students/{student['id']}/update",
            headers=teacher_headers,
            json={
                "identifier": "martin.g",
                "display_name": "Martin Giraud",
            },
        )
        assert updated_student_record.status_code == 200
        student = updated_student_record.json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/students",
                headers=teacher_headers,
                json={
                    "identifier": "martin.g",
                    "display_name": "Autre élève",
                },
            ).status_code
            == 409
        )
        listed_classes = client.get(
            "/api/classes",
            headers=teacher_headers,
        )
        assert listed_classes.status_code == 200
        assert listed_classes.json()[0]["student_count"] == 1

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
            (bank["grade_level"], bank["chapter"]) for bank in question_banks.json()
        ] == [("4e", "Calcul littéral"), ("5e", "Les fractions")]

        duplicate = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "5e", "chapter": "Les fractions"},
        )
        assert duplicate.status_code == 409
        assert client.get("/api/question-banks", headers=headers).status_code == 403

        question_payload = {
            "prompt": "Quelle fraction est égale à un demi ?",
            "difficulty": "easy",
            "answer_mode": "single",
            "answer_mode_disclosed": False,
            "code_language": "python",
            "code_content": "def half(value):\n    return value / 2",
            "choices": [
                {
                    "label": "1/2",
                    "is_correct": True,
                    "points": 2.5,
                    "image": {
                        "content_type": "image/png",
                        "data_base64": b64encode(VALID_PNG).decode(),
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
                    VALID_PNG,
                    "image/png",
                )
            },
        )
        assert created_question.status_code == 201
        question = created_question.json()
        assert question["has_image"] is True
        assert "correction_mode" not in question
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
        invalid_image = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_payload)},
            files={
                "image": (
                    "not-an-image.png",
                    b"\x89PNG\r\n\x1a\nnot-a-real-image",
                    "image/png",
                )
            },
        )
        assert invalid_image.status_code == 422
        reordered_payload = {
            **question_payload,
            "choices": [
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][1]["id"],
                },
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][0]["id"],
                },
            ],
        }
        reordered_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(reordered_payload)},
        )
        assert reordered_question.status_code == 200
        question = reordered_question.json()
        assert [choice["label"] for choice in question["choices"]] == [
            "1/3",
            "1/2",
        ]
        restored_payload = {
            **question_payload,
            "choices": [
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][1]["id"],
                },
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][0]["id"],
                },
            ],
        }
        restored_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(restored_payload)},
        )
        assert restored_question.status_code == 200
        question = restored_question.json()
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

        question_without_correct_answer = {
            **question_payload,
            "choices": [
                {"label": "1/2", "is_correct": False},
                {"label": "1/3", "is_correct": False},
            ],
        }
        invalid_question = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_without_correct_answer)},
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
        assert "correction_mode" not in exported_batch["questions"][0]
        assert exported_batch["questions"][0]["code_language"] == "python"
        assert exported_batch["questions"][0]["choices"][0]["points"] == 2.5
        assert exported_batch["questions"][0]["choices"][1]["points"] == -0.5
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
            imported_payload["questions"][0]["choices"][0]["code_language"] == "python"
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
            imported_question["correction_mode"] = "automatic"
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
        assert {item["answer_mode"] for item in example_batch["questions"]} == {
            "single",
            "multiple",
            "written",
        }
        assert all("correction_mode" not in item for item in example_batch["questions"])
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
        assert any(
            choice["points"] < 0
            for item in example_batch["questions"]
            for choice in item["choices"]
            if not choice["is_correct"]
        )

        example_batch["question_bank"] = {
            "grade_level": "Terminale",
            "chapter": "Import de l’exemple",
        }
        imported_example = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=example_batch,
        )
        assert imported_example.status_code == 201
        assert imported_example.json()["question_bank"]["question_count"] == 3
        assert {
            question["answer_mode"] for question in imported_example.json()["questions"]
        } == {"single", "multiple", "written"}

        invalid_quiz_distribution = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Révisions invalides",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "question_count": 3,
                "easy_percentage": 30,
                "medium_percentage": 30,
                "hard_percentage": 30,
            },
        )
        assert invalid_quiz_distribution.status_code == 422

        created_quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": " Révisions   générales ",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "question_count": 3,
                "allow_previous_questions": True,
                "easy_percentage": 34,
                "medium_percentage": 33,
                "hard_percentage": 33,
            },
        )
        assert created_quiz.status_code == 201
        quiz = created_quiz.json()
        assert quiz["title"] == "Révisions générales"
        assert quiz["question_count"] == 3
        assert quiz["duration_seconds"] == 1800
        assert quiz["allow_previous_questions"] is True
        assert len(quiz["question_banks"]) == 1
        assert (
            client.get("/api/quizzes", headers=teacher_headers).json()[0]["id"]
            == quiz["id"]
        )

        preview = client.get(
            f"/api/quizzes/{quiz['id']}/preview",
            headers=teacher_headers,
        )
        assert preview.status_code == 200
        assert len(preview.json()) == 3
        assert {question["difficulty"] for question in preview.json()} == {
            "easy",
            "medium",
            "hard",
        }

        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201
        quiz_session = launched.json()
        assert quiz_session["class_name"] == "5e B"
        assert quiz_session["status"] == "waiting"
        assert len(quiz_session["join_code"]) == 6
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()[0]["id"]
            == quiz_session["id"]
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )

        joined = client.post(
            "/api/quizzes/join",
            json={
                "join_code": quiz_session["join_code"].lower(),
                "student_identifier": " martin.g ",
            },
        )
        assert joined.status_code == 201
        assert joined.json()["quiz_title"] == quiz["title"]
        assert "participants" not in joined.json()
        with sqlite3.connect(tmp_path / "test.db") as connection:
            successful_join_limits = connection.execute(
                "SELECT COUNT(*) FROM login_rate_limits "
                "WHERE limiter_key LIKE 'quiz-join:%'"
            ).fetchone()[0]
        assert successful_join_limits == 0
        assert (
            client.post(
                "/api/quizzes/join",
                json={
                    "join_code": quiz_session["join_code"],
                    "student_identifier": "inconnu",
                },
            ).status_code
            == 403
        )
        joined_again = client.post(
            "/api/quizzes/join",
            json={
                "join_code": quiz_session["join_code"],
                "student_identifier": "martin.g",
            },
        )
        assert joined_again.status_code == 403
        assert joined_again.json()["detail"] == "Impossible de rejoindre ce quiz"
        participant_token = joined.json()["participant_token"]
        student_headers = {"X-Quiz-Token": participant_token}
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
            ).status_code
            == 401
        )

        waiting_room = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        )
        assert waiting_room.status_code == 200
        assert waiting_room.json()["participant_count"] == 1
        assert (
            waiting_room.json()["participants"][0]["student_display_name"]
            == "Martin Giraud"
        )
        student_state_url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "waiting"
        )

        started = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start",
            headers=teacher_headers,
        )
        assert started.status_code == 200
        assert started.json()["status"] == "in_progress"
        assert started.json()["started_at"] is not None
        assert started.json()["ends_at"] is not None
        violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert violation.status_code == 204
        monitored = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert monitored["violation_count"] == 1
        assert monitored["last_violation_type"] == "fullscreen_exit"
        assert monitored["last_violation_at"] is not None
        duplicate_violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert duplicate_violation.status_code == 204
        monitored = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert monitored["violation_count"] == 1
        assert (
            client.post(
                "/api/quizzes/join",
                json={
                    "join_code": quiz_session["join_code"],
                    "student_identifier": "nouvel.eleve",
                },
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/question-banks/{imported_example.json()['question_bank']['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/question-banks/questions/{preview.json()[0]['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )

        expected_by_prompt = {
            item["prompt"]: item for item in example_batch["questions"]
        }
        for question_number in range(1, 4):
            student_state = client.get(student_state_url, headers=student_headers)
            assert student_state.status_code == 200
            state_payload = student_state.json()
            assert state_payload["question_number"] == question_number
            assert state_payload["question"] is not None

            def collect_keys(value):
                if isinstance(value, dict):
                    return set(value) | {
                        key for child in value.values() for key in collect_keys(child)
                    }
                if isinstance(value, list):
                    return {key for child in value for key in collect_keys(child)}
                return set()

            assert collect_keys(state_payload).isdisjoint(
                {"is_correct", "points", "correction_mode"}
            )
            safe_question = state_payload["question"]
            expected = expected_by_prompt[safe_question["prompt"]]
            if safe_question["answer_mode"] == "written":
                answer_payload = {
                    "written_answer": next(
                        choice["label"]
                        for choice in expected["choices"]
                        if choice["is_correct"]
                    )
                }
            else:
                missing_answer = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json={},
                )
                assert missing_answer.status_code == 422
                empty_answer = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json={"selected_choice_ids": []},
                )
                assert empty_answer.status_code == 422
                correct_labels = {
                    choice["label"]
                    for choice in expected["choices"]
                    if choice["is_correct"]
                }
                answer_payload = {
                    "selected_choice_ids": [
                        choice["id"]
                        for choice in safe_question["choices"]
                        if choice["label"] in correct_labels
                    ]
                }
            submitted = client.post(
                f"{student_state_url}/answer",
                headers=student_headers,
                json=answer_payload,
            )
            assert submitted.status_code == 200
            if question_number < 3:
                assert submitted.json()["question_number"] == question_number + 1
                assert submitted.json()["question"] is not None
            else:
                assert submitted.json()["status"] == "finished"
                assert submitted.json()["question"] is None
            teacher_state = client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()
            assert teacher_state["participants"][0]["answered_count"] == question_number
            if question_number < 3:
                assert teacher_state["participants"][0]["score"] == 0
            if question_number == 2:
                previous = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 2},
                )
                assert previous.status_code == 200
                assert previous.json()["question_number"] == 2
                assert previous.json()["has_answered"] is True
                assert (
                    previous.json()["selected_choice_ids"] is not None
                    or previous.json()["written_answer"] is not None
                )
                assert collect_keys(previous.json()).isdisjoint(
                    {"is_correct", "points", "correction_mode", "score"}
                )
                resubmitted = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json=answer_payload,
                )
                assert resubmitted.status_code == 200
                assert resubmitted.json()["question_number"] == 3

        assert teacher_state["status"] == "finished"
        assert teacher_state["participants"][0]["score"] > 0
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
            == []
        )
        results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        )
        assert results.status_code == 200
        assert [result["id"] for result in results.json()] == [quiz_session["id"]]
        assert results.json()[0]["quiz_title"] == quiz["title"]
        assert results.json()[0]["class_name"] == "5e B"
        assert results.json()[0]["participants"][0]["score"] > 0
        assert (
            client.get("/api/quizzes/sessions/results", headers=headers).status_code
            == 403
        )
        previous_score = results.json()[0]["participants"][0]["score"]
        regraded_question = preview.json()[0]
        original_choice_ids = [choice["id"] for choice in regraded_question["choices"]]
        regraded_payload = {
            "prompt": regraded_question["prompt"],
            "difficulty": regraded_question["difficulty"],
            "answer_mode": regraded_question["answer_mode"],
            "answer_mode_disclosed": regraded_question["answer_mode_disclosed"],
            "code_language": regraded_question["code_language"],
            "code_content": regraded_question["code_content"],
            "choices": [
                {
                    "id": choice["id"],
                    "label": choice["label"],
                    "is_correct": choice["is_correct"],
                    "points": 9 if choice["is_correct"] else choice["points"],
                    "code_language": choice["code_language"],
                    "code_content": choice["code_content"],
                }
                for choice in regraded_question["choices"]
            ],
        }
        regraded = client.post(
            f"/api/question-banks/questions/{regraded_question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(regraded_payload)},
        )
        assert regraded.status_code == 200
        assert [choice["id"] for choice in regraded.json()["choices"]] == (
            original_choice_ids
        )
        refreshed_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        assert refreshed_results[0]["participants"][0]["score"] > previous_score

        expiring_launch = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert expiring_launch.status_code == 201
        expiring_session = expiring_launch.json()
        expiring_join = client.post(
            "/api/quizzes/join",
            json={
                "join_code": expiring_session["join_code"],
                "student_identifier": student["identifier"],
            },
        )
        assert expiring_join.status_code == 201
        assert (
            client.post(
                f"/api/quizzes/sessions/{expiring_session['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        with sqlite3.connect(tmp_path / "test.db") as connection:
            connection.execute(
                "UPDATE quiz_sessions SET started_at = ? WHERE id = ?",
                ("2000-01-01 00:00:00", expiring_session["id"]),
            )
            connection.commit()

        expired_session_details = client.get(
            f"/api/quizzes/sessions/{expiring_session['id']}",
            headers=teacher_headers,
        )
        assert expired_session_details.status_code == 200
        assert expired_session_details.json()["status"] == "finished"

        results_after_expiry = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        )
        assert results_after_expiry.status_code == 200
        assert expiring_session["id"] not in {
            result["id"] for result in results_after_expiry.json()
        }
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
            == []
        )
        completed_class = client.get("/api/classes", headers=teacher_headers).json()[0]
        assert completed_class["completed_quiz_count"] == 1
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "finished"
        )
        assert (
            client.delete(
                f"/api/classes/students/{student['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        session_after_student_delete = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()
        assert (
            session_after_student_delete["participants"][0]["student_display_name"]
            == "Martin Giraud"
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()["class_id"]
            is None
        )
        assert (
            client.delete(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
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

        deleted_question = client.delete(
            f"/api/question-banks/questions/{question['id']}",
            headers=teacher_headers,
        )
        assert deleted_question.status_code == 204
        assert (
            client.get(
                f"/api/question-banks/{first_bank.json()['id']}/questions",
                headers=teacher_headers,
            ).json()
            == []
        )
        assert (
            client.get(
                f"/api/question-banks/choices/{updated_choice['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 404
        )
        bank_after_question_delete = next(
            bank
            for bank in client.get(
                "/api/question-banks",
                headers=teacher_headers,
            ).json()
            if bank["id"] == first_bank.json()["id"]
        )
        assert bank_after_question_delete["question_count"] == 0
        assert (
            client.delete(
                f"/api/question-banks/questions/{question['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        disabled = client.post(
            f"/api/admin/users/{created.json()['id']}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False
        assert client.get("/api/users/me", headers=teacher_headers).status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "teacher.one",
                    "password": "another-strong-password",
                    "audience": "professor",
                },
            ).status_code
            == 401
        )
        enabled = client.post(
            f"/api/admin/users/{created.json()['id']}/status",
            headers=headers,
            json={"is_active": True},
        )
        assert enabled.status_code == 200
        for _ in range(4):
            failed_login = client.post(
                "/api/auth/login",
                json={
                    "username": "teacher.one",
                    "password": "incorrect-password",
                    "audience": "professor",
                },
            )
            assert failed_login.status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "teacher.one",
                    "password": "incorrect-password",
                    "audience": "professor",
                },
            ).status_code
            == 429
        )
        reset_access = client.post(
            f"/api/admin/users/{created.json()['id']}/credentials",
            headers=headers,
            json={
                "password": "replacement-strong-password",
                "reset_two_factor": True,
            },
        )
        assert reset_access.status_code == 200
        recovery_login = client.post(
            "/api/auth/login",
            json={
                "username": "teacher.one",
                "password": "replacement-strong-password",
                "audience": "professor",
            },
        )
        assert recovery_login.status_code == 200
        assert recovery_login.json()["status"] == "setup_required"


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
            row[1] for row in database.execute("PRAGMA table_info(question_choices)")
        }
    assert {
        "points",
        "image_data",
        "image_content_type",
        "code_language",
        "code_content",
    }.issubset(columns)


def test_existing_quiz_sessions_gain_class_and_student_links(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-quiz-sessions.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            """
            CREATE TABLE quiz_sessions (
                id INTEGER PRIMARY KEY,
                quiz_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                join_code TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                started_at DATETIME
            )
            """
        )
        database.execute(
            """
            CREATE TABLE quiz_participants (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL,
                student_identifier TEXT NOT NULL,
                joined_at DATETIME NOT NULL
            )
            """
        )

    create_app(settings_for(database_path))

    with sqlite3.connect(database_path) as database:
        session_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quiz_sessions)")
        }
        participant_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quiz_participants)")
        }
    assert "class_id" in session_columns
    assert {"student_id", "student_display_name"}.issubset(participant_columns)


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
        other_account = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert other_account.status_code == 200

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
            headers={"Authorization": f"Bearer {verified.json()['access_token']}"},
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
                future.result() for future in (pool.submit(verify), pool.submit(verify))
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


@pytest.mark.parametrize(
    ("setting_name", "value", "expected_message"),
    [
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
