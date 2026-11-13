"""Make-up sessions: creation, joining, control and their child sessions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text, update

from app.enums import SessionStatus
from app.models import (
    MakeupSession,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    User,
)
from app.routers import makeup as makeup_routes
from app.teacher_session_responses import active_makeup_session_responses

from support import (
    choice_answer,
    concurrent_writes,
    correct_choice_id,
    database_connection,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    row_is_locked,
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
            json=choice_answer(
                client, participant_headers, correct_choice_id(environment["question"])
            ),
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
    assert client.post(f"{url}/explode", headers=headers).status_code == 422
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


def test_cancelling_a_makeup_holds_its_lock_until_the_delete(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent start, and then an answer, cannot slip in between the
    checks and the delete."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup = create_makeup(client, environment)
    locked_at_delete: list[bool] = []
    delete_records = makeup_routes.delete_makeup_session_records

    def probe_then_delete(makeup_id: int, session: Any) -> None:
        locked_at_delete.append(row_is_locked(client, MakeupSession, makeup["id"]))
        delete_records(makeup_id, session)

    monkeypatch.setattr(
        makeup_routes, "delete_makeup_session_records", probe_then_delete
    )

    cancelled = client.post(
        f"/api/quizzes/makeup/sessions/{makeup['id']}/cancel", headers=headers
    )

    assert cancelled.status_code == 204
    assert locked_at_delete == [True]


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
            json=choice_answer(
                client, participant_headers, correct_choice_id(environment["question"])
            ),
        )
        assert answered.status_code == 200
        handed_in = hand_in_quiz(client, quiz_session["join_code"], participant_headers)
        assert handed_in["status"] == "finished"

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


@pytest.mark.parametrize("action", ["pause", "resume"])
def test_makeup_pause_and_resume_never_reopen_a_concurrently_finished_child(
    environment, action: str
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup = create_makeup(client, environment)
    url = f"/api/quizzes/makeup/sessions/{makeup['id']}"
    assert (
        client.post(
            "/api/quizzes/makeup/join",
            headers=environment["student_headers"],
            json={"join_code": makeup["join_code"]},
        ).status_code
        == 200
    )
    selected = select_quiz(client, environment, makeup, environment["student_headers"])
    assert selected.status_code == 201
    child_join_code = selected.json()["join_code"]
    assert client.post(f"{url}/start", headers=headers).status_code == 200
    if action == "resume":
        assert client.post(f"{url}/pause", headers=headers).status_code == 200

    with concurrent_writes(
        client,
        (
            # The child finishes (its last participant handed in, or its time
            # ran out) after the makeup request read it.
            "UPDATE quiz_sessions",
            lambda connection: connection.execute(
                update(QuizSession)
                .where(QuizSession.join_code == child_join_code)
                .values(status="finished")
            ),
        ),
    ) as fired:
        controlled = client.post(f"{url}/{action}", headers=headers)
    assert fired
    assert controlled.status_code == 200
    with client.app.state.session_factory() as session:
        child = session.scalar(
            select(QuizSession).where(QuizSession.join_code == child_join_code)
        )
        assert child is not None
        assert child.status == "finished"


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
            json=choice_answer(
                client, participant_headers, correct_choice_id(environment["question"])
            ),
        )
        assert answered.status_code == 200
        handed_in = hand_in_quiz(client, quiz_session["join_code"], participant_headers)
        assert handed_in["status"] == "finished"

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

        with database_connection(tmp_path / "makeup-eligibility.db") as connection:
            child_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_sessions WHERE makeup_session_id = %s",
                (allowed.json()["id"],),
            ).fetchone()[0]
        assert child_count == 1


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
                json=choice_answer(
                    client,
                    participant_headers,
                    correct_choice_id(environment["question"]),
                ),
            )
            assert answered.status_code == 200
            handed_in = hand_in_quiz(
                client, quiz_session["join_code"], participant_headers
            )
            assert handed_in["status"] == "finished"
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
            json=choice_answer(
                client, child_headers, correct_choice_id(environment["question"])
            ),
        )
        assert answered.status_code == 200
        handed_in = hand_in_quiz(client, selected.json()["join_code"], child_headers)
        assert handed_in["status"] == "finished"

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


def test_makeup_session_allows_absent_student_to_take_quiz(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "makeup-absent-student.db")) as client:
        environment = exam_environment(client)
        absent_account = client.post(
            "/api/students",
            headers=environment["teacher_headers"],
            json={"first_name": "Absent", "last_name": "Student"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{environment['student_class']['id']}/accounts/{absent_account['id']}",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        absent_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": absent_account["identifier"],
                "password": absent_account["generated_password"],
            },
        )
        assert absent_login.status_code == 200
        absent_headers = {
            "Authorization": f"Bearer {absent_login.json()['access_token']}"
        }

        # Launch the quiz for the class
        launched = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/launch",
            headers=environment["teacher_headers"],
            json={"class_id": environment["student_class"]["id"]},
        )
        assert launched.status_code == 201
        quiz_session = launched.json()

        # Present student joins and finishes the quiz; absent student does NOT join
        joined = client.post(
            "/api/quizzes/join",
            headers=environment["student_headers"],
            json={"join_code": quiz_session["join_code"]},
        )
        assert joined.status_code == 201
        present_token = joined.json()["participant_token"]

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
                headers={"X-Quiz-Token": present_token},
                json=choice_answer(
                    client,
                    {"X-Quiz-Token": present_token},
                    correct_choice_id(environment["question"]),
                ),
            ).status_code
            == 200
        )
        handed_in = hand_in_quiz(
            client, quiz_session["join_code"], {"X-Quiz-Token": present_token}
        )
        assert handed_in["status"] == "finished"

        # Teacher creates a makeup session for the class with the completed quiz
        makeup = client.post(
            "/api/quizzes/makeup/sessions",
            headers=environment["teacher_headers"],
            json={
                "class_id": environment["student_class"]["id"],
                "quiz_ids": [environment["quiz"]["id"]],
            },
        )
        assert makeup.status_code == 201
        makeup_data = makeup.json()

        # The absent student can join the makeup session and sees the quiz
        makeup_join = client.post(
            "/api/quizzes/makeup/join",
            headers=absent_headers,
            json={"join_code": makeup_data["join_code"]},
        )
        assert makeup_join.status_code == 200
        assert [q["id"] for q in makeup_join.json()["quizzes"]] == [
            environment["quiz"]["id"]
        ]

        # The absent student can select the quiz
        makeup_selected = client.post(
            f"/api/quizzes/makeup/{makeup_data['join_code']}/select",
            headers=absent_headers,
            json={"quiz_id": environment["quiz"]["id"]},
        )
        assert makeup_selected.status_code == 201
        assert makeup_selected.json()["status"] == "waiting"
        absent_token = makeup_selected.json()["participant_token"]

        # Teacher starts makeup session
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup_data['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        # Absent student answers and hands in
        state = client.get(
            f"/api/quizzes/student/sessions/{makeup_selected.json()['join_code']}",
            headers={"X-Quiz-Token": absent_token},
        )
        assert state.status_code == 200
        assert state.json()["status"] == "in_progress"
        assert (
            client.post(
                f"/api/quizzes/student/sessions/{makeup_selected.json()['join_code']}/answer",
                headers={"X-Quiz-Token": absent_token},
                json=choice_answer(
                    client,
                    {"X-Quiz-Token": absent_token},
                    correct_choice_id(environment["question"]),
                ),
            ).status_code
            == 200
        )
        hand_in_quiz(
            client, makeup_selected.json()["join_code"], {"X-Quiz-Token": absent_token}
        )

        # Teacher finishes makeup session
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup_data['id']}/finish",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        # Absent student sees their completed exam in history
        student_results = client.get(
            "/api/quizzes/student/results",
            headers=absent_headers,
        )
        assert student_results.status_code == 200
        results_list = student_results.json()
        assert len(results_list) == 1
        assert results_list[0]["score"] == 2.0

        # Teacher export includes absent student's result
        export = client.get(
            f"/api/quizzes/sessions/results/export?class_id={environment['student_class']['id']}",
            headers=environment["teacher_headers"],
        )
        assert export.status_code == 200
        assert absent_account["identifier"] in export.text


def start_makeup_with_open_training(
    client: TestClient,
    environment: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], str]:
    """Let the class take the exam, then open a training before the makeup."""
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
            json=choice_answer(
                client, participant_headers, correct_choice_id(environment["question"])
            ),
        ).status_code
        == 200
    )
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    bank_id = environment["question"]["question_bank_id"]
    assert (
        client.put(
            f"/api/quizzes/training/classes/{environment['student_class']['id']}"
            "/question-banks",
            headers=environment["teacher_headers"],
            json={
                "question_banks": [{"question_bank_id": bank_id, "question_count": 1}]
            },
        ).status_code
        == 200
    )
    makeup = client.post(
        "/api/quizzes/makeup/sessions",
        headers=environment["teacher_headers"],
        json={
            "class_id": environment["student_class"]["id"],
            "quiz_ids": [environment["quiz"]["id"]],
        },
    ).json()
    training = client.post(
        f"/api/quizzes/training/{bank_id}/start",
        headers=environment["student_headers"],
    )
    assert training.status_code == 201
    training_headers = {"X-Quiz-Token": training.json()["participant_token"]}
    selected = client.post(
        f"/api/quizzes/makeup/{makeup['join_code']}/select",
        headers=environment["student_headers"],
        json={"quiz_id": environment["quiz"]["id"]},
    )
    assert selected.status_code == 201
    return makeup, training_headers, training.json()["join_code"]


def test_makeup_discards_trainings_open_on_its_question_banks(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "makeup-training.db")) as client:
        environment = exam_environment(client)
        _, training_headers, training_code = start_makeup_with_open_training(
            client, environment
        )

        answered = client.post(
            f"/api/quizzes/student/sessions/{training_code}/answer",
            headers=training_headers,
            # The training is gone, so it has no tokens: the body never matters.
            json={"question_id": 0, "selected_choice_ids": ["unknown"]},
        )
        assert answered.status_code == 401


def test_training_gives_no_feedback_while_an_exam_uses_its_bank(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A training started concurrently with the exam escapes the discard; the
    # answer endpoint must still refuse to reveal the correction.
    monkeypatch.setattr(
        "app.routers.makeup.discard_active_training_sessions",
        lambda *arguments: None,
    )
    with make_client(settings_for(tmp_path / "training-guard.db")) as client:
        environment = exam_environment(client)
        _, training_headers, training_code = start_makeup_with_open_training(
            client, environment
        )

        answered = client.post(
            f"/api/quizzes/student/sessions/{training_code}/answer",
            headers=training_headers,
            json=choice_answer(
                client, training_headers, correct_choice_id(environment["question"])
            ),
        )
        assert answered.status_code == 409
        assert "training_feedback" not in answered.text


def started_makeup_child(
    client, environment: dict[str, Any], *, start: bool = True
) -> tuple[dict, dict[str, Any], dict[str, str]]:
    """A make-up with the student's child session, started unless asked not to."""
    makeup = create_makeup(client, environment)
    assert (
        client.post(
            "/api/quizzes/makeup/join",
            headers=environment["student_headers"],
            json={"join_code": makeup["join_code"]},
        ).status_code
        == 200
    )
    selected = select_quiz(client, environment, makeup, environment["student_headers"])
    assert selected.status_code == 201
    if start:
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
    child_headers = {"X-Quiz-Token": selected.json()["participant_token"]}
    return makeup, selected.json(), child_headers


def child_session(client, join_code: str) -> QuizSession:
    with client.app.state.session_factory() as session:
        child = session.scalar(
            select(QuizSession).where(QuizSession.join_code == join_code)
        )
        assert child is not None
        return child


def test_makeup_children_stay_out_of_the_active_session_list(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    _, child, _ = started_makeup_child(client, environment, start=False)

    active_ids = [
        listed["id"]
        for listed in client.get("/api/quizzes/sessions/active", headers=headers).json()
    ]
    assert child_session(client, child["join_code"]).id not in active_ids
    assert active_ids == []


def test_many_makeup_children_do_not_push_a_class_exam_out_of_the_list(
    environment,
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    launched = client.post(
        f"/api/quizzes/{environment['quiz']['id']}/launch",
        headers=headers,
        json={"class_id": environment["student_class"]["id"]},
    )
    assert launched.status_code == 201
    # A make-up taken by 25 students, all newer than the class exam: the list
    # shows at most 20 sessions, newest first.
    with client.app.state.session_factory() as session:
        class_exam = session.get(QuizSession, launched.json()["id"])
        assert class_exam is not None
        quiz = session.get(Quiz, class_exam.quiz_id)
        assert quiz is not None
        makeup = MakeupSession(
            owner_id=quiz.owner_id,
            class_id=environment["student_class"]["id"],
            class_name=class_exam.class_name,
            join_code="MKP0001",
            status="in_progress",
        )
        session.add(makeup)
        session.flush()
        for index in range(25):
            session.add(
                QuizSession(
                    quiz_id=class_exam.quiz_id,
                    class_id=class_exam.class_id,
                    class_name=class_exam.class_name,
                    join_code=f"CHD{index:04d}",
                    status="in_progress",
                    makeup_session_id=makeup.id,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()

    active = client.get("/api/quizzes/sessions/active", headers=headers).json()
    assert [listed["id"] for listed in active] == [launched.json()["id"]]


@pytest.mark.parametrize("action", ["start", "pause", "resume", "cancel"])
def test_class_session_controls_refuse_a_makeup_child(environment, action: str) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup, child, _ = started_makeup_child(
        client, environment, start=action != "start"
    )
    if action == "resume":
        assert (
            client.post(
                f"/api/quizzes/makeup/sessions/{makeup['id']}/pause", headers=headers
            ).status_code
            == 200
        )
    before = child_session(client, child["join_code"])

    refused = client.post(
        f"/api/quizzes/sessions/{before.id}/{action}", headers=headers
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "QUIZ_SESSION_IS_MAKEUP"
    after = child_session(client, child["join_code"])
    assert (after.status, after.paused_at, after.started_at) == (
        before.status,
        before.paused_at,
        before.started_at,
    )


def test_a_paused_makeup_can_be_finished_directly(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    makeup, child, child_headers = started_makeup_child(client, environment)
    child_url = f"/api/quizzes/student/sessions/{child['join_code']}"
    assert (
        client.post(
            f"{child_url}/answer",
            headers=child_headers,
            json=choice_answer(
                client, child_headers, correct_choice_id(environment["question"])
            ),
        ).status_code
        == 200
    )
    url = f"/api/quizzes/makeup/sessions/{makeup['id']}"
    assert client.post(f"{url}/pause", headers=headers).json()["status"] == "paused"

    finished = client.post(f"{url}/finish", headers=headers)
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"
    assert child_session(client, child["join_code"]).status == "finished"
    with client.app.state.session_factory() as session:
        answer = session.scalar(
            select(QuizAnswer)
            .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
            .where(QuizSession.join_code == child["join_code"])
        )
        assert answer is not None
        assert (answer.score, answer.is_graded) == (2.0, True)


def test_listing_shows_the_teachers_makeups(environment) -> None:
    client = environment["client"]
    makeup = create_makeup(client, environment)
    listed = client.get(
        "/api/quizzes/makeup/sessions", headers=environment["teacher_headers"]
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [makeup["id"]]


def makeup_selects(client, headers) -> tuple[int, list[dict[str, Any]]]:
    """SELECT statements of the teacher's make-up list, and the list."""
    engine = client.app.state.session_factory.kw["bind"]
    statements: list[str] = []

    def record_statement(_c, _cursor, statement, _p, _context, _many) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        listed = client.get("/api/quizzes/makeup/sessions", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    assert listed.status_code == 200
    return len(statements), listed.json()


def test_makeup_list_does_not_grow_with_the_makeups(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    create_makeup(client, environment)
    one_makeup, _ = makeup_selects(client, headers)
    for _ in range(2):
        create_makeup(client, environment)
    three_makeups, listed = makeup_selects(client, headers)
    assert len(listed) == 3
    assert three_makeups == one_makeup


def test_the_live_feed_lists_open_makeups_and_the_list_pages_all(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    finished = create_makeup(client, environment)
    still_open = create_makeup(client, environment)
    with client.app.state.session_factory() as session:
        session.execute(
            update(MakeupSession)
            .where(MakeupSession.id == finished["id"])
            .values(status=SessionStatus.FINISHED)
        )
        session.commit()
        owner = session.get(User, session.get(MakeupSession, finished["id"]).owner_id)
        assert [
            item.id for item in active_makeup_session_responses(owner, session)
        ] == [still_open["id"]]

    first_page = client.get(
        "/api/quizzes/makeup/sessions", headers=headers, params={"page_size": 1}
    )
    assert first_page.headers["X-Total-Count"] == "2"
    assert [item["id"] for item in first_page.json()] == [still_open["id"]]
    second_page = client.get(
        "/api/quizzes/makeup/sessions",
        headers=headers,
        params={"page_size": 1, "page": 2},
    )
    assert [item["id"] for item in second_page.json()] == [finished["id"]]
