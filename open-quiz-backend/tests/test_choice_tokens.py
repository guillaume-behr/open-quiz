"""Students name choices by opaque tokens, never by their real ids."""

from pathlib import Path
from typing import Any

from support import (
    correct_choice_id,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)


def add_student(client: Any, environment: dict[str, Any]) -> dict[str, str]:
    headers = environment["teacher_headers"]
    account = client.post(
        "/api/students",
        headers=headers,
        json={"first_name": "Second", "last_name": "Student"},
    ).json()
    assert (
        client.post(
            f"/api/classes/{environment['student_class']['id']}/accounts/"
            f"{account['id']}",
            headers=headers,
        ).status_code
        == 200
    )
    login = client.post(
        "/api/student-auth/login",
        json={
            "identifier": account["identifier"],
            "password": account["generated_password"],
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_students_never_see_or_send_real_choice_ids(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "tokens")) as client:
        environment = exam_environment(client)
        second_student = add_student(client, environment)
        quiz_session, first = launch_and_join(client, environment)
        joined = client.post(
            "/api/quizzes/join",
            headers=second_student,
            json={"join_code": quiz_session["join_code"]},
        )
        assert joined.status_code == 201
        second = {"X-Quiz-Token": joined.json()["participant_token"]}
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        question = environment["question"]
        real_ids = {choice["id"] for choice in question["choices"]}

        def choices_of(headers: dict[str, str]) -> dict[str, str]:
            state = client.get(url, headers=headers).json()
            return {
                choice["label"]: choice["id"] for choice in state["question"]["choices"]
            }

        first_choices = choices_of(first)
        second_choices = choices_of(second)
        for choices in (first_choices, second_choices):
            for token in choices.values():
                assert isinstance(token, str)
                assert token not in {str(choice_id) for choice_id in real_ids}
        # Each participation has tokens of its own.
        assert not set(first_choices.values()) & set(second_choices.values())

        correct_label = next(
            choice["label"] for choice in question["choices"] if choice["is_correct"]
        )
        # A real id, or another participant's token, names no choice.
        assert (
            client.post(
                f"{url}/answer",
                headers=first,
                json={
                    "question_id": question["id"],
                    "selected_choice_ids": [correct_choice_id(question)],
                },
            ).status_code
            == 422
        )
        borrowed = client.post(
            f"{url}/answer",
            headers=first,
            json={
                "question_id": question["id"],
                "selected_choice_ids": [second_choices[correct_label]],
            },
        )
        assert borrowed.status_code == 422
        assert borrowed.json()["detail"]["code"] == "ANSWER_CHOICE_INVALID"

        answered = client.post(
            f"{url}/answer",
            headers=first,
            json={
                "question_id": question["id"],
                "selected_choice_ids": [first_choices[correct_label]],
            },
        )
        assert answered.status_code == 200
        assert answered.json()["selected_choice_ids"] in (
            None,
            [first_choices[correct_label]],
        )
