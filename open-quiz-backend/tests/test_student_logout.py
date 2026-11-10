"""Logging a student out also ends their training participations."""

from pathlib import Path

from support import (
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
    training_banks,
)


def test_logout_revokes_training_tokens_but_not_exam_ones(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "logout")) as client:
        environment = exam_environment(client)
        bank_id = environment["question"]["question_bank_id"]
        assert (
            client.put(
                f"/api/quizzes/training/classes/{environment['student_class']['id']}"
                "/question-banks",
                headers=environment["teacher_headers"],
                json=training_banks(bank_id),
            ).status_code
            == 200
        )
        training = client.post(
            f"/api/quizzes/training/{bank_id}/start",
            headers=environment["student_headers"],
        )
        assert training.status_code == 201
        training_url = f"/api/quizzes/student/sessions/{training.json()['join_code']}"
        training_headers = {"X-Quiz-Token": training.json()["participant_token"]}
        assert client.get(training_url, headers=training_headers).status_code == 200

        assert (
            client.post(
                "/api/student-auth/logout", headers=environment["student_headers"]
            ).status_code
            == 204
        )

        # The next person on this computer cannot answer as this student.
        assert client.get(training_url, headers=training_headers).status_code == 401


def test_logout_keeps_a_waiting_exam_participation(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "logout-exam")) as client:
        environment = exam_environment(client)
        quiz_session, exam_headers = launch_and_join(client, environment)
        assert (
            client.post(
                "/api/student-auth/logout", headers=environment["student_headers"]
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}",
                headers=exam_headers,
            ).status_code
            == 200
        )
