"""Make-up sessions: creation, joining, control and their child sessions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.models import (
    MakeupSession,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
)

from support import (
    concurrent_writes,
    correct_choice_id,
    database_connection,
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
                json={
                    "selected_choice_ids": [correct_choice_id(environment["question"])]
                },
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
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
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
                json={
                    "selected_choice_ids": [correct_choice_id(environment["question"])]
                },
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
                json={
                    "selected_choice_ids": [correct_choice_id(environment["question"])]
                },
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
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
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
            json={"question_bank_ids": [bank_id]},
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
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
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
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert answered.status_code == 409
        assert "training_feedback" not in answered.text
