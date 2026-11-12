"""A teacher never reaches another teacher's records (IDOR).

Teacher A owns a full set of records; teacher B, signed in, tries every route
that names one of them by id. Each must answer 404, as for an id that does
not exist, and change nothing. A meta-test lists every route that takes such
an id, so a new one cannot be added without its row here.
"""

import json
from base64 import b64encode
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import Base
from app.models import GradeLevel, QuizAnswer, QuizParticipant

from support import (
    VALID_PNG,
    choice_answer,
    correct_choice_id,
    create_professor,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)

QUESTION = {
    "prompt": "Pick",
    "points": 1,
    "difficulty": "easy",
    "answer_mode": "single",
    "answer_mode_disclosed": True,
    "choices": [
        {
            "label": "Pictured",
            "is_correct": True,
            "points": 1,
            "image": {
                "content_type": "image/png",
                "data_base64": b64encode(VALID_PNG).decode(),
            },
        },
        {"label": "Plain", "is_correct": False, "points": 0},
    ],
}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    path = tmp_path_factory.mktemp("ownership") / "db"
    with make_client(settings_for(path)) as client:
        a = exam_environment(client)
        headers_a = a["teacher_headers"]
        bank_id = a["question"]["question_bank_id"]
        launched, participant_headers = launch_and_join(client, a)
        client.post(f"/api/quizzes/sessions/{launched['id']}/start", headers=headers_a)
        client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
            headers=participant_headers,
            json=choice_answer(
                client, participant_headers, correct_choice_id(a["question"])
            ),
        )
        hand_in_quiz(client, launched["join_code"], participant_headers)
        pictured = client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=headers_a,
            data={"payload": json.dumps(QUESTION)},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        ).json()
        makeup = client.post(
            "/api/quizzes/makeup/sessions",
            headers=headers_a,
            json={"class_id": a["student_class"]["id"], "quiz_ids": [a["quiz"]["id"]]},
        ).json()
        with client.app.state.session_factory() as session:
            participant_id = session.scalar(
                select(QuizParticipant.id).where(
                    QuizParticipant.session_id == launched["id"]
                )
            )
            answer_id = session.scalar(
                select(QuizAnswer.id).where(QuizAnswer.session_id == launched["id"])
            )
            grade_level_id = session.scalar(
                select(GradeLevel.id).where(GradeLevel.name == "5e")
            )

        _, headers_b = create_professor(
            client, a["admin_headers"], username="other.teacher"
        )
        class_b = client.post(
            "/api/classes", headers=headers_b, json={"name": "B", "grade_level": "5e"}
        ).json()
        account_b = client.post(
            "/api/students",
            headers=headers_b,
            json={"first_name": "Bea", "last_name": "Other"},
        ).json()
        client.post(
            f"/api/classes/{class_b['id']}/accounts/{account_b['id']}",
            headers=headers_b,
        )
        student_b = client.post(
            "/api/student-auth/login",
            json={
                "identifier": account_b["identifier"],
                "password": account_b["generated_password"],
            },
        ).json()
        yield {
            "client": client,
            "headers_b": headers_b,
            "student_b": {"Authorization": f"Bearer {student_b['access_token']}"},
            "ids": {
                "class_id": a["student_class"]["id"],
                "account_id": a["account"]["id"],
                "question_bank_id": bank_id,
                "question_id": pictured["id"],
                "choice_id": pictured["choices"][0]["id"],
                "quiz_id": a["quiz"]["id"],
                "session_id": launched["id"],
                "participant_id": participant_id,
                "answer_id": answer_id,
                "makeup_id": makeup["id"],
                "grade_level_id": grade_level_id,
                "own_class_id": class_b["id"],
                "own_account_id": account_b["id"],
            },
        }


def question_form(_: dict[str, int]) -> dict[str, Any]:
    return {"data": {"payload": json.dumps(QUESTION)}}


def quiz_body(ids: dict[str, int]) -> dict[str, Any]:
    return {
        "json": {
            "title": "Borrowed",
            "question_bank_ids": [ids["question_bank_id"]],
            "easy_question_count": 1,
            "medium_question_count": 0,
            "hard_question_count": 0,
        }
    }


def no_body(_: dict[str, int]) -> dict[str, Any]:
    return {}


# (method, route as declared, concrete path, request body, who asks)
# "teacher" is teacher B; "student" is a student of B's class.
FOREIGN_REQUESTS: list[tuple[str, str, str, Any, str]] = [
    (
        "GET",
        "/api/question-banks/{question_bank_id}/questions",
        "/api/question-banks/{question_bank_id}/questions",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/question-banks/{question_bank_id}/questions",
        "/api/question-banks/{question_bank_id}/questions",
        question_form,
        "teacher",
    ),
    (
        "POST",
        "/api/question-banks/{question_bank_id}/update",
        "/api/question-banks/{question_bank_id}/update",
        lambda ids: {"json": {"grade_level": "5e", "chapter": "Stolen"}},
        "teacher",
    ),
    (
        "DELETE",
        "/api/question-banks/{question_bank_id}",
        "/api/question-banks/{question_bank_id}",
        no_body,
        "teacher",
    ),
    (
        "GET",
        "/api/question-banks/{question_bank_id}/export",
        "/api/question-banks/{question_bank_id}/export",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/question-banks/questions/{question_id}/update",
        "/api/question-banks/questions/{question_id}/update",
        question_form,
        "teacher",
    ),
    (
        "DELETE",
        "/api/question-banks/questions/{question_id}",
        "/api/question-banks/questions/{question_id}",
        no_body,
        "teacher",
    ),
    (
        "GET",
        "/api/question-banks/questions/{question_id}/image",
        "/api/question-banks/questions/{question_id}/image",
        no_body,
        "teacher",
    ),
    (
        "GET",
        "/api/question-banks/choices/{choice_id}/image",
        "/api/question-banks/choices/{choice_id}/image",
        no_body,
        "teacher",
    ),
    (
        "DELETE",
        "/api/classes/{class_id}",
        "/api/classes/{class_id}",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/classes/{class_id}/update",
        "/api/classes/{class_id}/update",
        lambda ids: {"json": {"name": "Stolen", "grade_level": "5e"}},
        "teacher",
    ),
    (
        "POST",
        "/api/classes/{class_id}/accounts/{account_id}",
        "/api/classes/{class_id}/accounts/{own_account_id}",
        no_body,
        "teacher",
    ),
    (
        "DELETE",
        "/api/classes/{class_id}/accounts/{account_id}",
        "/api/classes/{class_id}/accounts/{account_id}",
        no_body,
        "teacher",
    ),
    (
        "DELETE",
        "/api/classes/grade-levels/{grade_level_id}",
        "/api/classes/grade-levels/{grade_level_id}",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/students/{account_id}/update",
        "/api/students/{account_id}/update",
        lambda ids: {
            "json": {
                "identifier": "taken.over",
                "display_name": "X",
                "is_active": False,
            }
        },
        "teacher",
    ),
    (
        "DELETE",
        "/api/students/{account_id}",
        "/api/students/{account_id}",
        no_body,
        "teacher",
    ),
    ("DELETE", "/api/quizzes/{quiz_id}", "/api/quizzes/{quiz_id}", no_body, "teacher"),
    (
        "GET",
        "/api/quizzes/{quiz_id}/preview",
        "/api/quizzes/{quiz_id}/preview",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/{quiz_id}/update",
        "/api/quizzes/{quiz_id}/update",
        quiz_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/{quiz_id}/launch",
        "/api/quizzes/{quiz_id}/launch",
        lambda ids: {"json": {"class_id": ids["own_class_id"]}},
        "teacher",
    ),
    (
        "GET",
        "/api/quizzes/sessions/{session_id}",
        "/api/quizzes/sessions/{session_id}",
        no_body,
        "teacher",
    ),
    (
        "DELETE",
        "/api/quizzes/sessions/{session_id}",
        "/api/quizzes/sessions/{session_id}",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/start",
        "/api/quizzes/sessions/{session_id}/start",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/pause",
        "/api/quizzes/sessions/{session_id}/pause",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/resume",
        "/api/quizzes/sessions/{session_id}/resume",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/cancel",
        "/api/quizzes/sessions/{session_id}/cancel",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/publish-grades",
        "/api/quizzes/sessions/{session_id}/publish-grades",
        no_body,
        "teacher",
    ),
    (
        "GET",
        "/api/quizzes/sessions/{session_id}/participants/{participant_id}/answers",
        "/api/quizzes/sessions/{session_id}/participants/{participant_id}/answers",
        no_body,
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/sessions/{session_id}/answers/{answer_id}/grade",
        "/api/quizzes/sessions/{session_id}/answers/{answer_id}/grade",
        lambda ids: {"json": {"score": 0}},
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/makeup/sessions/{session_id}/{action}",
        "/api/quizzes/makeup/sessions/{makeup_id}/cancel",
        no_body,
        "teacher",
    ),
    (
        "GET",
        "/api/quizzes/training/classes/{class_id}/question-banks",
        "/api/quizzes/training/classes/{class_id}/question-banks",
        no_body,
        "teacher",
    ),
    (
        "PUT",
        "/api/quizzes/training/classes/{class_id}/question-banks",
        "/api/quizzes/training/classes/{class_id}/question-banks",
        lambda ids: {"json": {"question_banks": []}},
        "teacher",
    ),
    (
        "POST",
        "/api/quizzes/training/{question_bank_id}/start",
        "/api/quizzes/training/{question_bank_id}/start",
        no_body,
        "student",
    ),
]

# Routes that only ever return the requester's own records: asked about A's,
# they answer with nothing rather than 404.
SCOPED_TO_REQUESTER: list[tuple[str, str, str, str]] = [
    # A student's own finished attempts in a bank: none in A's bank.
    (
        "GET",
        "/api/quizzes/training/{question_bank_id}/history",
        "/api/quizzes/training/{question_bank_id}/history",
        "student",
    ),
]

# Requests on B's own records that name one of A's: refused as invalid input.
FOREIGN_REFERENCES: list[tuple[str, str, Any]] = [
    ("POST", "/api/quizzes", quiz_body),
    (
        "PUT",
        "/api/quizzes/training/classes/{own_class_id}/question-banks",
        lambda ids: {
            "json": {
                "question_banks": [
                    {"question_bank_id": ids["question_bank_id"], "question_count": 1}
                ]
            }
        },
    ),
    ("POST", "/api/classes/{own_class_id}/accounts/{account_id}", no_body),
]


def fingerprint(client: TestClient) -> dict[str, list[Any]]:
    """Every row of every table, to prove a refused request changed nothing."""
    with client.app.state.session_factory() as session:
        return {
            name: sorted(
                str(row)
                for row in session.execute(text(f"SELECT * FROM {name}"))  # noqa: S608 - table names from the metadata
            )
            for name in Base.metadata.tables
            if name
            not in {"login_rate_limits", "refresh_sessions", "refresh_session_families"}
        }


def send(world: dict[str, Any], method: str, path: str, body: Any, who: str) -> Any:
    headers = world["headers_b"] if who == "teacher" else world["student_b"]
    return world["client"].request(
        method, path.format(**world["ids"]), headers=headers, **body(world["ids"])
    )


@pytest.mark.parametrize(
    ("method", "path", "body", "who"),
    [(method, path, body, who) for method, _, path, body, who in FOREIGN_REQUESTS],
    ids=[f"{method} {route}" for method, route, *_ in FOREIGN_REQUESTS],
)
def test_another_teachers_record_is_not_found(
    world: dict[str, Any], method: str, path: str, body: Any, who: str
) -> None:
    before = fingerprint(world["client"])
    response = send(world, method, path, body, who)
    assert response.status_code == 404, response.text
    assert fingerprint(world["client"]) == before


@pytest.mark.parametrize(
    ("method", "path", "body"),
    FOREIGN_REFERENCES,
    ids=[f"{method} {path}" for method, path, _ in FOREIGN_REFERENCES],
)
def test_another_teachers_record_cannot_be_referenced(
    world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    before = fingerprint(world["client"])
    response = send(world, method, path, body, "teacher")
    assert 400 <= response.status_code < 500, response.text
    assert fingerprint(world["client"]) == before


@pytest.mark.parametrize(
    ("method", "path", "who"),
    [(method, path, who) for method, _, path, who in SCOPED_TO_REQUESTER],
    ids=[f"{method} {route}" for method, route, *_ in SCOPED_TO_REQUESTER],
)
def test_another_teachers_record_yields_nothing(
    world: dict[str, Any], method: str, path: str, who: str
) -> None:
    before = fingerprint(world["client"])
    response = send(world, method, path, no_body, who)
    assert response.status_code == 200, response.text
    assert response.json() == []
    assert fingerprint(world["client"]) == before


def test_lists_show_only_the_teachers_own_records(world: dict[str, Any]) -> None:
    client, headers = world["client"], world["headers_b"]
    ids = world["ids"]
    for path, own in (
        ("/api/question-banks", set()),
        ("/api/quizzes", set()),
        ("/api/classes", {ids["own_class_id"]}),
        ("/api/students", {ids["own_account_id"]}),
        ("/api/quizzes/sessions/active", set()),
        ("/api/quizzes/sessions/results", set()),
        ("/api/quizzes/makeup/sessions", set()),
    ):
        listed = client.get(path, headers=headers)
        assert listed.status_code == 200, path
        assert {item["id"] for item in listed.json()} == own, path


# Routes that take an id but are not teacher records: an administrator's,
# or a quiz participant's, which a join code and a participant token guard
# (tests/test_student_quiz_routes.py, tests/test_participant_resume.py).
NOT_TEACHER_RECORDS = ("/api/admin/", "/api/problem-reports/", "{join_code}")


def test_every_route_naming_a_record_has_a_foreign_request(
    world: dict[str, Any],
) -> None:
    """Adding a route that takes an id means adding its row above."""
    covered = {(method, route) for method, route, *_ in FOREIGN_REQUESTS} | {
        (method, route) for method, route, *_ in SCOPED_TO_REQUESTER
    }
    routes = {
        (method.upper(), path)
        for path, operations in world["client"].app.openapi()["paths"].items()
        if "{" in path and not any(part in path for part in NOT_TEACHER_RECORDS)
        for method in operations
    }
    assert routes - covered == set()
