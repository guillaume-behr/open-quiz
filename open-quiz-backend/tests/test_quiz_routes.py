"""Teacher quiz management paths outside the main flows."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update

from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    TrainingQuizProfile,
)

from support import (
    concurrent_writes,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


@pytest.fixture
def environment(tmp_path: Path):
    with make_client(settings_for(tmp_path / "quiz-routes")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        yield environment


def start_and_answer(
    client, environment: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    launched, participant_headers = launch_and_join(client, environment)
    assert (
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )
    answered = client.post(
        f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
        headers=participant_headers,
        json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
    )
    assert answered.status_code == 200
    return launched, participant_headers


def finished_exam(client, environment: dict[str, Any]) -> dict[str, Any]:
    launched, participant_headers = start_and_answer(client, environment)
    hand_in_quiz(client, launched["join_code"], participant_headers)
    return launched


def owner_id(client, headers: dict[str, str]) -> int:
    return client.get("/api/users/me", headers=headers).json()["id"]


def quiz_payload(environment: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    return {
        "title": "Edge quiz",
        "question_bank_ids": [environment["question"]["question_bank_id"]],
        "easy_question_count": 1,
        "medium_question_count": 0,
        "hard_question_count": 0,
        **overrides,
    }


def test_quiz_management_rejects_unknown_and_busy_quizzes(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    quiz = environment["quiz"]

    assert client.get("/api/quizzes/999999/preview", headers=headers).status_code == 404
    invalid_bank = client.post(
        f"/api/quizzes/{quiz['id']}/update",
        headers=headers,
        json=quiz_payload(environment, question_bank_ids=[999999]),
    )
    assert invalid_bank.status_code == 422

    listed = client.get(
        "/api/quizzes",
        headers=headers,
        params={"search": "Edge", "grade_level": "5e"},
    )
    assert [item["id"] for item in listed.json()] == [quiz["id"]]

    no_class = client.post(
        f"/api/quizzes/{quiz['id']}/launch",
        headers=headers,
        json={"class_id": 999999},
    )
    assert no_class.status_code == 422
    empty_class = client.post(
        "/api/classes", headers=headers, json={"name": "Empty", "grade_level": "5e"}
    ).json()
    assert (
        client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=headers,
            json={"class_id": empty_class["id"]},
        ).status_code
        == 409
    )

    launched, _ = launch_and_join(client, environment)
    assert client.delete(f"/api/quizzes/{quiz['id']}", headers=headers).status_code == (
        409
    )
    assert (
        client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=headers,
            json=quiz_payload(environment),
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/quizzes/sessions/{launched['id']}", headers=headers
        ).status_code
        == 409
    )
    for action in ("pause", "resume"):
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/{action}", headers=headers
            ).status_code
            == 409
        )


def test_deleting_quizzes_keeps_results_and_makeups(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    payload = quiz_payload(environment, title="Disposable")

    disposable = client.post("/api/quizzes", headers=headers, json=payload).json()
    cancelled = client.post(
        f"/api/quizzes/{disposable['id']}/launch",
        headers=headers,
        json={"class_id": environment["student_class"]["id"]},
    ).json()
    assert (
        client.post(
            f"/api/quizzes/sessions/{cancelled['id']}/cancel", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(f"/api/quizzes/{disposable['id']}", headers=headers).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/quizzes/{disposable['id']}/preview", headers=headers
        ).status_code
        == 404
    )

    used_by_makeup = client.post("/api/quizzes", headers=headers, json=payload).json()
    with client.app.state.session_factory() as session:
        makeup = MakeupSession(
            owner_id=owner_id(client, headers),
            class_id=environment["student_class"]["id"],
            class_name="5e A",
            join_code="MAKEUP03",
        )
        session.add(makeup)
        session.flush()
        session.add(
            MakeupSessionQuiz(session_id=makeup.id, quiz_id=used_by_makeup["id"])
        )
        session.commit()
    assert (
        client.delete(
            f"/api/quizzes/{used_by_makeup['id']}", headers=headers
        ).status_code
        == 409
    )

    finished_exam(client, environment)
    assert (
        client.delete(
            f"/api/quizzes/{environment['quiz']['id']}", headers=headers
        ).status_code
        == 409
    )


def test_training_profiles_are_not_managed_as_exams(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    with client.app.state.session_factory() as session:
        training = Quiz(
            owner_id=owner_id(client, headers),
            title="Training",
            mode="training",
            question_count=0,
        )
        session.add(training)
        session.commit()
        training_id = training.id
    assert (
        client.get(f"/api/quizzes/{training_id}/preview", headers=headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/quizzes/{training_id}/update",
            headers=headers,
            json=quiz_payload(environment),
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/quizzes/{training_id}/launch",
            headers=headers,
            json={"class_id": environment["student_class"]["id"]},
        ).status_code
        == 409
    )


def test_session_control_conflicts(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]

    launched, participant_headers = start_and_answer(client, environment)
    session_url = f"/api/quizzes/sessions/{launched['id']}"
    restarted = client.post(f"{session_url}/start", headers=headers)
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "in_progress"
    assert client.post(f"{session_url}/cancel", headers=headers).status_code == 409

    hand_in_quiz(client, launched["join_code"], participant_headers)
    assert client.post(f"{session_url}/pause", headers=headers).status_code == 409
    assert client.post(f"{session_url}/cancel", headers=headers).status_code == 409


def test_starting_requires_a_present_participant_and_survives_races(
    environment,
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    launched, participant_headers = launch_and_join(client, environment)
    session_url = f"/api/quizzes/sessions/{launched['id']}"
    assert (
        client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/leave",
            headers=participant_headers,
        ).status_code
        == 204
    )
    assert client.post(f"{session_url}/start", headers=headers).status_code == 409

    with concurrent_writes(
        client,
        (
            "UPDATE quiz_sessions SET status",
            lambda connection: connection.execute(
                update(QuizSession)
                .where(QuizSession.id == launched["id"])
                .values(status="cancelled")
            ),
        ),
    ) as fired:
        raced = client.post(f"{session_url}/start", headers=headers)
    assert fired
    assert raced.status_code == 200
    assert raced.json()["status"] == "cancelled"


def test_results_and_answer_reviews_validate_their_targets(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]

    running, participant_headers = start_and_answer(client, environment)
    running_url = f"/api/quizzes/sessions/{running['id']}"
    assert (
        client.get(f"{running_url}/participants/1/answers", headers=headers).status_code
        == 409
    )
    assert (
        client.post(f"{running_url}/publish-grades", headers=headers).status_code == 409
    )
    assert (
        client.post(
            f"{running_url}/answers/1/grade", headers=headers, json={"score": 1}
        ).status_code
        == 409
    )
    with client.app.state.session_factory() as session:
        participant_id = session.scalar(
            select(QuizParticipant.id).where(
                QuizParticipant.session_id == running["id"]
            )
        )
    hand_in_quiz(client, running["join_code"], participant_headers)

    assert (
        client.get(
            f"{running_url}/participants/999999/answers", headers=headers
        ).status_code
        == 404
    )
    answers = client.get(
        f"{running_url}/participants/{participant_id}/answers", headers=headers
    )
    assert answers.status_code == 200
    answer_id = answers.json()[0]["id"]

    assert (
        client.post(
            f"{running_url}/answers/999999/grade", headers=headers, json={"score": 1}
        ).status_code
        == 404
    )
    choice_answer = client.post(
        f"{running_url}/answers/{answer_id}/grade", headers=headers, json={"score": 1}
    )
    assert choice_answer.status_code == 422

    published = client.post(f"{running_url}/publish-grades", headers=headers)
    assert published.status_code == 200
    first_published_at = published.json()["grades_published_at"]
    again = client.post(f"{running_url}/publish-grades", headers=headers)
    assert again.json()["grades_published_at"] == first_published_at
    assert (
        client.post(
            f"{running_url}/answers/{answer_id}/grade",
            headers=headers,
            json={"score": 1},
        ).status_code
        == 409
    )

    filtered = client.get(
        "/api/quizzes/sessions/results",
        headers=headers,
        params={"class_search": "nothing-matches"},
    )
    assert filtered.json() == []
    assert (
        client.get(
            "/api/quizzes/sessions/results/export",
            headers=headers,
            params={"class_id": 999999},
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/quizzes/sessions/results/export",
            headers=headers,
            params={
                "class_id": environment["student_class"]["id"],
                "quiz_id": 999999,
            },
        ).status_code
        == 404
    )


def test_written_answers_cannot_exceed_their_points(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    bank_id = environment["question"]["question_bank_id"]
    written = client.post(
        f"/api/question-banks/{bank_id}/questions",
        headers=headers,
        data={
            "payload": json.dumps(
                {
                    "prompt": "Explain",
                    "difficulty": "medium",
                    "answer_mode": "written",
                    "choices": [{"label": "Because", "is_correct": True, "points": 2}],
                }
            )
        },
    ).json()
    quiz = client.post(
        "/api/quizzes",
        headers=headers,
        json=quiz_payload(
            environment,
            title="Written",
            easy_question_count=0,
            medium_question_count=1,
        ),
    ).json()
    environment = {**environment, "quiz": quiz, "question": written}
    launched, participant_headers = launch_and_join(client, environment)
    client.post(f"/api/quizzes/sessions/{launched['id']}/start", headers=headers)
    assert (
        client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
            headers=participant_headers,
            json={"written_answer": "Because"},
        ).status_code
        == 200
    )
    hand_in_quiz(client, launched["join_code"], participant_headers)
    session_url = f"/api/quizzes/sessions/{launched['id']}"
    assert (
        client.post(f"{session_url}/publish-grades", headers=headers).status_code == 409
    )
    with client.app.state.session_factory() as session:
        answer_id = session.scalar(
            select(QuizAnswer.id).where(QuizAnswer.session_id == launched["id"])
        )
    too_high = client.post(
        f"{session_url}/answers/{answer_id}/grade",
        headers=headers,
        json={"score": 3},
    )
    assert too_high.status_code == 422


def test_cancelled_sessions_without_answers_are_cleaned_up(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    launched, _ = launch_and_join(client, environment)
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="cancelled")
        )
        session.commit()
    assert client.get("/api/quizzes/sessions/active", headers=headers).json() == []
    with client.app.state.session_factory() as session:
        assert session.get(QuizSession, launched["id"]) is None


def test_training_configuration_validates_its_input(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    class_id = environment["student_class"]["id"]
    bank_id = environment["question"]["question_bank_id"]
    url = f"/api/quizzes/training/classes/{class_id}/question-banks"

    assert (
        client.get(
            "/api/quizzes/training/classes/999999/question-banks", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/quizzes/training/classes/999999/question-banks",
            headers=headers,
            json={"question_bank_ids": [bank_id]},
        ).status_code
        == 404
    )
    assert (
        client.put(
            url, headers=headers, json={"question_bank_ids": [999999]}
        ).status_code
        == 422
    )
    assert (
        client.put(
            url,
            headers=headers,
            json={
                "question_banks": [{"question_bank_id": bank_id, "question_count": 5}]
            },
        ).status_code
        == 422
    )


def test_training_profile_creation_tolerates_a_concurrent_creator(
    environment,
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_headers = environment["student_headers"]
    class_id = environment["student_class"]["id"]
    bank_id = environment["question"]["question_bank_id"]
    teacher_id = owner_id(client, headers)
    assert (
        client.put(
            f"/api/quizzes/training/classes/{class_id}/question-banks",
            headers=headers,
            json={"question_bank_ids": [bank_id]},
        ).status_code
        == 200
    )

    def create_profile(connection) -> None:
        quiz_id = connection.execute(
            Quiz.__table__.insert()
            .values(
                owner_id=teacher_id,
                title="Concurrent training",
                mode="training",
                source_language="fr",
                question_count=0,
                duration_seconds=900,
                allow_previous_questions=True,
                allow_answer_review=False,
                allow_negative_points=False,
                same_questions_for_all=False,
                easy_question_count=0,
                medium_question_count=0,
                hard_question_count=0,
                easy_points=0,
                medium_points=0,
                hard_points=0,
            )
            .returning(Quiz.id)
        ).scalar_one()
        connection.execute(
            TrainingQuizProfile.__table__.insert().values(
                owner_id=teacher_id, quiz_id=quiz_id
            )
        )

    with concurrent_writes(
        client, ("INSERT INTO training_quiz_profiles", create_profile)
    ) as fired:
        started = client.post(
            f"/api/quizzes/training/{bank_id}/start", headers=student_headers
        )
    assert fired
    assert started.status_code == 201
