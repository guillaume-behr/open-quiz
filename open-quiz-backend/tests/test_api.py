import asyncio
import json
import os
import sqlite3
from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from importlib.util import find_spec
from pathlib import Path
from threading import Barrier
from time import sleep, time
from typing import Any

import pyotp
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select

from app.config import Settings, secure_private_file
from app.database import legacy_difficulty_counts
from app.middleware import RequestBodyLimitMiddleware
from app.models import (
    AuthenticationChallenge,
    ProblemReport,
    Question,
    QuestionBank,
    QuestionChoice,
    Quiz,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    QuizSessionStudentQuestion,
    RefreshSession,
    RefreshSessionFamily,
    Student,
    StudentAccount,
    StudentClass,
    User,
)
from app.rate_limit import LoginRateLimiter
from app.routers.auth import REFRESH_COOKIE, REFRESH_PROOF_HEADER
from app.routers.quizzes import (
    generate_join_code,
    participant_maximum_scores,
    safe_spreadsheet_cell,
)
from app.schemas import (
    LoginRequest,
    QuestionBatchImport,
    StudentLoginRequest,
    StudentQuizAnswer,
)
from app.security import DUMMY_PASSWORD_HASH, refresh_request_proof
from main import create_app
from scripts.reset_two_factor import reset

JWT_SECRET = "test-secret-that-is-at-least-32-bytes-long"
TOTP_ENCRYPTION_KEY = "test-totp-key-that-is-at-least-32-bytes"
STUDENT_CREDENTIAL_ENCRYPTION_KEY = (
    "test-student-credential-key-with-enough-variety-4567"
)
ADMIN_PASSWORD = "a-strong-test-password"
FRONTEND_ORIGIN = "http://localhost:5173"
VALID_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)
TEST_CLIENT_BACKEND_OPTIONS = {"use_uvloop": True} if find_spec("uvloop") else {}


def settings_for(database: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{database.as_posix()}",
        "jwt_secret": JWT_SECRET,
        "totp_encryption_key": TOTP_ENCRYPTION_KEY,
        "student_credential_encryption_key": STUDENT_CREDENTIAL_ENCRYPTION_KEY,
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
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    )


def refresh_headers(client: TestClient, secret: str = JWT_SECRET) -> dict[str, str]:
    refresh_token = client.cookies.get(REFRESH_COOKIE)
    assert refresh_token
    return {
        REFRESH_PROOF_HEADER: refresh_request_proof(refresh_token, secret),
    }


def test_health_checks_database_readiness(tmp_path: Path) -> None:
    database = tmp_path / "health.db"
    with make_client(settings_for(database)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    if os.name == "posix":
        assert database.stat().st_mode & 0o077 == 0


def test_rate_limit_expiration_has_a_supporting_index(tmp_path: Path) -> None:
    database = tmp_path / "rate-limit-index.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE login_rate_limits ("
            "limiter_key VARCHAR(96) PRIMARY KEY, "
            "window_started_at INTEGER NOT NULL, attempts INTEGER NOT NULL)"
        )
    with make_client(settings_for(database)):
        pass

    with sqlite3.connect(database) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(login_rate_limits)")
        }
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


def test_startup_enforces_security_data_retention(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "retention.db",
        quiz_result_retention_days=1,
        problem_report_retention_days=1,
    )
    app = create_app(settings)
    with TestClient(
        app,
        headers={"Origin": FRONTEND_ORIGIN},
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ):
        pass

    expired_at = datetime.now(UTC) - timedelta(days=2)
    with app.state.session_factory() as session:
        admin = session.scalar(select(User).where(User.is_admin.is_(True)))
        assert admin is not None
        quiz = Quiz(
            owner_id=admin.id,
            title="Expired quiz",
            question_count=1,
            easy_question_count=1,
            medium_question_count=0,
            hard_question_count=0,
        )
        session.add(quiz)
        session.flush()
        quiz_session = QuizSession(
            quiz_id=quiz.id,
            class_name="Expired class",
            join_code="OLD123",
            status="finished",
            started_at=expired_at,
        )
        session.add(quiz_session)
        session.flush()
        session.add(
            QuizParticipant(
                session_id=quiz_session.id,
                student_identifier="expired.student",
            )
        )
        session.add(
            ProblemReport(
                message="Expired report",
                page_path="/",
                created_at=expired_at,
            )
        )
        refresh_session = RefreshSession(
            token_hash="a" * 64,
            user_id=admin.id,
            expires_at=int(time()) - 1,
        )
        session.add(refresh_session)
        session.flush()
        session.add(
            RefreshSessionFamily(
                session_id=refresh_session.id,
                family_id="b" * 64,
            )
        )
        session.add(
            AuthenticationChallenge(
                token_id_hash="c" * 64,
                user_id=admin.id,
                purpose="two_factor_verification",
                expires_at=int(time()) - 1,
            )
        )
        session.commit()

    with make_client(settings):
        pass

    with sqlite3.connect(tmp_path / "retention.db") as database:
        for table in (
            "quiz_sessions",
            "quiz_participants",
            "problem_reports",
            "refresh_sessions",
            "refresh_session_families",
            "authentication_challenges",
        ):
            assert database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_question_batch_import_has_a_fixed_question_limit() -> None:
    question = {
        "prompt": "Question",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [{"label": "Answer", "is_correct": True}],
    }

    with pytest.raises(ValidationError):
        QuestionBatchImport.model_validate(
            {
                "version": 1,
                "question_bank": {"grade_level": "2de", "chapter": "Limits"},
                "questions": [question] * 501,
            }
        )


@pytest.mark.parametrize(
    ("schema", "identity_field"),
    [
        (LoginRequest, "username"),
        (StudentLoginRequest, "identifier"),
    ],
)
def test_login_schemas_preserve_password_characters(
    schema, identity_field: str
) -> None:
    password = "  exact password value  "

    payload = schema.model_validate({identity_field: "account", "password": password})

    assert payload.password == password


def test_login_accepts_the_exact_configured_password_with_spaces(
    tmp_path: Path,
) -> None:
    exact_password = "  strong admin password 2026  "
    with make_client(
        settings_for(
            tmp_path / "password-characters.db",
            admin_password=exact_password,
        )
    ) as client:
        altered = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": exact_password.strip()},
        )
        accepted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": exact_password},
        )

    assert altered.status_code == status.HTTP_401_UNAUTHORIZED
    assert accepted.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    "value",
    [
        '=HYPERLINK("https://attacker.example")',
        "+SUM(1, 1)",
        "-1+2",
        "@SUM(1, 1)",
        "\t=1+1",
        "\r=1+1",
        "  =1+1",
    ],
)
def test_csv_cells_neutralize_spreadsheet_formulas(value: str) -> None:
    assert safe_spreadsheet_cell(value) == f"'{value}"


def test_quiz_launches_when_question_points_overshoot_the_target(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "point-overshoot.db")) as client:
        admin_headers = login_admin(client)
        teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "overshoot.teacher",
                "display_name": "Overshoot Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client, "overshoot.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "6e C", "grade_level": "6e"},
        ).json()
        student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Lucas", "last_name": "Durand"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{student['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "6e", "chapter": "Overshoot"},
        ).json()
        for index in range(2):
            question = client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": f"Overshoot question {index}",
                            "points": 10,
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Correct", "is_correct": True},
                                {"label": "Wrong", "is_correct": False},
                            ],
                        }
                    )
                },
            )
            assert question.status_code == 201

        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Points trop élevés",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert quiz.status_code == 201

        launched = client.post(
            f"/api/quizzes/{quiz.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201


def test_quiz_launches_when_question_points_cannot_reach_the_target(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "point-fallback.db")) as client:
        admin_headers = login_admin(client)
        teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "fallback.teacher",
                "display_name": "Fallback Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client, "fallback.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "6e B", "grade_level": "6e"},
        ).json()
        student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Emma", "last_name": "Martin"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{student['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "6e", "chapter": "Fallback"},
        ).json()
        for index in range(2):
            question = client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": f"Fallback question {index}",
                            "points": 1,
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Correct", "is_correct": True},
                                {"label": "Wrong", "is_correct": False},
                            ],
                        }
                    )
                },
            )
            assert question.status_code == 201

        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Points inatteignables",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert quiz.status_code == 201

        launched = client.post(
            f"/api/quizzes/{quiz.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201


def test_login_rate_limit_buckets_use_a_secret_key() -> None:
    subject = "password:identity:known-user"
    secret = "private-rate-limit-key"
    limiter = LoginRateLimiter(5, 900, secret)
    expected_digest = hmac_new(
        secret.encode(),
        subject.encode(),
        sha256,
    ).hexdigest()[: LoginRateLimiter.BUCKET_HEX_CHARACTERS]

    assert limiter._account_key(subject) == f"account:{expected_digest}"
    assert limiter._account_key(subject) != LoginRateLimiter(
        5,
        900,
        "different-private-key",
    )._account_key(subject)


def test_public_information_describes_instance_settings(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "public-information.db",
        legal_host_name="Test host",
        legal_host_address="Test host address",
        privacy_controller_name="Test controller",
        accessibility_contact="Accessibility contact",
        refresh_token_days=9,
        quiz_result_retention_days=120,
    )
    with make_client(settings) as client:
        response = client.get("/api/public-information")

    assert response.status_code == 200
    assert "publisher" not in response.json()
    assert response.json()["host"] == {
        "name": "Test host",
        "address": "Test host address",
    }
    assert response.json()["privacy"]["controller_name"] == "Test controller"
    assert response.json()["privacy"]["quiz_result_retention_days"] == 120
    assert response.json()["cookies"]["authentication_max_age_days"] == 9
    assert response.json()["accessibility"]["contact"] == "Accessibility contact"
    assert response.headers["cache-control"] == "no-store"


def test_problem_reports_are_anonymous_and_admin_only(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "problem-reports.db")) as client:
        created = client.post(
            "/api/problem-reports",
            json={
                "message": "  Le bouton de validation ne répond pas.  ",
                "page_path": "/dashboard",
            },
        )
        assert created.status_code == 201
        assert created.json()["message"] == ("Le bouton de validation ne répond pas.")
        assert set(created.json()) == {
            "id",
            "message",
            "page_path",
            "created_at",
        }
        assert client.get("/api/problem-reports").status_code == 401

        headers = login_admin(client)
        reports = client.get("/api/problem-reports", headers=headers)
        assert reports.status_code == 200
        assert [report["id"] for report in reports.json()] == [created.json()["id"]]

        deleted = client.delete(
            f"/api/problem-reports/{created.json()['id']}",
            headers=headers,
        )
        assert deleted.status_code == 204
        assert client.get("/api/problem-reports", headers=headers).json() == []


def test_problem_reports_are_rate_limited(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "problem-report-rate-limit.db",
        problem_report_attempts=2,
    )
    with make_client(settings) as client:
        for index in range(2):
            response = client.post(
                "/api/problem-reports",
                json={
                    "message": f"Problème numéro {index}",
                    "page_path": "/",
                },
            )
            assert response.status_code == 201

        limited = client.post(
            "/api/problem-reports",
            json={"message": "Un autre problème", "page_path": "/"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0


@pytest.mark.parametrize(
    "page_path",
    ["https://example.test/page", "//example.test/page", "/valid\nspoofed"],
)
def test_problem_reports_reject_non_local_page_paths(
    tmp_path: Path, page_path: str
) -> None:
    with make_client(settings_for(tmp_path / "problem-report-path.db")) as client:
        response = client.post(
            "/api/problem-reports",
            json={"message": "A sufficiently detailed problem", "page_path": page_path},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_production_allows_missing_public_information(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "missing-public-information.db",
        frontend_origin="https://quiz.example.test",
        environment="production",
    )

    assert settings.legal_host_name == ""
    assert settings.privacy_controller_name == ""


def test_quiz_join_requires_an_authenticated_student(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "quiz-auth.db")) as client:
        missing_session = client.post(
            "/api/quizzes/join",
            json={"join_code": "ABC123"},
        )
        assert missing_session.status_code == 401
        invalid_session = client.post(
            "/api/quizzes/join",
            headers={"Authorization": "Bearer invalid-token"},
            json={"join_code": "ABC123"},
        )
        assert invalid_session.status_code == 401


def test_invalid_participant_tokens_share_a_bounded_session_rate_limit(
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
        assert different_token.status_code == 429


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
    refresh_token = client.cookies.get(REFRESH_COOKIE)
    assert refresh_token
    assert verified.json()["refresh_proof"] == refresh_request_proof(
        refresh_token,
        JWT_SECRET,
    )
    return (
        {"Authorization": f"Bearer {verified.json()['access_token']}"},
        secret,
    )


def login_admin(client: TestClient) -> dict[str, str]:
    headers, _ = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
    return headers


def test_teacher_lists_use_constant_query_counts(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "list-performance.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "performance.teacher",
                    "display_name": "Performance Teacher",
                    "password": "a-secure-performance-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client,
            "performance.teacher",
            "a-secure-performance-password",
        )
        for index in range(6):
            student_class = client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": f"Class {index}", "grade_level": "6e"},
            ).json()
            account = client.post(
                "/api/students",
                headers=teacher_headers,
                json={"first_name": "Student", "last_name": str(index)},
            ).json()
            assert (
                client.post(
                    f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                    headers=teacher_headers,
                ).status_code
                == 200
            )

        with client.app.state.session_factory() as session:
            professor_id = session.scalar(
                select(User.id).where(User.username == "performance.teacher")
            )
            assert professor_id is not None
            bank = QuestionBank(
                owner_id=professor_id,
                grade_level="6e",
                chapter="Performance",
            )
            session.add(bank)
            session.flush()
            quizzes = [
                Quiz(
                    owner_id=professor_id,
                    mode="exam",
                    title=f"Quiz {index}",
                    question_count=0,
                )
                for index in range(6)
            ]
            session.add_all(quizzes)
            session.flush()
            session.add_all(
                QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank.id)
                for quiz in quizzes
            )
            session.commit()

        engine = client.app.state.session_factory.kw["bind"]
        statements: list[str] = []

        def record_statement(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            assert (
                client.get("/api/students", headers=teacher_headers).status_code == 200
            )
            student_query_count = len(statements)
            statements.clear()
            assert (
                client.get("/api/classes", headers=teacher_headers).status_code == 200
            )
            class_query_count = len(statements)
            statements.clear()
            assert (
                client.get("/api/quizzes", headers=teacher_headers).status_code == 200
            )
            quiz_query_count = len(statements)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        assert student_query_count <= 4
        assert class_query_count <= 7
        assert quiz_query_count <= 5


def test_participant_maximum_scores_uses_constant_query_count(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "score-performance.db")) as client:
        with client.app.state.session_factory() as session:
            professor = User(
                username="score.teacher",
                display_name="Score Teacher",
                password_hash="unused",
            )
            session.add(professor)
            session.flush()
            student_class = StudentClass(
                owner_id=professor.id,
                name="Class",
                grade_level="6e",
            )
            bank = QuestionBank(
                owner_id=professor.id,
                grade_level="6e",
                chapter="Scores",
            )
            quiz = Quiz(
                owner_id=professor.id,
                mode="exam",
                title="Scores",
                question_count=1,
            )
            session.add_all([student_class, bank, quiz])
            session.flush()
            question = Question(
                question_bank_id=bank.id,
                prompt="Question",
                difficulty="easy",
                answer_mode="single",
                correction_mode="automatic",
            )
            session.add(question)
            session.flush()
            session.add(
                QuestionChoice(
                    question_id=question.id,
                    label="Answer",
                    is_correct=True,
                    points=2.5,
                    position=0,
                )
            )
            quiz_session = QuizSession(
                quiz_id=quiz.id,
                class_id=student_class.id,
                class_name="Class",
                join_code="SCORE1",
            )
            session.add(quiz_session)
            session.flush()
            participants = []
            for index in range(12):
                student = Student(
                    class_id=student_class.id,
                    identifier=f"student.{index}",
                    display_name=f"Student {index}",
                )
                session.add(student)
                session.flush()
                participant = QuizParticipant(
                    session_id=quiz_session.id,
                    student_id=student.id,
                    student_identifier=student.identifier,
                )
                session.add(participant)
                participants.append(participant)
                session.add(
                    QuizSessionStudentQuestion(
                        session_id=quiz_session.id,
                        student_id=student.id,
                        student_identifier=student.identifier,
                        question_id=question.id,
                        position=0,
                    )
                )
            session.commit()

            engine = client.app.state.session_factory.kw["bind"]
            statements: list[str] = []

            def record_statement(
                _connection, _cursor, statement, _parameters, _context, _executemany
            ) -> None:
                if statement.lstrip().upper().startswith("SELECT"):
                    statements.append(statement)

            event.listen(engine, "before_cursor_execute", record_statement)
            try:
                scores = participant_maximum_scores(
                    quiz_session, participants, session
                )
            finally:
                event.remove(engine, "before_cursor_execute", record_statement)

        assert scores == {participant.id: 2.5 for participant in participants}
        assert len(statements) == 3


def test_professor_manages_student_accounts_and_class_assignments(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "student-accounts.db")) as client:
        admin_headers = login_admin(client)
        created_teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "account.teacher",
                "display_name": "Account Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert created_teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client,
            "account.teacher",
            "a-secure-teacher-password",
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "4e A", "grade_level": "4e"},
        ).json()

        created = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Léa",
                "last_name": "Dupont",
            },
        )
        assert created.status_code == 201
        account = created.json()
        assert account["class_id"] is None
        assert "password" not in account
        assert account["identifier"] == "lea.dupont"
        generated_password = account["generated_password"]
        assert len(generated_password) == 10
        assert generated_password[:8].isalpha()
        assert generated_password[:8].isupper()
        assert generated_password[8:].isdigit()
        credentials_response = client.get(
            "/api/students/credentials", headers=teacher_headers
        )
        assert credentials_response.status_code == 200
        assert credentials_response.headers["cache-control"] == "no-store"
        assert credentials_response.json() == [
            {
                "identifier": "lea.dupont",
                "display_name": "Léa Dupont",
                "password": generated_password,
            }
        ]
        exported = client.get(
            "/api/students/credentials/export", headers=teacher_headers
        )
        assert exported.status_code == 200
        assert exported.headers["cache-control"] == "no-store"
        assert exported.headers["content-disposition"] == (
            'attachment; filename="student-credentials.json"'
        )
        assert exported.json() == {"students": credentials_response.json()}
        assert client.get("/api/students/credentials").status_code == 401
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "other.account.teacher",
                    "display_name": "Other Account Teacher",
                    "password": "another-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        other_teacher_headers, _ = complete_first_login(
            client,
            "other.account.teacher",
            "another-secure-teacher-password",
        )
        assert (
            client.get(
                "/api/students/credentials", headers=other_teacher_headers
            ).json()
            == []
        )
        with client.app.state.session_factory() as session:
            stored_account = session.scalar(
                select(StudentAccount).where(StudentAccount.id == account["id"])
            )
            assert stored_account is not None
            assert stored_account.encrypted_password
            assert generated_password not in stored_account.encrypted_password
        inactive_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Inactive",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/students/{inactive_account['id']}/update",
                headers=teacher_headers,
                json={
                    "identifier": inactive_account["identifier"],
                    "display_name": inactive_account["display_name"],
                    "is_active": False,
                },
            ).status_code
            == 200
        )

        logged_in = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "LEA.DUPONT",
                "password": account["generated_password"],
            },
        )
        assert logged_in.status_code == 200
        student_headers = {
            "Authorization": f"Bearer {logged_in.json()['access_token']}"
        }
        assert (
            client.get("/api/student-auth/me", headers=student_headers).json()[
                "display_name"
            ]
            == "Léa Dupont"
        )

        assigned = client.post(
            f"/api/classes/{student_class['id']}/accounts/{account['id']}",
            headers=teacher_headers,
        )
        assert assigned.status_code == 200
        assert assigned.json()["students"][0]["account_id"] == account["id"]
        class_credentials = client.get(
            "/api/students/credentials",
            headers=teacher_headers,
            params={"class_id": student_class["id"]},
        )
        assert class_credentials.status_code == 200
        assert [item["identifier"] for item in class_credentials.json()] == [
            account["identifier"]
        ]
        assert (
            client.get(
                "/api/students/credentials",
                headers=other_teacher_headers,
                params={"class_id": student_class["id"]},
            ).status_code
            == 404
        )
        listed_accounts = client.get("/api/students", headers=teacher_headers).json()
        assert all("password" not in item for item in listed_accounts)
        assert (
            next(item for item in listed_accounts if item["id"] == account["id"])[
                "class_name"
            ]
            == "4e A"
        )
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"class_id": student_class["id"]},
            ).json()
        ] == [account["id"]]
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"unassigned": True},
            ).json()
        ] == [inactive_account["id"]]
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"is_active": False},
            ).json()
        ] == [inactive_account["id"]]
        assert (
            client.get(
                "/api/students",
                headers=teacher_headers,
                params={"class_id": student_class["id"], "unassigned": True},
            ).status_code
            == 422
        )

        unassigned = client.delete(
            f"/api/classes/{student_class['id']}/accounts/{account['id']}",
            headers=teacher_headers,
        )
        assert unassigned.status_code == 204
        listed_accounts = client.get("/api/students", headers=teacher_headers).json()
        assert (
            next(item for item in listed_accounts if item["id"] == account["id"])[
                "class_id"
            ]
            is None
        )


def test_training_quiz_is_self_started_ungraded_and_returns_feedback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "training-quiz.db"
    with make_client(settings_for(database_path)) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "training.teacher",
                    "display_name": "Training Teacher",
                    "password": "a-secure-training-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "training.teacher", "a-secure-training-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "3e A", "grade_level": "3e"},
        ).json()
        account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Training",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "3e", "chapter": "Training"},
        ).json()
        question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Two plus two?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {"label": "Four", "is_correct": True},
                            {"label": "Five", "is_correct": False},
                        ],
                    }
                )
            },
        ).json()
        correct_choice_id = next(
            choice["id"] for choice in question["choices"] if choice["is_correct"]
        )
        manual_training = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "mode": "training",
                "title": "Mental arithmetic",
                "question_bank_ids": [bank["id"]],
                "duration_seconds": 60,
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert manual_training.status_code == 422
        training_banks = client.put(
            f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
            headers=teacher_headers,
            json={"question_bank_ids": [bank["id"]]},
        )
        assert training_banks.status_code == 200
        assert training_banks.json()[0]["id"] == bank["id"]
        other_level_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Wrong level"},
        ).json()
        assert (
            client.put(
                f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
                headers=teacher_headers,
                json={"question_bank_ids": [other_level_bank["id"]]},
            ).status_code
            == 422
        )
        assert client.get("/api/quizzes", headers=teacher_headers).json() == []
        assert (
            client.get(
                f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
                headers=teacher_headers,
            ).json()[0]["id"]
            == bank["id"]
        )
        other_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "3e B", "grade_level": "3e"},
        ).json()
        assert (
            client.get(
                f"/api/quizzes/training/classes/{other_class['id']}/question-banks",
                headers=teacher_headers,
            ).json()
            == []
        )
        other_class_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Other",
                "last_name": "Class Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{other_class['id']}/accounts/{other_class_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        other_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "other.class.student",
                "password": other_class_account["generated_password"],
            },
        ).json()
        other_student_headers = {
            "Authorization": f"Bearer {other_login['access_token']}"
        }
        assert (
            client.get("/api/quizzes/training", headers=other_student_headers).json()
            == []
        )
        assert (
            client.post(
                f"/api/quizzes/training/{bank['id']}/start",
                headers=other_student_headers,
            ).status_code
            == 404
        )

        login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "training.student",
                "password": account["generated_password"],
            },
        ).json()
        student_headers = {"Authorization": f"Bearer {login['access_token']}"}
        available = client.get("/api/quizzes/training", headers=student_headers)
        assert available.status_code == 200
        assert available.json()[0]["chapter"] == "Training"
        started = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert started.status_code == 201
        assert started.json()["status"] == "in_progress"
        assert started.json()["quiz_title"] == "Training"
        redrawn = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert redrawn.status_code == 201
        assert redrawn.json()["join_code"] != started.json()["join_code"]

        other_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Other",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        with sqlite3.connect(database_path) as database:
            assert (
                database.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM quiz_session_questions"
                ).fetchone()[0]
                == 1
            )
        replaced_attempt = client.post(
            f"/api/quizzes/student/sessions/{started.json()['join_code']}/answer",
            headers={"X-Quiz-Token": started.json()["participant_token"]},
            json={"selected_choice_ids": [correct_choice_id]},
        )
        assert replaced_attempt.status_code == 401
        updated_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Two plus two, exactly?",
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {
                                "id": choice["id"],
                                "label": choice["label"],
                                "is_correct": choice["is_correct"],
                            }
                            for choice in question["choices"]
                        ],
                    }
                )
            },
        )
        assert updated_question.status_code == 200
        redrawn_answered = client.post(
            f"/api/quizzes/student/sessions/{redrawn.json()['join_code']}/answer",
            headers={"X-Quiz-Token": redrawn.json()["participant_token"]},
            json={"selected_choice_ids": [correct_choice_id]},
        )
        assert redrawn_answered.status_code == 200
        assert redrawn_answered.json()["status"] == "finished"
        assert redrawn_answered.json()["training_feedback"] == {
            "question_id": question["id"],
            "is_correct": True,
            "correct_choice_ids": [correct_choice_id],
            "expected_answer": None,
            "submitted_answer": None,
            "requires_manual_review": False,
        }
        assert (
            client.get("/api/quizzes/sessions/results", headers=teacher_headers).json()
            == []
        )
        class_after_training = client.get(
            "/api/classes", headers=teacher_headers
        ).json()[0]
        assert class_after_training["completed_quiz_count"] == 0
        assert class_after_training["latest_quiz_title"] is None
        with sqlite3.connect(database_path) as database:
            assert (
                database.execute("SELECT COUNT(*) FROM quiz_answers").fetchone()[0] == 1
            )
            assert (
                database.execute("SELECT COUNT(*) FROM quiz_sessions").fetchone()[0]
                == 1
            )
        history = client.get(
            f"/api/quizzes/training/{bank['id']}/history",
            headers=student_headers,
        )
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["score"] == 1
        assert history.json()[0]["maximum_score"] == 1

        second_question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Three plus three?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "choices": [
                            {"label": "Six", "is_correct": True},
                            {"label": "Seven", "is_correct": False},
                        ],
                    }
                )
            },
        )
        assert second_question.status_code == 201
        disposable_training = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert disposable_training.status_code == 201
        drawn_question_id = disposable_training.json()["question"]["id"]
        assert (
            client.delete(
                f"/api/question-banks/questions/{drawn_question_id}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        discarded_state = client.get(
            f"/api/quizzes/student/sessions/{disposable_training.json()['join_code']}",
            headers={"X-Quiz-Token": disposable_training.json()["participant_token"]},
        )
        assert discarded_state.status_code == 401
        replacement_question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Four plus four?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "choices": [
                            {"label": "Eight", "is_correct": True},
                            {"label": "Nine", "is_correct": False},
                        ],
                    }
                )
            },
        )
        assert replacement_question.status_code == 201
        exam = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Scored arithmetic",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert exam.status_code == 201
        launched_exam = client.post(
            f"/api/quizzes/{exam.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched_exam.status_code == 201
        joined_exam = client.post(
            "/api/quizzes/join",
            headers=student_headers,
            json={"join_code": launched_exam.json()["join_code"]},
        )
        assert joined_exam.status_code == 201
        with sqlite3.connect(database_path) as database:
            assert "points" not in {
                row[1] for row in database.execute("PRAGMA table_info(questions)")
            }
            assert "points" not in {
                row[1]
                for row in database.execute("PRAGMA table_info(quiz_session_questions)")
            }
            common_question_ids = {
                row[0]
                for row in database.execute(
                    "SELECT question_id FROM quiz_session_questions "
                    "WHERE session_id = ?",
                    (launched_exam.json()["id"],),
                )
            }
            student_question_ids = [
                row[0]
                for row in database.execute(
                    "SELECT question_id FROM quiz_session_student_questions "
                    "WHERE session_id = ? AND student_identifier = ? ORDER BY position",
                    (launched_exam.json()["id"], account["identifier"]),
                )
            ]
        assert common_question_ids == set()
        assert len(student_question_ids) == 2
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched_exam.json()['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        student_exam_state = client.get(
            f"/api/quizzes/student/sessions/{launched_exam.json()['join_code']}",
            headers={"X-Quiz-Token": joined_exam.json()["participant_token"]},
        )
        assert student_exam_state.status_code == 200
        assert student_exam_state.json()["question"]["id"] == student_question_ids[0]


def test_legacy_quiz_percentages_keep_the_previous_draw_distribution() -> None:
    assert legacy_difficulty_counts(
        3,
        {"easy": 50, "medium": 50, "hard": 0},
        {"easy": 2, "medium": 1, "hard": 0},
    ) == {"easy": 2, "medium": 1, "hard": 0}

    assert legacy_difficulty_counts(
        4,
        {"easy": 75, "medium": 25, "hard": 0},
        {"easy": 1, "medium": 2, "hard": 1},
    ) == {"easy": 1, "medium": 2, "hard": 1}


def test_legacy_quiz_migration_persists_available_difficulty_counts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-quiz-percentages.db"
    with make_client(settings_for(database_path)):
        pass
    with sqlite3.connect(database_path) as database:
        owner_id = database.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
        database.execute(
            "INSERT INTO question_banks "
            "(id, owner_id, grade_level, chapter, created_at) "
            "VALUES (1, ?, '3e', 'Legacy', CURRENT_TIMESTAMP)",
            (owner_id,),
        )
        database.executemany(
            "INSERT INTO questions "
            "(id, question_bank_id, prompt, difficulty, answer_mode, "
            "answer_mode_disclosed, correction_mode, created_at) "
            "VALUES (?, 1, ?, ?, 'single', 1, 'automatic', CURRENT_TIMESTAMP)",
            [
                (1, "Easy one", "easy"),
                (2, "Easy two", "easy"),
                (3, "Medium one", "medium"),
            ],
        )
        database.execute("DROP TABLE quizzes")
        database.execute(
            "CREATE TABLE quizzes ("
            "id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, title TEXT NOT NULL, "
            "question_count INTEGER NOT NULL, easy_percentage INTEGER NOT NULL, "
            "medium_percentage INTEGER NOT NULL, hard_percentage INTEGER NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )
        database.execute(
            "INSERT INTO quizzes VALUES "
            "(1, ?, 'Legacy quiz', 3, 50, 50, 0, CURRENT_TIMESTAMP)",
            (owner_id,),
        )
        database.execute(
            "INSERT INTO quiz_question_banks (quiz_id, question_bank_id) VALUES (1, 1)"
        )
        database.commit()

    create_app(settings_for(database_path))

    with sqlite3.connect(database_path) as database:
        migrated = database.execute(
            "SELECT question_count, easy_question_count, "
            "medium_question_count, hard_question_count FROM quizzes WHERE id = 1"
        ).fetchone()
    assert migrated == (3, 2, 1, 0)


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

        predictable_password = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.weak",
                "display_name": "Teacher Weak",
                "password": "a" * 16,
            },
        )
        assert predictable_password.status_code == 422

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
        assert student_class["latest_quiz_title"] is None
        assert student_class["latest_quiz_at"] is None
        grade_levels = client.get("/api/grade-levels", headers=teacher_headers).json()
        assert [level["name"] for level in grade_levels] == [
            "1ere",
            "2nd",
            "5e",
            "Tle",
        ]
        duplicate_grade_level = client.post(
            "/api/grade-levels",
            headers=teacher_headers,
            json={"name": " 5E "},
        )
        assert duplicate_grade_level.status_code == 201
        fifth_grade = next(
            level for level in grade_levels if level["name"] == "5e"
        )
        assert duplicate_grade_level.json()["id"] == fifth_grade["id"]
        assert (
            client.delete(
                f"/api/grade-levels/{fifth_grade['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )
        unused_level = client.post(
            "/api/grade-levels",
            headers=teacher_headers,
            json={"name": " 4e "},
        )
        assert unused_level.status_code == 201
        assert unused_level.json()["name"] == "4e"
        assert (
            client.delete(
                f"/api/grade-levels/{unused_level.json()['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": "5e B", "grade_level": "5e"},
            ).status_code
            == 409
        )

        student_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Martin",
                "last_name": "Giraud",
            },
        ).json()
        assigned_class = client.post(
            f"/api/classes/{student_class['id']}/accounts/{student_account['id']}",
            headers=teacher_headers,
        )
        assert assigned_class.status_code == 200
        assert (
            assigned_class.json()["students"][0]["account_id"] == student_account["id"]
        )
        exam_student_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "martin.giraud",
                "password": student_account["generated_password"],
            },
        )
        assert exam_student_login.status_code == 200
        exam_account_headers = {
            "Authorization": f"Bearer {exam_student_login.json()['access_token']}"
        }
        updated_class = client.post(
            f"/api/classes/{student_class['id']}/update",
            headers=teacher_headers,
            json={"name": "5e B", "grade_level": "Cinquième"},
        )
        assert updated_class.status_code == 200
        assert updated_class.json()["grade_level"] == "Cinquième"
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/students",
                headers=teacher_headers,
                json={"display_name": "Legacy student"},
            ).status_code
            == 404
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
                    "image": {
                        "content_type": "image/png",
                        "data_base64": b64encode(VALID_PNG).decode(),
                    },
                    "code_language": "python",
                    "code_content": "print(1 / 2)",
                },
                {"label": "1/3", "is_correct": False},
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
        assert "points" not in question
        assert question["has_image"] is True
        assert "correction_mode" not in question
        assert question["answer_mode_disclosed"] is False
        assert question["code_language"] == "python"
        assert "return value / 2" in question["code_content"]
        assert [choice["is_correct"] for choice in question["choices"]] == [
            True,
            False,
        ]
        assert [choice["points"] for choice in question["choices"]] == [1, 0]
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
        assert "points" not in exported_batch["questions"][0]
        assert exported_batch["questions"][0]["code_language"] == "python"
        assert [
            choice["points"] for choice in exported_batch["questions"][0]["choices"]
        ] == [1, 0]
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
        assert (
            "Niveaux de classe disponibles"
            in example_batch["question_bank"]["_comment_grade_level"]
        )
        assert "3e" in example_batch["question_bank"]["_comment_grade_level"]
        assert {item["answer_mode"] for item in example_batch["questions"]} == {
            "single",
            "multiple",
            "written",
        }
        assert all("correction_mode" not in item for item in example_batch["questions"])
        assert all("points" not in item for item in example_batch["questions"])
        assert any(item["image"] for item in example_batch["questions"])
        assert any(item["code_content"] for item in example_batch["questions"])
        assert (
            next(
                item
                for item in example_batch["questions"]
                if item["answer_mode"] == "written"
            )["response_language"]
            == "python"
        )
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
        assert all(
            "points" in choice
            for item in example_batch["questions"]
            for choice in item["choices"]
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
        assert (
            next(
                question
                for question in imported_example.json()["questions"]
                if question["answer_mode"] == "written"
            )["response_language"]
            == "python"
        )

        invalid_quiz_counts = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Révisions invalides",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "easy_question_count": 2,
                "medium_question_count": 1,
                "hard_question_count": 0,
            },
        )
        assert invalid_quiz_counts.status_code == 422

        created_quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": " Révisions   générales ",
                "source_language": "en",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert created_quiz.status_code == 201
        quiz = created_quiz.json()
        assert quiz["title"] == "Révisions générales"
        assert quiz["source_language"] == "en"
        assert quiz["question_count"] == 3
        assert quiz["easy_question_count"] == 1
        assert quiz["medium_question_count"] == 1
        assert quiz["hard_question_count"] == 1
        assert {
            "easy_points",
            "medium_points",
            "hard_points",
        }.isdisjoint(quiz)
        assert quiz["duration_seconds"] == 900
        assert quiz["allow_previous_questions"] is False
        assert quiz["same_questions_for_all"] is False
        assert len(quiz["question_banks"]) == 1
        assert quiz["question_banks"][0]["easy_question_count"] == 1
        assert quiz["question_banks"][0]["medium_question_count"] == 1
        assert quiz["question_banks"][0]["hard_question_count"] == 1
        assert (
            client.get("/api/quizzes", headers=teacher_headers).json()[0]["id"]
            == quiz["id"]
        )
        updated_quiz = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=teacher_headers,
            json={
                "title": "Révisions générales modifiées",
                "source_language": "en",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "duration_seconds": 2400,
                "allow_previous_questions": True,
                "same_questions_for_all": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert updated_quiz.status_code == 200
        quiz = updated_quiz.json()
        assert quiz["title"] == "Révisions générales modifiées"
        assert quiz["source_language"] == "en"
        assert quiz["duration_seconds"] == 2400
        assert quiz["allow_previous_questions"] is True
        assert quiz["same_questions_for_all"] is False

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

        late_student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Late",
                "last_name": "Student",
            },
        )
        assert late_student.status_code == 201
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/"
                f"{late_student.json()['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        late_student_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "late.student",
                "password": late_student.json()["generated_password"],
            },
        )
        late_account_headers = {
            "Authorization": f"Bearer {late_student_login.json()['access_token']}"
        }

        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201
        quiz_session = launched.json()
        assert quiz_session["class_name"] == "Cinquième 5e B"
        assert quiz_session["status"] == "waiting"
        assert len(quiz_session["join_code"]) == 6
        with sqlite3.connect(tmp_path / "test.db") as connection:
            student_count = connection.execute(
                "SELECT COUNT(*) FROM students WHERE class_id = ?",
                (student_class["id"],),
            ).fetchone()[0]
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = ?",
                    (quiz_session["id"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM quiz_session_student_questions "
                    "WHERE session_id = ?",
                    (quiz_session["id"],),
                ).fetchone()[0]
                == student_count * quiz["question_count"]
            )
            assigned_points = connection.execute(
                "SELECT assigned.student_id, SUM(CASE WHEN choices.points > 0 "
                "THEN choices.points ELSE 0 END) "
                "FROM quiz_session_student_questions AS assigned "
                "JOIN question_choices AS choices "
                "ON choices.question_id = assigned.question_id "
                "WHERE assigned.session_id = ? GROUP BY assigned.student_id",
                (quiz_session["id"],),
            ).fetchall()
            assert assigned_points
            assert all(total == 18 for _, total in assigned_points)
            assert {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT question_total FROM ("
                    "SELECT assigned.student_id, assigned.question_id, "
                    "SUM(CASE WHEN choices.points > 0 THEN choices.points "
                    "ELSE 0 END) AS question_total "
                    "FROM quiz_session_student_questions AS assigned "
                    "JOIN question_choices AS choices "
                    "ON choices.question_id = assigned.question_id "
                    "WHERE assigned.session_id = ? "
                    "GROUP BY assigned.student_id, assigned.question_id)",
                    (quiz_session["id"],),
                )
            } == {3, 6, 9}
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()[0]["id"]
            == quiz_session["id"]
        )
        assert (
            client.post(
                f"/api/quizzes/{quiz['id']}/update",
                headers=teacher_headers,
                json={
                    "title": quiz["title"],
                    "source_language": "en",
                    "question_bank_ids": [
                        imported_example.json()["question_bank"]["id"]
                    ],
                    "duration_seconds": 2400,
                    "allow_previous_questions": True,
                    "easy_question_count": 1,
                    "medium_question_count": 1,
                    "hard_question_count": 1,
                },
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )

        legacy_join_payload = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={
                "join_code": quiz_session["join_code"],
                "student_identifier": "martin.giraud",
            },
        )
        assert legacy_join_payload.status_code == 422
        joined = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"].lower()},
        )
        assert joined.status_code == 201
        assert joined.json()["quiz_title"] == quiz["title"]
        assert joined.json()["source_language"] == "en"
        assert joined.json()["student_name"] == "Martin Giraud"
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
                json={"join_code": quiz_session["join_code"]},
            ).status_code
            == 401
        )
        joined_again = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"]},
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
        left = client.post(f"{student_state_url}/leave", headers=student_headers)
        assert left.status_code == 204
        assert client.get(student_state_url, headers=student_headers).status_code == 401
        waiting_room_after_leave = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        )
        assert waiting_room_after_leave.status_code == 200
        assert waiting_room_after_leave.json()["participant_count"] == 0
        assert waiting_room_after_leave.json()["participants"] == []

        rejoined = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert rejoined.status_code == 201
        assert rejoined.json()["participant_token"] != participant_token
        participant_token = rejoined.json()["participant_token"]
        student_headers = {"X-Quiz-Token": participant_token}
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()["participant_count"]
            == 1
        )
        assert (
            client.get(student_state_url, headers=student_headers).json()[
                "source_language"
            ]
            == "en"
        )
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "waiting"
        )
        waiting_violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert waiting_violation.status_code == 204
        waiting_participant = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert waiting_participant["violation_count"] == 0

        started = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start",
            headers=teacher_headers,
        )
        assert started.status_code == 200
        assert started.json()["status"] == "in_progress"
        assert started.json()["started_at"] is not None
        assert started.json()["ends_at"] is not None
        late_join = client.post(
            "/api/quizzes/join",
            headers=late_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert late_join.status_code == 403
        assert late_join.json()["detail"] == "Impossible de rejoindre ce quiz"
        original_ends_at = started.json()["ends_at"]
        paused = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/pause",
            headers=teacher_headers,
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        paused_student_state = client.get(
            student_state_url,
            headers=student_headers,
        ).json()
        assert paused_student_state["status"] == "paused"
        assert paused_student_state["question"] is None
        assert (
            client.post(
                f"{student_state_url}/answer",
                headers=student_headers,
                json={},
            ).status_code
            == 409
        )
        resumed = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/resume",
            headers=teacher_headers,
        )
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "in_progress"
        assert resumed.json()["ends_at"] >= original_ends_at
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
                json={"join_code": quiz_session["join_code"]},
            ).status_code
            == 401
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
            repeated_state = client.get(
                student_state_url,
                headers=student_headers,
            ).json()
            assert [
                choice["id"] for choice in repeated_state["question"]["choices"]
            ] == [choice["id"] for choice in state_payload["question"]["choices"]]
            assert [
                choice["position"] for choice in state_payload["question"]["choices"]
            ] == list(range(len(state_payload["question"]["choices"])))

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
                    "written_answer": "Réponse rédactionnelle très longue. " * 200
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
                assert previous.json()["accessible_question_numbers"] == [1, 2, 3]
                assert previous.json()["has_answered"] is True
                assert (
                    previous.json()["selected_choice_ids"] is not None
                    or previous.json()["written_answer"] is not None
                )
                assert collect_keys(previous.json()).isdisjoint(
                    {"is_correct", "points", "correction_mode", "score"}
                )
                returned_to_current = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 3},
                )
                assert returned_to_current.status_code == 200
                assert returned_to_current.json()["question_number"] == 3
                previous = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 2},
                )
                assert previous.status_code == 200
                paused_with_answer = client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/pause",
                    headers=teacher_headers,
                )
                assert paused_with_answer.status_code == 200
                answer_during_pause = client.get(
                    student_state_url,
                    headers=student_headers,
                ).json()
                assert answer_during_pause["status"] == "paused"
                assert answer_during_pause["question"] is None
                assert (
                    answer_during_pause["selected_choice_ids"]
                    == previous.json()["selected_choice_ids"]
                )
                assert (
                    answer_during_pause["written_answer"]
                    == previous.json()["written_answer"]
                )
                resumed_with_answer = client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/resume",
                    headers=teacher_headers,
                )
                assert resumed_with_answer.status_code == 200
                answer_after_resume = client.get(
                    student_state_url,
                    headers=student_headers,
                ).json()
                assert (
                    answer_after_resume["selected_choice_ids"]
                    == previous.json()["selected_choice_ids"]
                )
                assert (
                    answer_after_resume["written_answer"]
                    == previous.json()["written_answer"]
                )
                resubmitted = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json=answer_payload,
                )
                assert resubmitted.status_code == 200
                assert resubmitted.json()["question_number"] == 3

        assert teacher_state["status"] == "finished"
        student_history = client.get(
            "/api/quizzes/student/results",
            headers=exam_account_headers,
        )
        assert student_history.status_code == 200
        assert student_history.json() == []
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
        assert results.json()[0]["class_name"] == "Cinquième 5e B"
        assert results.json()[0]["participants"][0]["score"] > 0
        maximum_score = results.json()[0]["participants"][0]["maximum_score"]
        assert maximum_score > 0
        assert results.json()[0]["median_maximum_score"] == maximum_score
        assert results.json()[0]["participants"][0]["pending_manual_grading_count"] == 1
        original_ends_at = results.json()[0]["ends_at"]

        exported_results = client.get(
            "/api/quizzes/sessions/results/export",
            headers=teacher_headers,
            params={"class_id": student_class["id"], "quiz_id": quiz["id"]},
        )
        assert exported_results.status_code == 200
        assert exported_results.headers["content-type"].startswith("text/csv")
        assert "attachment;" in exported_results.headers["content-disposition"]
        assert exported_results.text.startswith("\ufeffclass,quiz,date,")
        assert quiz["title"] in exported_results.text
        assert teacher_state["participants"][0]["student_identifier"] in (
            exported_results.text
        )

        all_quiz_results = client.get(
            "/api/quizzes/sessions/results/export",
            headers=teacher_headers,
            params={"class_id": student_class["id"]},
        )
        assert all_quiz_results.status_code == 200
        assert quiz["title"] in all_quiz_results.text

        edited_quiz = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=teacher_headers,
            json={
                "title": "Nouveau titre pour les prochaines sessions",
                "source_language": "de",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "duration_seconds": 60,
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert edited_quiz.status_code == 200
        historical_result = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()[0]
        assert historical_result["quiz_title"] == quiz["title"]
        assert historical_result["ends_at"] == original_ends_at
        historical_search = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
            params={"quiz_search": quiz["title"]},
        )
        assert [result["id"] for result in historical_search.json()] == [
            quiz_session["id"]
        ]
        renamed_search = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
            params={"quiz_search": edited_quiz.json()["title"]},
        )
        assert renamed_search.json() == []
        historical_student_state = client.get(
            student_state_url,
            headers=student_headers,
        ).json()
        assert historical_student_state["quiz_title"] == quiz["title"]
        assert historical_student_state["source_language"] == "en"
        assert historical_student_state["allow_previous_questions"] is True
        assert (
            client.get("/api/quizzes/sessions/results", headers=headers).status_code
            == 403
        )
        reviewed_answers = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}/participants/"
            f"{teacher_state['participants'][0]['id']}/answers",
            headers=teacher_headers,
        )
        assert reviewed_answers.status_code == 200
        assert len(reviewed_answers.json()) == 3
        assert all(
            answer["is_correct"] is True
            for answer in reviewed_answers.json()
            if answer["answer_mode"] != "written"
        )
        written_review = next(
            answer
            for answer in reviewed_answers.json()
            if answer["answer_mode"] == "written"
        )
        assert written_review["submitted_answers"]
        assert len(written_review["submitted_answers"][0]) > 4000
        assert written_review["expected_answers"]
        assert written_review["score"] == 0
        assert written_review["is_graded"] is False
        assert written_review["is_correct"] is None
        unpublished = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
            headers=teacher_headers,
        )
        assert unpublished.status_code == 409
        manually_graded = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/answers/"
            f"{written_review['id']}/grade",
            headers=teacher_headers,
            json={"score": written_review["max_score"]},
        )
        assert manually_graded.status_code == 200
        assert manually_graded.json()["is_graded"] is True
        assert manually_graded.json()["score"] == written_review["max_score"]
        assert manually_graded.json()["is_correct"] is True
        graded_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        assert graded_results[0]["participants"][0]["pending_manual_grading_count"] == 0
        published = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
            headers=teacher_headers,
        )
        assert published.status_code == 200
        assert published.json()["grades_published_at"] is not None
        graded_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        published_history = client.get(
            "/api/quizzes/student/results",
            headers=exam_account_headers,
        ).json()[0]
        assert published_history["session_id"] == quiz_session["id"]
        assert published_history["quiz_title"] == quiz["title"]
        assert (
            published_history["score"] == published.json()["participants"][0]["score"]
        )
        assert published_history["maximum_score"] == maximum_score
        assert len(published_history["answers"]) == 3
        assert all(answer["is_correct"] for answer in published_history["answers"])
        assert all(
            {"score", "max_score", "is_graded"}.isdisjoint(answer)
            for answer in published_history["answers"]
        )
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/answers/"
                f"{written_review['id']}/grade",
                headers=teacher_headers,
                json={"score": 0},
            ).status_code
            == 409
        )
        regraded_question = next(
            question
            for question in preview.json()
            if question["answer_mode"] != "written"
        )
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
        assert regraded.status_code == 409
        assert regraded.json()["detail"] == (
            "Cette question est utilisée par un quiz déjà lancé"
        )
        refreshed_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        assert refreshed_results == graded_results

        makeup_created = client.post(
            "/api/quizzes/makeup/sessions",
            headers=teacher_headers,
            json={
                "class_id": student_class["id"],
                "quiz_ids": [quiz["id"]],
            },
        )
        assert makeup_created.status_code == 201
        makeup = makeup_created.json()
        assert (
            makeup["quizzes"][0]["duration_seconds"]
            == edited_quiz.json()["duration_seconds"]
        )
        makeup_joined = client.post(
            "/api/quizzes/makeup/join",
            headers=exam_account_headers,
            json={"join_code": makeup["join_code"]},
        )
        assert makeup_joined.status_code == 200
        assert [item["id"] for item in makeup_joined.json()["quizzes"]] == [quiz["id"]]
        makeup_selected = client.post(
            f"/api/quizzes/makeup/{makeup['join_code']}/select",
            headers=exam_account_headers,
            json={"quiz_id": quiz["id"]},
        )
        assert makeup_selected.status_code == 201
        assert makeup_selected.json()["status"] == "waiting"
        assert makeup_selected.json()["quiz_title"] == edited_quiz.json()["title"]
        assert (
            client.post(
                f"/api/quizzes/makeup/{makeup['join_code']}/select",
                headers=exam_account_headers,
                json={"quiz_id": quiz["id"]},
            ).status_code
            == 409
        )
        makeup_started = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
            headers=teacher_headers,
        )
        assert makeup_started.status_code == 200
        assert makeup_started.json()["status"] == "in_progress"
        makeup_state = client.get(
            f"/api/quizzes/student/sessions/{makeup_selected.json()['join_code']}",
            headers={"X-Quiz-Token": makeup_selected.json()["participant_token"]},
        )
        assert makeup_state.status_code == 200
        assert makeup_state.json()["status"] == "in_progress"
        assert makeup_state.json()["question"] is not None
        makeup_finished = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/finish",
            headers=teacher_headers,
        )
        assert makeup_finished.status_code == 200
        assert makeup_finished.json()["status"] == "finished"

        cancelled_launch = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert cancelled_launch.status_code == 201
        cancelled_session = cancelled_launch.json()
        cancelled_join = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": cancelled_session["join_code"]},
        )
        assert cancelled_join.status_code == 201
        cancelled_headers = {"X-Quiz-Token": cancelled_join.json()["participant_token"]}
        cancelled = client.post(
            f"/api/quizzes/sessions/{cancelled_session['id']}/cancel",
            headers=teacher_headers,
        )
        assert cancelled.status_code == 204
        cancelled_student_state = client.get(
            f"/api/quizzes/student/sessions/{cancelled_session['join_code']}",
            headers=cancelled_headers,
        )
        assert cancelled_student_state.status_code == 401
        assert cancelled_session["id"] not in {
            item["id"]
            for item in client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
        }
        assert (
            client.get(
                f"/api/quizzes/sessions/{cancelled_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        expiring_launch = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert expiring_launch.status_code == 201
        expiring_session = expiring_launch.json()
        expiring_join = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": expiring_session["join_code"]},
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
        assert completed_class["completed_quiz_count"] == 2
        assert completed_class["latest_quiz_title"] == edited_quiz.json()["title"]
        assert completed_class["latest_quiz_at"] is not None
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "finished"
        )
        assert (
            client.delete(
                f"/api/students/{student_account['id']}",
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


def test_existing_question_choices_gain_neutral_legacy_points(tmp_path: Path) -> None:
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
        database.executemany(
            """
            INSERT INTO question_choices (
                id,
                question_id,
                label,
                is_correct,
                position
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "Correct answer", True, 0),
                (2, 1, "Incorrect answer", False, 1),
            ],
        )

    create_app(settings_for(database_path))

    with sqlite3.connect(database_path) as database:
        columns = {
            row[1] for row in database.execute("PRAGMA table_info(question_choices)")
        }
        points = list(
            database.execute("SELECT points FROM question_choices ORDER BY position")
        )
    assert {
        "points",
        "image_data",
        "image_content_type",
        "code_language",
        "code_content",
    }.issubset(columns)
    assert points == [(0.0,), (0.0,)]


def test_legacy_students_without_accounts_are_deleted(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-students.db"
    create_app(settings_for(database_path))
    with sqlite3.connect(database_path) as database:
        database.execute(
            "INSERT INTO students "
            "(id, class_id, account_id, identifier, display_name, created_at) "
            "VALUES (1, 999, NULL, 'legacy.student', 'Legacy Student', "
            "CURRENT_TIMESTAMP)"
        )
        database.commit()

    create_app(settings_for(database_path))

    with sqlite3.connect(database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0


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
    assert {
        "paused_at",
        "paused_duration_seconds",
        "quiz_title",
        "source_language",
        "duration_seconds",
        "allow_previous_questions",
    }.issubset(session_columns)
    assert {"student_id", "student_display_name", "left_at"}.issubset(
        participant_columns
    )


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

        refreshed = client.post(
            "/api/auth/refresh",
            headers=refresh_headers(client),
        )
        assert refreshed.status_code == 200
        second_refresh = client.cookies.get(REFRESH_COOKIE)
        assert second_refresh and second_refresh != first_refresh
        assert refreshed.json()["refresh_proof"] == refresh_request_proof(
            second_refresh,
            JWT_SECRET,
        )
        with sqlite3.connect(database_path) as database:
            second_expires_at = database.execute(
                "SELECT expires_at FROM refresh_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        assert second_expires_at == first_expires_at

        client.cookies.set(
            REFRESH_COOKIE,
            first_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        first_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )

        client.cookies.set(
            REFRESH_COOKIE,
            second_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        second_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )

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
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
        assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_and_logout_require_the_session_proof(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "refresh-proof.db")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert client.post("/api/auth/refresh").status_code == 403
        assert (
            client.post(
                "/api/auth/refresh",
                headers={REFRESH_PROOF_HEADER: "invalid-proof"},
            ).status_code
            == 403
        )
        assert client.post("/api/auth/logout").status_code == 403

        refreshed = client.post(
            "/api/auth/refresh",
            headers=refresh_headers(client),
        )
        assert refreshed.status_code == 200


def test_later_login_requires_two_factor_code(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )

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
        assert (
            known_device.post(
                "/api/auth/refresh",
                headers=refresh_headers(known_device),
            ).status_code
            == 200
        )

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
        other_unknown = client.post(
            "/api/auth/login",
            json={"username": "another-unknown", "password": "incorrect-password"},
        )
        assert other_unknown.status_code == 401
        other_account = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert other_account.status_code == 200

        for _ in range(3):
            known_account_failure = client.post(
                "/api/auth/login",
                json={"username": "root-admin", "password": "incorrect-password"},
            )
            assert known_account_failure.status_code == 401
        correct_credentials = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert correct_credentials.status_code == 429

    with make_client(app_settings) as client:
        still_limited = client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "incorrect-password"},
        )
        assert still_limited.status_code == 429

    with TestClient(
        create_app(settings_for(tmp_path / "origin.db")),
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
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
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ) as client:
        accepted = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        assert accepted.status_code == 200

    with TestClient(
        create_app(app_settings),
        headers={"Origin": "http://attacker.example"},
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
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


def test_global_auth_rate_limit_is_shared_across_login_flows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(
        tmp_path / "global-auth-limit.db",
        global_login_attempts=50,
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda *_: False)
    monkeypatch.setattr("app.routers.student_auth.verify_password", lambda *_: False)

    with make_client(app_settings) as client:
        for attempt in range(49):
            response = client.post(
                "/api/auth/login",
                json={
                    "username": f"unknown-{attempt}",
                    "password": "incorrect-password",
                },
            )
            assert response.status_code == 401

        student_response = client.post(
            "/api/student-auth/login",
            json={"identifier": "unknown", "password": "incorrect-password"},
        )
        assert student_response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            json={"username": "another-account", "password": "incorrect-password"},
        )

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_correct_password_does_not_reset_two_factor_throttling(
    tmp_path: Path,
) -> None:
    app_settings = settings_for(tmp_path / "two-factor-limit.db", login_attempts=3)
    with make_client(app_settings) as client:
        _, secret = complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
        challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        valid_code = pyotp.TOTP(secret).at(time() + 30)
        invalid_code = "000000" if valid_code != "000000" else "111111"
        for _ in range(3):
            failed = client.post(
                "/api/auth/2fa/verify",
                json={
                    "challenge_token": challenge["challenge_token"],
                    "code": invalid_code,
                },
            )
            assert failed.status_code == 401

        replacement_challenge = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        ).json()
        limited = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": replacement_challenge["challenge_token"],
                "code": valid_code,
            },
        )
        assert limited.status_code == 429


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
        assert previous_refresh

    rotated = settings_for(
        database,
        admin_password="a-different-strong-password",
    )
    with make_client(rotated) as client:
        assert client.get("/api/users/me", headers=access_headers).status_code == 401
        client.cookies.set(
            REFRESH_COOKIE,
            previous_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        previous_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )
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
        assert (
            client.post(
                "/api/auth/logout",
                headers=refresh_headers(client),
            ).status_code
            == 204
        )
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


def test_written_answers_have_an_application_level_size_limit() -> None:
    assert StudentQuizAnswer(written_answer="a" * 20000).written_answer
    with pytest.raises(ValidationError):
        StudentQuizAnswer(written_answer="a" * 20001)


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


def exam_environment(client: TestClient) -> dict[str, Any]:
    """Provision a teacher, a class with one student and a one-question quiz."""
    admin_headers = login_admin(client)
    assert (
        client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "edge.teacher",
                "display_name": "Edge Teacher",
                "password": "a-secure-edge-password",
            },
        ).status_code
        == 201
    )
    teacher_headers, _ = complete_first_login(
        client, "edge.teacher", "a-secure-edge-password"
    )
    student_class = client.post(
        "/api/classes",
        headers=teacher_headers,
        json={"name": "5e A", "grade_level": "5e"},
    ).json()
    account = client.post(
        "/api/students",
        headers=teacher_headers,
        json={"first_name": "Edge", "last_name": "Student"},
    ).json()
    assert (
        client.post(
            f"/api/classes/{student_class['id']}/accounts/{account['id']}",
            headers=teacher_headers,
        ).status_code
        == 200
    )
    student_login = client.post(
        "/api/student-auth/login",
        json={
            "identifier": account["identifier"],
            "password": account["generated_password"],
        },
    )
    assert student_login.status_code == 200
    student_headers = {
        "Authorization": f"Bearer {student_login.json()['access_token']}"
    }
    bank = client.post(
        "/api/question-banks",
        headers=teacher_headers,
        json={"grade_level": "5e", "chapter": "Edge cases"},
    ).json()
    question = client.post(
        f"/api/question-banks/{bank['id']}/questions",
        headers=teacher_headers,
        data={
            "payload": json.dumps(
                {
                    "prompt": "One plus one?",
                    "points": 2,
                    "difficulty": "easy",
                    "answer_mode": "single",
                    "answer_mode_disclosed": True,
                    "choices": [
                        {"label": "Two", "is_correct": True, "points": 2},
                        {"label": "Three", "is_correct": False, "points": -3},
                    ],
                }
            )
        },
    ).json()
    quiz = client.post(
        "/api/quizzes",
        headers=teacher_headers,
        json={
            "title": "Edge quiz",
            "question_bank_ids": [bank["id"]],
            "allow_previous_questions": False,
            "easy_question_count": 1,
            "medium_question_count": 0,
            "hard_question_count": 0,
        },
    ).json()
    return {
        "teacher_headers": teacher_headers,
        "student_headers": student_headers,
        "student_class": student_class,
        "account": account,
        "question": question,
        "quiz": quiz,
    }


def launch_and_join(
    client: TestClient,
    environment: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    launched = client.post(
        f"/api/quizzes/{environment['quiz']['id']}/launch",
        headers=environment["teacher_headers"],
        json={"class_id": environment["student_class"]["id"]},
    )
    assert launched.status_code == 201
    joined = client.post(
        "/api/quizzes/join",
        headers=environment["student_headers"],
        json={"join_code": launched.json()["join_code"]},
    )
    assert joined.status_code == 201
    participant_headers = {"X-Quiz-Token": joined.json()["participant_token"]}
    return launched.json(), participant_headers


def test_join_and_start_race_never_strands_a_participant(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "join-start-race.db")) as client:
        environment = exam_environment(client)
        launched = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/launch",
            headers=environment["teacher_headers"],
            json={"class_id": environment["student_class"]["id"]},
        ).json()
        barrier = Barrier(2)
        responses: dict[str, Any] = {}

        def join() -> int:
            barrier.wait()
            response = client.post(
                "/api/quizzes/join",
                headers=environment["student_headers"],
                json={"join_code": launched["join_code"]},
            )
            responses["join"] = response
            return response.status_code

        def start() -> int:
            barrier.wait()
            response = client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            )
            responses["start"] = response
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            join_status = pool.submit(join)
            start_status = pool.submit(start)
            assert join_status.result() == status.HTTP_201_CREATED
            assert start_status.result() in {
                status.HTTP_200_OK,
                status.HTTP_409_CONFLICT,
            }

        joined = responses["join"].json()
        state = client.get(
            f"/api/quizzes/student/sessions/{launched['join_code']}",
            headers={"X-Quiz-Token": joined["participant_token"]},
        )
        assert state.status_code == status.HTTP_200_OK
        if responses["start"].status_code == status.HTTP_200_OK:
            assert state.json()["status"] == "in_progress"
            assert state.json()["question"] is not None
        else:
            assert state.json()["status"] == "waiting"
            assert state.json()["question"] is None


def correct_choice_id(question: dict[str, Any]) -> int:
    return next(choice["id"] for choice in question["choices"] if choice["is_correct"])


def test_answer_points_are_summed_and_negative_points_follow_quiz_setting(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "answer-points.db")) as client:
        environment = exam_environment(client)
        wrong_choice_id = next(
            choice["id"]
            for choice in environment["question"]["choices"]
            if not choice["is_correct"]
        )

        def complete_with_wrong_answer() -> float:
            quiz_session, participant_headers = launch_and_join(client, environment)
            assert (
                client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/start",
                    headers=environment["teacher_headers"],
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
                    headers=participant_headers,
                    json={"selected_choice_ids": [wrong_choice_id]},
                ).status_code
                == 200
            )
            return client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=environment["teacher_headers"],
            ).json()["participants"][0]["score"]

        assert complete_with_wrong_answer() == 0
        updated = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": environment["quiz"]["title"],
                "question_bank_ids": [environment["question"]["question_bank_id"]],
                "allow_negative_points": True,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert updated.status_code == 200
        environment["quiz"] = updated.json()
        assert complete_with_wrong_answer() == -3


def test_student_login_verifies_password_for_unknown_accounts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifications: list[tuple[str, str]] = []

    def spy(password: str, encoded: str) -> bool:
        verifications.append((password, encoded))
        return False

    monkeypatch.setattr("app.routers.student_auth.verify_password", spy)
    with make_client(settings_for(tmp_path / "student-timing.db")) as client:
        response = client.post(
            "/api/student-auth/login",
            json={"identifier": "ghost.student", "password": "wrong-password"},
        )

    assert response.status_code == 401
    # The verification must run even for unknown identifiers so the response
    # time does not reveal whether the account exists.
    assert verifications == [("wrong-password", DUMMY_PASSWORD_HASH)]


def test_problem_report_rate_limit_is_instance_wide(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "problem-report-instance-limit.db",
        problem_report_attempts=2,
    )
    with make_client(settings) as client:
        for index in range(2):
            response = client.post(
                "/api/problem-reports",
                json={"message": f"Problème numéro {index}", "page_path": "/"},
                headers={"X-Forwarded-For": f"203.0.113.{index + 1}"},
            )
            assert response.status_code == 201

        # A fresh client address must not grant a fresh budget: the quota is
        # never keyed on an IP address.
        limited = client.post(
            "/api/problem-reports",
            json={"message": "Encore un problème", "page_path": "/"},
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        assert limited.status_code == 429


def test_makeup_join_is_rate_limited_per_student_account(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "makeup-join-limit.db",
        quiz_join_attempts=5,
        quiz_rate_window_seconds=60,
    )
    with make_client(settings) as client:
        environment = exam_environment(client)
        for _ in range(5):
            response = client.post(
                "/api/quizzes/makeup/join",
                headers=environment["student_headers"],
                json={"join_code": "ZZZZZZ"},
            )
            assert response.status_code == 403

        limited = client.post(
            "/api/quizzes/makeup/join",
            headers=environment["student_headers"],
            json={"join_code": "ZZZZZZ"},
        )
        assert limited.status_code == 429

        # Another student account keeps its own budget.
        other_account = client.post(
            "/api/students",
            headers=environment["teacher_headers"],
            json={"first_name": "Other", "last_name": "Student"},
        ).json()
        other_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": other_account["identifier"],
                "password": other_account["generated_password"],
            },
        )
        assert other_login.status_code == 200
        other_headers = {
            "Authorization": f"Bearer {other_login.json()['access_token']}"
        }
        other_attempt = client.post(
            "/api/quizzes/makeup/join",
            headers=other_headers,
            json={"join_code": "ZZZZZZ"},
        )
        assert other_attempt.status_code == 403


def test_makeup_finish_completes_paused_child_sessions(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "makeup-paused-finish.db")) as client:
        environment = exam_environment(client)
        quiz_session, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        answered = client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "finished"

        makeup = client.post(
            "/api/quizzes/makeup/sessions",
            headers=environment["teacher_headers"],
            json={
                "class_id": environment["student_class"]["id"],
                "quiz_ids": [environment["quiz"]["id"]],
            },
        ).json()
        assert (
            client.post(
                "/api/quizzes/makeup/join",
                headers=environment["student_headers"],
                json={"join_code": makeup["join_code"]},
            ).status_code
            == 200
        )
        selected = client.post(
            f"/api/quizzes/makeup/{makeup['join_code']}/select",
            headers=environment["student_headers"],
            json={"quiz_id": environment["quiz"]["id"]},
        )
        assert selected.status_code == 201
        child_headers = {"X-Quiz-Token": selected.json()["participant_token"]}
        child_state_url = (
            f"/api/quizzes/student/sessions/{selected.json()['join_code']}"
        )
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/pause",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        resumed = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/resume",
            headers=environment["teacher_headers"],
        )
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "in_progress"

        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/pause",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/resume",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        finished = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/finish",
            headers=environment["teacher_headers"],
        )
        assert finished.status_code == 200
        assert finished.json()["status"] == "finished"
        # A child paused when the makeup finishes must not stay stuck.
        child_state = client.get(child_state_url, headers=child_headers)
        assert child_state.status_code == 200
        assert child_state.json()["status"] == "finished"


def test_concurrent_answer_submissions_keep_a_single_answer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent-answers.db"
    with make_client(settings_for(database_path)) as client:
        environment = exam_environment(client)
        quiz_session, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        barrier = Barrier(4)
        answer_url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer"
        payload = {"selected_choice_ids": [correct_choice_id(environment["question"])]}

        def submit() -> int:
            barrier.wait()
            return client.post(
                answer_url,
                headers=participant_headers,
                json=payload,
            ).status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = [
                future.result() for future in [pool.submit(submit) for _ in range(4)]
            ]

        assert statuses == [200, 200, 200, 200]
        with sqlite3.connect(database_path) as connection:
            answer_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_answers WHERE session_id = ?",
                (quiz_session["id"],),
            ).fetchone()[0]
        assert answer_count == 1


def test_makeup_session_requires_quizzes_taken_by_the_class(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "makeup-eligibility.db")) as client:
        environment = exam_environment(client)
        makeup_payload = {
            "class_id": environment["student_class"]["id"],
            "quiz_ids": [environment["quiz"]["id"]],
        }
        # The class has not taken the quiz yet: the retake must be refused.
        refused = client.post(
            "/api/quizzes/makeup/sessions",
            headers=environment["teacher_headers"],
            json=makeup_payload,
        )
        assert refused.status_code == 422

        quiz_session, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        answered = client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "finished"

        # Once the class has completed the quiz, the retake is allowed.
        allowed = client.post(
            "/api/quizzes/makeup/sessions",
            headers=environment["teacher_headers"],
            json=makeup_payload,
        )
        assert allowed.status_code == 201
        assert allowed.json()["status"] == "waiting"

        barrier = Barrier(2)

        def select_makeup() -> int:
            barrier.wait()
            return client.post(
                f"/api/quizzes/makeup/{allowed.json()['join_code']}/select",
                headers=environment["student_headers"],
                json={"quiz_id": environment["quiz"]["id"]},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(
                future.result()
                for future in (pool.submit(select_makeup), pool.submit(select_makeup))
            )
        assert statuses == [201, 409]

        with sqlite3.connect(tmp_path / "makeup-eligibility.db") as connection:
            child_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_sessions WHERE makeup_session_id = ?",
                (allowed.json()["id"],),
            ).fetchone()[0]
        assert child_count == 1


def test_join_code_reservations_prevent_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(tmp_path / "join-code-reservations.db")
    app = create_app(app_settings)
    monkeypatch.setattr("app.routers.quizzes.randomizer.choice", lambda _: "A")

    with app.state.session_factory() as session:
        assert generate_join_code(session) == "AAAAAA"
        session.commit()

    with (
        app.state.session_factory() as session,
        pytest.raises(HTTPException) as error,
    ):
        generate_join_code(session)
    assert error.value.status_code == 503


def test_makeup_pause_resume_leaves_finished_child_alone(
    tmp_path: Path,
) -> None:
    """Pausing/resuming/cancelling a makeup must not reopen finished children."""
    with make_client(settings_for(tmp_path / "makeup-finished-child.db")) as client:
        environment = exam_environment(client)

        def run_exam() -> dict[str, str]:
            quiz_session, participant_headers = launch_and_join(client, environment)
            assert (
                client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/start",
                    headers=environment["teacher_headers"],
                ).status_code
                == 200
            )
            answered = client.post(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
                headers=participant_headers,
                json={
                    "selected_choice_ids": [correct_choice_id(environment["question"])]
                },
            )
            assert answered.status_code == 200
            assert answered.json()["status"] == "finished"
            return {"participant_headers": participant_headers}

        run_exam()
        makeup = client.post(
            "/api/quizzes/makeup/sessions",
            headers=environment["teacher_headers"],
            json={
                "class_id": environment["student_class"]["id"],
                "quiz_ids": [environment["quiz"]["id"]],
            },
        ).json()
        assert (
            client.post(
                "/api/quizzes/makeup/join",
                headers=environment["student_headers"],
                json={"join_code": makeup["join_code"]},
            ).status_code
            == 200
        )
        selected = client.post(
            f"/api/quizzes/makeup/{makeup['join_code']}/select",
            headers=environment["student_headers"],
            json={"quiz_id": environment["quiz"]["id"]},
        )
        assert selected.status_code == 201
        child_headers = {"X-Quiz-Token": selected.json()["participant_token"]}
        child_url = f"/api/quizzes/student/sessions/{selected.json()['join_code']}"
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        # The student completes their retake and the child session finishes.
        answered = client.post(
            f"/api/quizzes/student/sessions/{selected.json()['join_code']}/answer",
            headers=child_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "finished"

        # Teacher pauses then resumes the whole makeup: the finished child must
        # remain finished instead of being reopened.
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/pause",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        assert (
            client.get(child_url, headers=child_headers).json()["status"] == "finished"
        )
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/resume",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        assert (
            client.get(child_url, headers=child_headers).json()["status"] == "finished"
        )
