"""What a student's exam history reveals, and to whom."""

from pathlib import Path
from typing import Any

from support import (
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
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


def finished_exam(client: Any, environment: dict[str, Any]) -> dict[str, Any]:
    """An exam the first student sits, and a classmate leaves before it starts."""
    classmate = add_student(client, environment)
    environment["classmate_headers"] = classmate
    quiz_session, participant_headers = launch_and_join(client, environment)
    url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
    joined = client.post(
        "/api/quizzes/join",
        headers=classmate,
        json={"join_code": quiz_session["join_code"]},
    )
    assert joined.status_code == 201
    left = client.post(
        f"{url}/leave",
        headers={"X-Quiz-Token": joined.json()["participant_token"]},
    )
    assert left.status_code == 204
    assert (
        client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )
    answer = {"selected_choice_ids": [correct_choice_id(environment["question"])]}
    assert (
        client.post(f"{url}/answer", headers=participant_headers, json=answer)
    ).status_code == 200
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    teacher_view = client.get(
        f"/api/quizzes/sessions/{quiz_session['id']}",
        headers=environment["teacher_headers"],
    ).json()
    assert teacher_view["status"] == "finished"
    return quiz_session


def history(client: Any, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/api/quizzes/student/results", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_a_student_who_left_before_the_start_gets_no_correction(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "history-left")) as client:
        environment = exam_environment(client)
        quiz_session = finished_exam(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        assert history(client, environment["classmate_headers"]) == []
        assert [
            item["session_id"]
            for item in history(client, environment["student_headers"])
        ] == [quiz_session["id"]]


def test_the_correction_waits_for_the_grades_to_be_published(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "history-publish")) as client:
        environment = exam_environment(client)
        quiz_session = finished_exam(client, environment)

        [unpublished] = history(client, environment["student_headers"])
        assert unpublished["grades_published"] is False
        assert unpublished["score"] is None
        assert unpublished["maximum_score"] is None
        [answer] = unpublished["answers"]
        assert answer["submitted_answers"] == ["Two"]
        assert answer["expected_answers"] == []
        assert answer["score"] is None
        assert answer["is_correct"] is None
        assert answer["feedback"] is None

        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        [published] = history(client, environment["student_headers"])
        assert published["grades_published"] is True
        assert published["score"] == 2.0
        assert published["maximum_score"] == 2.0
        [answer] = published["answers"]
        assert answer["expected_answers"] == ["Two"]
        assert answer["score"] == 2.0
        assert answer["is_correct"] is True
