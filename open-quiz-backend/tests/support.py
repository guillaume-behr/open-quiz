"""Shared helpers for the backend test suite."""

import json
import os
from base64 import b64decode
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import psycopg
import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, event

import main
from app.config import Settings
from app.database import postgres_url
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
)
from app.routers.auth import REFRESH_COOKIE, REFRESH_PROOF_HEADER
from app.security import refresh_request_proof
from main import create_app

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


# install-dev.sh creates the role and database of this default; keep both in
# step when changing it.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://open_quiz_test:open-quiz-test-password@127.0.0.1:5432/open_quiz_test",
)


PREPARED_TEST_SCHEMAS: set[str] = set()


STUDENT_EXAM_FORBIDDEN_ANSWER_FIELDS = {
    "correct_choice_ids",
    "correction_mode",
    "expected_answer",
    "expected_answers",
    "is_correct",
    "max_score",
    "points",
    "score",
}


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in nested_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in nested_keys(child)}
    return set()


def assert_student_exam_payload_hides_answers(payload: Any) -> None:
    assert nested_keys(payload).isdisjoint(STUDENT_EXAM_FORBIDDEN_ANSWER_FIELDS)


def database_url_for(database: Path) -> str:
    schema = f"test_{sha256(str(database).encode()).hexdigest()[:24]}"
    base_url = postgres_url(TEST_DATABASE_URL)
    if schema not in PREPARED_TEST_SCHEMAS:
        engine = create_engine(base_url)
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine.dispose()
        PREPARED_TEST_SCHEMAS.add(schema)
    return base_url.update_query_dict(
        {"options": f"-csearch_path={schema}"}
    ).render_as_string(hide_password=False)


@contextmanager
def database_connection(database: Path):
    url = postgres_url(database_url_for(database)).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as connection:
        yield connection


def settings_for(database: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": database_url_for(database),
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
    assert invalid.json()["detail"]["code"] == "AUTH_2FA_CODE_INVALID"

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


def hand_in_quiz(
    client: TestClient,
    join_code: str,
    participant_headers: dict[str, str],
) -> dict[str, Any]:
    """Confirm the reviewed answers, which is what ends an exam for a student.

    Quizzes offer the review step by default, so answering the last question
    is no longer what hands the paper in.
    """
    submitted = client.post(
        f"/api/quizzes/student/sessions/{join_code}/submit",
        headers=participant_headers,
    )
    assert submitted.status_code == 200
    return submitted.json()


def correct_choice_id(question: dict[str, Any]) -> int:
    return next(choice["id"] for choice in question["choices"] if choice["is_correct"])


def wrong_choice_id(question: dict[str, Any]) -> int:
    return next(
        choice["id"] for choice in question["choices"] if not choice["is_correct"]
    )


@contextmanager
def concurrent_writes(
    client: TestClient,
    *steps: tuple[str, Callable[[Connection], object]],
) -> Iterator[list[str]]:
    """Commit each step from another connection just before a matching statement.

    Every step fires once, in order, right before the request's next SQL
    statement starting with its prefix, which simulates a concurrent request
    winning a race. The yielded list records the prefixes that fired.
    """
    engine = client.app.state.session_factory.kw["bind"]
    pending = list(steps)
    fired: list[str] = []

    def before_cursor_execute(connection, cursor, statement, *_: object) -> None:
        if not pending or connection.info.get("concurrent_writer"):
            return
        prefix, action = pending[0]
        if not " ".join(statement.split()).upper().startswith(prefix.upper()):
            return
        pending.pop(0)
        with engine.begin() as other:
            other.info["concurrent_writer"] = True
            try:
                action(other)
            finally:
                other.info.pop("concurrent_writer", None)
        fired.append(prefix)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield fired
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def create_professor(
    client: TestClient,
    admin_headers: dict[str, str],
    username: str = "edge.teacher",
    password: str = "a-secure-edge-password",
) -> tuple[dict[str, Any], dict[str, str]]:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": username, "display_name": username, "password": password},
    )
    assert created.status_code == 201
    headers, _ = complete_first_login(client, username, password)
    return created.json(), headers


def seeded_exam_session(
    session: Any,
    owner_id: int,
    *,
    join_code: str,
    status_value: str,
    created_at: datetime,
    with_answer: bool,
) -> int:
    """Build a session an owner never came back to close."""
    bank = QuestionBank(
        owner_id=owner_id,
        grade_level="6e",
        chapter=f"Abandoned {join_code}",
    )
    session.add(bank)
    session.flush()
    question = Question(
        question_bank_id=bank.id,
        prompt="2 + 2 ?",
        difficulty="easy",
        answer_mode="single",
        correction_mode="automatic",
    )
    session.add(question)
    session.flush()
    choice = QuestionChoice(
        question_id=question.id,
        label="4",
        is_correct=True,
        points=2.0,
        position=0,
    )
    session.add(choice)
    quiz = Quiz(owner_id=owner_id, title=f"Quiz {join_code}", question_count=1)
    session.add(quiz)
    session.flush()
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        class_name="Abandoned class",
        join_code=join_code,
        status=status_value,
        created_at=created_at,
        started_at=created_at,
    )
    session.add(quiz_session)
    session.flush()
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_identifier=f"pupil.{join_code.lower()}",
        student_display_name="Abandoned Pupil",
        current_position=0,
    )
    session.add(participant)
    session.flush()
    if with_answer:
        session.add(
            QuizAnswer(
                session_id=quiz_session.id,
                participant_id=participant.id,
                question_id=question.id,
                answer_data=json.dumps({"selected_choice_ids": [choice.id]}),
            )
        )
    session.flush()
    return quiz_session.id


def expire_due_sessions(client: TestClient) -> int:
    """Run one tick of the expiry loop, which tests drive explicitly."""
    return main.expire_due_sessions(
        client.app.state.session_factory, client.app.state.live_quiz_hub
    )
