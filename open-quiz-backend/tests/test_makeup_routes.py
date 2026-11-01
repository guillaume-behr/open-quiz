"""Make-up session paths outside the main flows."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text, update

from app.models import MakeupSession, QuizAnswer, QuizParticipant, QuizSession

from support import (
    concurrent_writes,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


def add_student(client, environment: dict[str, Any], first_name: str) -> dict:
    headers = environment["teacher_headers"]
    account = client.post(
        "/api/students",
        headers=headers,
        json={"first_name": first_name, "last_name": "Pupil"},
    ).json()
    login = client.post(
        "/api/student-auth/login",
        json={
            "identifier": account["identifier"],
            "password": account["generated_password"],
        },
    )
    return {
        **account,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


@pytest.fixture
def environment(tmp_path: Path):
    with make_client(settings_for(tmp_path / "makeup-routes")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        launched, participant_headers = launch_and_join(client, environment)
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        )
        client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        hand_in_quiz(client, launched["join_code"], participant_headers)
        yield environment


def create_makeup(client, environment: dict[str, Any]) -> dict[str, Any]:
    created = client.post(
        "/api/quizzes/makeup/sessions",
        headers=environment["teacher_headers"],
        json={
            "class_id": environment["student_class"]["id"],
            "quiz_ids": [environment["quiz"]["id"]],
        },
    )
    assert created.status_code == 201
    return created.json()


def select_quiz(client, environment, makeup, student_headers) -> Any:
    return client.post(
        f"/api/quizzes/makeup/{makeup['join_code']}/select",
        headers=student_headers,
        json={"quiz_id": environment["quiz"]["id"]},
    )


def test_makeup_options_and_creation_are_validated(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]

    assert (
        client.get(
            "/api/quizzes/makeup/quiz-options",
            headers=headers,
            params={"class_id": 999999},
        ).status_code
        == 404
    )
    options = client.get(
        "/api/quizzes/makeup/quiz-options",
        headers=headers,
        params={"class_id": environment["student_class"]["id"]},
    )
    assert [quiz["id"] for quiz in options.json()] == [environment["quiz"]["id"]]

    invalid = client.post(
        "/api/quizzes/makeup/sessions",
        headers=headers,
        json={"class_id": environment["student_class"]["id"], "quiz_ids": [999999]},
    )
    assert invalid.status_code == 422


def test_makeup_control_rejects_unknown_actions_and_states(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup = create_makeup(client, environment)
    url = f"/api/quizzes/makeup/sessions/{makeup['id']}"

    assert (
        client.post("/api/quizzes/makeup/sessions/999999/start", headers=headers)
    ).status_code == 404
    assert client.post(f"{url}/explode", headers=headers).status_code == 404
    assert client.post(f"{url}/pause", headers=headers).status_code == 409
    no_children = client.post(f"{url}/start", headers=headers)
    assert no_children.status_code == 409
    assert no_children.json()["detail"]["code"] == "MAKEUP_NO_SELECTION"
    assert "Au moins un élève" in no_children.json()["detail"]["message"]

    with concurrent_writes(
        client,
        (
            "UPDATE makeup_sessions SET status",
            lambda connection: connection.execute(
                update(MakeupSession)
                .where(MakeupSession.id == makeup["id"])
                .values(status="in_progress")
            ),
        ),
    ) as fired:
        raced = client.post(f"{url}/start", headers=headers)
    assert fired
    assert raced.status_code == 409


def test_cancelling_a_makeup_removes_it_unless_answers_exist(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_headers = environment["student_headers"]

    makeup = create_makeup(client, environment)
    assert select_quiz(client, environment, makeup, student_headers).status_code == 201
    with client.app.state.session_factory() as session:
        child = session.scalar(
            select(QuizSession).where(QuizSession.makeup_session_id == makeup["id"])
        )
        participant_id = session.scalar(
            select(QuizParticipant.id).where(QuizParticipant.session_id == child.id)
        )
        answer = QuizAnswer(
            session_id=child.id,
            participant_id=participant_id,
            question_id=environment["question"]["id"],
            answer_data="{}",
        )
        session.add(answer)
        session.commit()
        answer_id = answer.id
    url = f"/api/quizzes/makeup/sessions/{makeup['id']}"
    assert client.post(f"{url}/cancel", headers=headers).status_code == 409

    with client.app.state.session_factory() as session:
        session.delete(session.get(QuizAnswer, answer_id))
        session.commit()
    cancelled = client.post(f"{url}/cancel", headers=headers)
    assert cancelled.status_code == 204
    with client.app.state.session_factory() as session:
        assert session.get(MakeupSession, makeup["id"]) is None
        assert session.get(QuizSession, child.id) is None


def test_listing_removes_legacy_cancelled_makeups(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup = create_makeup(client, environment)
    with client.app.state.session_factory() as session:
        session.execute(
            update(MakeupSession)
            .where(MakeupSession.id == makeup["id"])
            .values(status="cancelled")
        )
        session.commit()
    assert client.get("/api/quizzes/makeup/sessions", headers=headers).json() == []
    with client.app.state.session_factory() as session:
        assert session.get(MakeupSession, makeup["id"]) is None


def test_makeup_start_leaves_already_running_children_alone(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup = create_makeup(client, environment)
    assert (
        select_quiz(client, environment, makeup, environment["student_headers"])
    ).status_code == 201
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.makeup_session_id == makeup["id"])
            .values(status="in_progress", started_at=started_at)
        )
        session.commit()
    started = client.post(
        f"/api/quizzes/makeup/sessions/{makeup['id']}/start", headers=headers
    )
    assert started.status_code == 200
    with client.app.state.session_factory() as session:
        child = session.scalar(
            select(QuizSession).where(QuizSession.makeup_session_id == makeup["id"])
        )
        assert child.started_at == started_at


def test_makeup_joining_and_selection_edge_cases(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_class = environment["student_class"]
    classmate = add_student(client, environment, "Classmate")
    client.post(
        f"/api/classes/{student_class['id']}/accounts/{classmate['id']}",
        headers=headers,
    )
    outsider = add_student(client, environment, "Outsider")
    makeup = create_makeup(client, environment)

    refused = client.post(
        "/api/quizzes/makeup/join",
        headers=outsider["headers"],
        json={"join_code": makeup["join_code"]},
    )
    assert refused.status_code == 403
    unknown = client.post(
        "/api/quizzes/makeup/ZZZZZZ/select",
        headers=outsider["headers"],
        json={"quiz_id": environment["quiz"]["id"]},
    )
    assert unknown.status_code == 409

    first = select_quiz(client, environment, makeup, environment["student_headers"])
    assert first.status_code == 201
    second = select_quiz(client, environment, makeup, classmate["headers"])
    assert second.status_code == 201

    late = add_student(client, environment, "Late")
    client.post(
        f"/api/classes/{student_class['id']}/accounts/{late['id']}", headers=headers
    )
    with concurrent_writes(
        client,
        (
            "UPDATE makeup_sessions SET status",
            lambda connection: connection.execute(
                update(MakeupSession)
                .where(MakeupSession.id == makeup["id"])
                .values(status="in_progress")
            ),
        ),
    ) as fired:
        raced = select_quiz(client, environment, makeup, late["headers"])
    assert fired
    assert raced.status_code == 409


def test_a_concurrent_selection_by_the_same_student_is_refused(environment) -> None:
    client = environment["client"]
    makeup = create_makeup(client, environment)
    account_id = environment["account"]["id"]

    def claim(connection) -> None:
        connection.execute(
            text(
                "INSERT INTO makeup_session_selections (session_id, student_id) "
                "SELECT :session_id, id FROM students WHERE account_id = :account_id"
            ),
            {"session_id": makeup["id"], "account_id": account_id},
        )

    with concurrent_writes(
        client, ("INSERT INTO makeup_session_selections", claim)
    ) as fired:
        refused = select_quiz(
            client, environment, makeup, environment["student_headers"]
        )
    assert fired
    assert refused.status_code == 409
