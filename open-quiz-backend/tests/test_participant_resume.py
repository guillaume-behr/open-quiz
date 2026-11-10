"""A student who lost their participant token resumes the exam on a new one."""

from pathlib import Path
from typing import Any

from sqlalchemy import update

from app.models import QuizParticipant

from support import (
    add_class_student,
    choice_answer,
    concurrent_writes,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


def started_exam(client: Any, environment: dict[str, Any]):
    quiz_session, participant_headers = launch_and_join(client, environment)
    assert (
        client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )
    return quiz_session, participant_headers


def rejoin(client: Any, environment: dict[str, Any], join_code: str):
    return client.post(
        "/api/quizzes/join",
        headers=environment["student_headers"],
        json={"join_code": join_code},
    )


def test_a_lost_token_is_replaced_and_the_teacher_is_told(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "resume")) as client:
        environment = exam_environment(client)
        quiz_session, old_headers = started_exam(client, environment)
        url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        answered = client.post(
            f"{url}/answer",
            headers=old_headers,
            json=choice_answer(
                client, old_headers, correct_choice_id(environment["question"])
            ),
        )
        assert answered.status_code == 200

        # The tab is gone with its token: joining again resumes the exam.
        resumed = rejoin(client, environment, quiz_session["join_code"])
        assert resumed.status_code == 201
        new_headers = {"X-Quiz-Token": resumed.json()["participant_token"]}
        assert new_headers != old_headers
        assert resumed.json()["answered_count"] == 1
        assert resumed.json()["awaiting_final_submission"] is True

        # The old tab stops working, and says why.
        stale = client.get(url, headers=old_headers)
        assert stale.status_code == 401
        assert stale.json()["detail"]["code"] == "QUIZ_PARTICIPANT_SESSION_RESUMED"

        teacher_view = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=environment["teacher_headers"],
        ).json()
        [participant] = teacher_view["participants"]
        assert participant["violation_count"] == 1
        assert participant["last_violation_type"] == "session_resumed"

        hand_in_quiz(client, quiz_session["join_code"], new_headers)
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=environment["teacher_headers"],
            ).json()["status"]
            == "finished"
        )


def test_resuming_in_the_waiting_room_is_not_reported(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "resume-waiting")) as client:
        environment = exam_environment(client)
        quiz_session, old_headers = launch_and_join(client, environment)

        resumed = rejoin(client, environment, quiz_session["join_code"])
        assert resumed.status_code == 201
        url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        assert client.get(url, headers=old_headers).status_code == 401
        new_headers = {"X-Quiz-Token": resumed.json()["participant_token"]}
        assert client.get(url, headers=new_headers).status_code == 200
        teacher_view = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=environment["teacher_headers"],
        ).json()
        assert teacher_view["participants"][0]["violation_count"] == 0


def test_an_unknown_token_is_still_just_invalid(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "resume-unknown")) as client:
        environment = exam_environment(client)
        quiz_session, _ = started_exam(client, environment)
        response = client.get(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}",
            headers={"X-Quiz-Token": "never-issued"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "QUIZ_PARTICIPANT_TOKEN_INVALID"


def test_another_account_cannot_take_over_a_participation(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "resume-other")) as client:
        environment = exam_environment(client)
        classmate = add_class_student(client, environment)
        quiz_session, headers = started_exam(client, environment)

        # The classmate never joined: after the start they cannot, and they
        # certainly do not get the first student's place.
        taken = client.post(
            "/api/quizzes/join",
            headers=classmate,
            json={"join_code": quiz_session["join_code"]},
        )
        assert taken.status_code == 403
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}",
                headers=headers,
            ).status_code
            == 200
        )


def test_two_resumes_at_once_hand_out_a_single_token(tmp_path: Path) -> None:
    """A resume that lost the race to another one is refused, not merged."""
    with make_client(settings_for(tmp_path / "resume-race")) as client:
        environment = exam_environment(client)
        quiz_session, _ = started_exam(client, environment)

        def resume_elsewhere(connection) -> None:
            connection.execute(
                update(QuizParticipant).values(access_token_hash="0" * 64)
            )

        with concurrent_writes(
            client, ("UPDATE quiz_participants SET", resume_elsewhere)
        ) as fired:
            late = rejoin(client, environment, quiz_session["join_code"])
        assert fired
        assert late.status_code == 403
        assert late.json()["detail"]["code"] == "QUIZ_JOIN_REJECTED"
