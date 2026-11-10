"""An answer names the question it was given for; states carry server time."""

from datetime import UTC, datetime
from pathlib import Path

from app.models import QuizAnswer

from support import (
    choice_tokens,
    correct_choice_id,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)


def test_an_answer_for_another_question_is_refused(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "question-id")) as client:
        environment = exam_environment(client)
        quiz_session, headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        question = environment["question"]
        body = {
            "selected_choice_ids": choice_tokens(
                client, headers, correct_choice_id(question)
            )
        }

        stale = client.post(
            f"{url}/answer", headers=headers, json={**body, "question_id": 999999}
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "ANSWER_QUESTION_MISMATCH"
        with client.app.state.session_factory() as session:
            assert session.query(QuizAnswer).count() == 0

        answered = client.post(
            f"{url}/answer",
            headers=headers,
            json={**body, "question_id": question["id"]},
        )
        assert answered.status_code == 200
        with client.app.state.session_factory() as session:
            assert session.query(QuizAnswer).count() == 1


def test_states_carry_the_server_time(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "server-now")) as client:
        environment = exam_environment(client)
        quiz_session, headers = launch_and_join(client, environment)
        before = datetime.now(UTC)
        student_state = client.get(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}",
            headers=headers,
        ).json()
        teacher_state = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=environment["teacher_headers"],
        ).json()
        after = datetime.now(UTC)
        for state in (student_state, teacher_state):
            server_now = datetime.fromisoformat(state["server_now"])
            assert before <= server_now <= after
