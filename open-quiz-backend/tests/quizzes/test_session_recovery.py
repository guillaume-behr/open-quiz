"""Ending a class exam early, and students getting back into an exam.

A teacher finishes a class session that someone holds open; a student added
to the class after the launch gets questions of their own; a make-up student
who lost their tab takes their quiz back with the make-up code; an exam stays
in the history of a student who left its class; and an open make-up keeps
the questions it may still draw.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from support import (
    add_class_student,
    choice_answer,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


@pytest.fixture
def environment(tmp_path: Path):
    with make_client(settings_for(tmp_path / "quiz.db")) as client:
        yield {"client": client, **exam_environment(client)}


def started_session(
    client: TestClient, environment: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    launched, participant_headers = launch_and_join(client, environment)
    started = client.post(
        f"/api/quizzes/sessions/{launched['id']}/start",
        headers=environment["teacher_headers"],
    )
    assert started.status_code == 200
    return launched, participant_headers


def answer_correctly(
    client: TestClient,
    environment: dict[str, Any],
    join_code: str,
    participant_headers: dict[str, str],
) -> None:
    answered = client.post(
        f"/api/quizzes/student/sessions/{join_code}/answer",
        headers=participant_headers,
        json=choice_answer(
            client, participant_headers, correct_choice_id(environment["question"])
        ),
    )
    assert answered.status_code == 200


def test_a_teacher_finishes_a_running_class_session(environment) -> None:
    client = environment["client"]
    teacher_headers = environment["teacher_headers"]
    launched, participant_headers = started_session(client, environment)
    # Answered but never handed in: the session would run until its timer.
    answer_correctly(client, environment, launched["join_code"], participant_headers)
    url = f"/api/quizzes/sessions/{launched['id']}"

    finished = client.post(f"{url}/finish", headers=teacher_headers)

    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"
    # Graded as the timer would have.
    assert finished.json()["participants"][0]["score"] == 2
    # A second click changes nothing.
    again = client.post(f"{url}/finish", headers=teacher_headers)
    assert again.status_code == 200
    assert again.json()["status"] == "finished"
    student_state = client.get(
        f"/api/quizzes/student/sessions/{launched['join_code']}",
        headers=participant_headers,
    )
    assert student_state.json()["status"] == "finished"


def test_a_paused_class_session_can_be_finished_but_not_a_waiting_one(
    environment,
) -> None:
    client = environment["client"]
    teacher_headers = environment["teacher_headers"]
    launched, _ = launch_and_join(client, environment)
    url = f"/api/quizzes/sessions/{launched['id']}"

    waiting = client.post(f"{url}/finish", headers=teacher_headers)
    assert waiting.status_code == 409
    assert waiting.json()["detail"]["code"] == "QUIZ_SESSION_NOT_FINISHABLE"

    assert client.post(f"{url}/start", headers=teacher_headers).status_code == 200
    assert client.post(f"{url}/pause", headers=teacher_headers).status_code == 200
    finished = client.post(f"{url}/finish", headers=teacher_headers)
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"


def test_a_student_added_after_the_launch_gets_a_draw_of_their_own(
    environment,
) -> None:
    client = environment["client"]
    launched, _ = launch_and_join(client, environment)
    newcomer_headers = add_class_student(client, environment, "Late")

    joined = client.post(
        "/api/quizzes/join",
        headers=newcomer_headers,
        json={"join_code": launched["join_code"]},
    )
    assert joined.status_code == 201
    assert joined.json()["total_questions"] == 1
    # Joining again resumes, without drawing twice.
    again = client.post(
        "/api/quizzes/join",
        headers=newcomer_headers,
        json={"join_code": launched["join_code"]},
    )
    assert again.status_code == 201
    assert again.json()["total_questions"] == 1

    # Once the exam has started, nobody new may join.
    assert (
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )
    too_late = client.post(
        "/api/quizzes/join",
        headers=add_class_student(client, environment, "Later"),
        json={"join_code": launched["join_code"]},
    )
    assert too_late.status_code == 403


def open_makeup(client: TestClient, environment: dict[str, Any]) -> dict[str, Any]:
    """Finish the class exam, then open a make-up of it."""
    launched, participant_headers = started_session(client, environment)
    answer_correctly(client, environment, launched["join_code"], participant_headers)
    hand_in_quiz(client, launched["join_code"], participant_headers)
    makeup = client.post(
        "/api/quizzes/makeup/sessions",
        headers=environment["teacher_headers"],
        json={
            "class_id": environment["student_class"]["id"],
            "quiz_ids": [environment["quiz"]["id"]],
        },
    )
    assert makeup.status_code == 201
    return makeup.json()


def test_a_makeup_student_who_lost_their_tab_resumes_with_the_makeup_code(
    environment,
) -> None:
    client = environment["client"]
    student_headers = environment["student_headers"]
    makeup = open_makeup(client, environment)
    selected = client.post(
        f"/api/quizzes/makeup/{makeup['join_code']}/select",
        headers=student_headers,
        json={"quiz_id": environment["quiz"]["id"]},
    )
    assert selected.status_code == 201
    first_token = selected.json()["participant_token"]
    child_code = selected.json()["join_code"]
    assert (
        client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )

    # The make-up lobby says the quiz is chosen already...
    lobby = client.post(
        "/api/quizzes/makeup/join",
        headers=student_headers,
        json={"join_code": makeup["join_code"]},
    )
    assert lobby.status_code == 409
    assert lobby.json()["detail"]["code"] == "MAKEUP_ALREADY_CHOSEN"
    # ...and joining with the make-up code takes that quiz back.
    resumed = client.post(
        "/api/quizzes/join",
        headers=student_headers,
        json={"join_code": makeup["join_code"]},
    )
    assert resumed.status_code == 201
    assert resumed.json()["join_code"] == child_code
    assert resumed.json()["question"] is not None
    old_tab = client.get(
        f"/api/quizzes/student/sessions/{child_code}",
        headers={"X-Quiz-Token": first_token},
    )
    assert old_tab.status_code == 401
    assert old_tab.json()["detail"]["code"] == "QUIZ_PARTICIPANT_SESSION_RESUMED"


def test_a_makeup_code_opens_no_quiz_for_a_student_who_chose_none(
    environment,
) -> None:
    client = environment["client"]
    makeup = open_makeup(client, environment)

    joined = client.post(
        "/api/quizzes/join",
        headers=environment["student_headers"],
        json={"join_code": makeup["join_code"]},
    )
    assert joined.status_code == 403
    assert joined.json()["detail"]["code"] == "QUIZ_JOIN_REJECTED"


def test_an_exam_stays_in_the_history_of_a_student_who_left_the_class(
    environment,
) -> None:
    client = environment["client"]
    launched, participant_headers = started_session(client, environment)
    answer_correctly(client, environment, launched["join_code"], participant_headers)
    hand_in_quiz(client, launched["join_code"], participant_headers)

    removed = client.delete(
        f"/api/classes/{environment['student_class']['id']}/accounts/"
        f"{environment['account']['id']}",
        headers=environment["teacher_headers"],
    )
    assert removed.status_code == 204

    history = client.get(
        "/api/quizzes/student/results", headers=environment["student_headers"]
    )
    assert [item["session_id"] for item in history.json()] == [launched["id"]]


def test_an_open_makeup_keeps_the_questions_it_may_draw(environment) -> None:
    client = environment["client"]
    teacher_headers = environment["teacher_headers"]
    open_makeup(client, environment)
    question = environment["question"]

    deleted = client.delete(
        f"/api/question-banks/questions/{question['id']}", headers=teacher_headers
    )
    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "QUESTION_USED_BY_MAKEUP"

    def edit(difficulty: str, prompt: str):
        return client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": prompt,
                        "difficulty": difficulty,
                        "answer_mode": "single",
                        "choices": [
                            {
                                "id": choice["id"],
                                "label": choice["label"],
                                "is_correct": choice["is_correct"],
                                "points": choice["points"],
                            }
                            for choice in question["choices"]
                        ],
                    }
                )
            },
        )

    moved = edit("hard", question["prompt"])
    assert moved.status_code == 409
    assert moved.json()["detail"]["code"] == "QUESTION_USED_BY_MAKEUP"
    # A change that leaves the draw as it is goes through.
    assert edit("easy", "One plus one, again?").status_code == 200
