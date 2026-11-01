"""Student exam and training paths outside the main flows."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text, update

from app.models import (
    Question,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
)
from app.routers import quizzes

from support import (
    VALID_PNG,
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
    with make_client(settings_for(tmp_path / "student-routes")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        yield environment


def add_question(client, environment: dict[str, Any], **overrides: Any) -> dict:
    payload = {
        "prompt": "Pick the even number",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [
            {"label": "Two", "is_correct": True, "points": 1},
            {"label": "Three", "is_correct": False},
        ],
        **overrides,
    }
    created = client.post(
        f"/api/question-banks/{environment['question']['question_bank_id']}/questions",
        headers=environment["teacher_headers"],
        data={"payload": json.dumps(payload)},
    )
    assert created.status_code == 201
    return created.json()


def two_question_quiz(client, environment: dict[str, Any], **overrides: Any) -> dict:
    add_question(client, environment)
    quiz = client.post(
        "/api/quizzes",
        headers=environment["teacher_headers"],
        json={
            "title": "Two questions",
            "question_bank_ids": [environment["question"]["question_bank_id"]],
            "allow_previous_questions": True,
            "easy_question_count": 2,
            "medium_question_count": 0,
            "hard_question_count": 0,
            **overrides,
        },
    )
    assert quiz.status_code == 201
    return {**environment, "quiz": quiz.json()}


def started(client, environment: dict[str, Any]) -> tuple[dict, dict[str, str], str]:
    launched, participant_headers = launch_and_join(client, environment)
    assert (
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        ).status_code
        == 200
    )
    return (
        launched,
        participant_headers,
        f"/api/quizzes/student/sessions/{launched['join_code']}",
    )


def answer_current(client, url: str, headers: dict[str, str], **payload: Any):
    state = client.get(url, headers=headers).json()
    question = state["question"]
    if not payload:
        payload = {"selected_choice_ids": [question["choices"][0]["id"]]}
    return client.post(f"{url}/answer", headers=headers, json=payload)


def test_joining_rejects_unknown_codes_classes_and_draws(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_headers = environment["student_headers"]

    unknown = client.post(
        "/api/quizzes/join", headers=student_headers, json={"join_code": "NOPE42"}
    )
    assert unknown.status_code == 403

    other_class = client.post(
        "/api/classes", headers=headers, json={"name": "5e B", "grade_level": "5e"}
    ).json()
    outsider = client.post(
        "/api/students",
        headers=headers,
        json={"first_name": "Out", "last_name": "Sider"},
    ).json()
    client.post(
        f"/api/classes/{other_class['id']}/accounts/{outsider['id']}", headers=headers
    )
    outsider_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/student-auth/login",
            json={
                "identifier": outsider["identifier"],
                "password": outsider["generated_password"],
            },
        ).json()["access_token"]
    }

    launched = client.post(
        f"/api/quizzes/{environment['quiz']['id']}/launch",
        headers=headers,
        json={"class_id": environment["student_class"]["id"]},
    ).json()
    not_in_class = client.post(
        "/api/quizzes/join",
        headers=outsider_headers,
        json={"join_code": launched["join_code"]},
    )
    assert not_in_class.status_code == 403

    # Joining the class after the draw leaves the newcomer without questions.
    newcomer = client.post(
        "/api/students",
        headers=headers,
        json={"first_name": "New", "last_name": "Comer"},
    ).json()
    assert (
        client.post(
            f"/api/classes/{environment['student_class']['id']}/accounts/"
            f"{newcomer['id']}",
            headers=headers,
        ).status_code
        == 200
    )
    newcomer_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/student-auth/login",
            json={
                "identifier": newcomer["identifier"],
                "password": newcomer["generated_password"],
            },
        ).json()["access_token"]
    }
    late = client.post(
        "/api/quizzes/join",
        headers=newcomer_headers,
        json={"join_code": launched["join_code"]},
    )
    assert late.status_code == 403

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(class_id=None)
        )
        session.commit()
    detached = client.post(
        "/api/quizzes/join",
        headers=student_headers,
        json={"join_code": launched["join_code"]},
    )
    assert detached.status_code == 403


def test_joining_survives_concurrent_session_changes(environment) -> None:
    client = environment["client"]
    student_headers = environment["student_headers"]
    launched = client.post(
        f"/api/quizzes/{environment['quiz']['id']}/launch",
        headers=environment["teacher_headers"],
        json={"class_id": environment["student_class"]["id"]},
    ).json()
    join = {"join_code": launched["join_code"]}

    def set_status(value: str):
        return lambda connection: connection.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status=value)
        )

    with concurrent_writes(
        client, ("UPDATE quiz_sessions SET status", set_status("cancelled"))
    ) as fired:
        assert (
            client.post("/api/quizzes/join", headers=student_headers, json=join)
        ).status_code == 403
    assert fired
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="waiting")
        )
        session.commit()

    student_id = environment["account"]["id"]

    def insert_participant(connection) -> None:
        membership = connection.execute(
            select(Student.id, Student.identifier).where(
                Student.account_id == student_id
            )
        ).one()
        connection.execute(
            QuizParticipant.__table__.insert().values(
                session_id=launched["id"],
                student_id=membership.id,
                student_identifier=membership.identifier,
                violation_count=0,
            )
        )

    with concurrent_writes(
        client, ("INSERT INTO quiz_participants", insert_participant)
    ) as fired:
        duplicate = client.post("/api/quizzes/join", headers=student_headers, json=join)
    assert fired
    assert duplicate.status_code == 403

    still_present = client.post("/api/quizzes/join", headers=student_headers, json=join)
    assert still_present.status_code == 403

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.session_id == launched["id"])
            .values(left_at=datetime.now(UTC))
        )
        session.commit()
    with concurrent_writes(
        client, ("UPDATE quiz_sessions SET status", set_status("finished"))
    ) as fired:
        assert (
            client.post("/api/quizzes/join", headers=student_headers, json=join)
        ).status_code == 403
    assert fired

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="waiting")
        )
        session.commit()
    with concurrent_writes(
        client,
        (
            "UPDATE quiz_participants SET",
            lambda connection: connection.execute(
                update(QuizParticipant)
                .where(QuizParticipant.session_id == launched["id"])
                .values(left_at=None)
            ),
        ),
    ) as fired:
        assert (
            client.post("/api/quizzes/join", headers=student_headers, json=join)
        ).status_code == 403
    assert fired


def test_answers_are_validated_against_the_question(environment) -> None:
    client = environment["client"]
    environment = two_question_quiz(client, environment)
    written = add_question(
        client,
        environment,
        prompt="Explain",
        difficulty="medium",
        answer_mode="written",
        choices=[{"label": "Because", "is_correct": True}],
    )
    quiz = client.post(
        "/api/quizzes",
        headers=environment["teacher_headers"],
        json={
            "title": "Mixed",
            "question_bank_ids": [environment["question"]["question_bank_id"]],
            "easy_question_count": 1,
            "medium_question_count": 1,
            "hard_question_count": 0,
            "same_questions_for_all": True,
        },
    ).json()
    environment = {**environment, "quiz": quiz}
    _, headers, url = started(client, environment)

    last_payload: dict[str, Any] = {}
    for _ in range(2):
        state = client.get(url, headers=headers).json()
        question = state["question"]
        if question["id"] == written["id"]:
            assert (
                client.post(
                    f"{url}/answer", headers=headers, json={"written_answer": "   "}
                ).status_code
                == 422
            )
            last_payload = {"written_answer": "Because"}
            changed_payload = {"written_answer": "Something else"}
        else:
            choice_ids = [choice["id"] for choice in question["choices"]]
            for payload in (
                {"written_answer": "text"},
                {"selected_choice_ids": choice_ids},
                {"selected_choice_ids": [999999]},
            ):
                assert (
                    client.post(f"{url}/answer", headers=headers, json=payload)
                ).status_code == 422
            last_payload = {"selected_choice_ids": [choice_ids[0]]}
            changed_payload = {"selected_choice_ids": [choice_ids[1]]}
        response = client.post(f"{url}/answer", headers=headers, json=last_payload)
        assert response.status_code == 200

    # Every question is answered: a late duplicate must match what was stored.
    last_question = client.get(url, headers=headers).json()
    assert last_question["awaiting_final_submission"] is True
    duplicate = client.post(f"{url}/answer", headers=headers, json=last_payload)
    assert duplicate.status_code == 200
    mismatch = client.post(f"{url}/answer", headers=headers, json=changed_payload)
    assert mismatch.status_code == 409


def test_answering_requires_a_current_question_and_a_student(environment) -> None:
    client = environment["client"]
    launched, headers, url = started(client, environment)

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.session_id == launched["id"])
            .values(current_position=5)
        )
        session.commit()
    beyond = client.post(
        f"{url}/answer",
        headers=headers,
        json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
    )
    assert beyond.status_code == 409
    assert beyond.json()["detail"]["code"] == "QUIZ_NO_CURRENT_QUESTION"

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.session_id == launched["id"])
            .values(current_position=0, student_id=None)
        )
        session.commit()
    orphaned = client.post(
        f"{url}/answer",
        headers=headers,
        json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
    )
    assert orphaned.status_code == 401


def test_an_orphaned_participant_cannot_answer(environment, monkeypatch) -> None:
    client = environment["client"]
    launched, headers, url = started(client, environment)
    from app.routers import student_sessions

    original = student_sessions.authenticated_participant

    def without_student(*args, **kwargs):
        quiz_session, quiz, participant = original(*args, **kwargs)
        participant.student_id = None
        return quiz_session, quiz, participant

    monkeypatch.setattr(student_sessions, "authenticated_participant", without_student)
    response = client.post(
        f"{url}/answer",
        headers=headers,
        json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "QUIZ_STUDENT_REMOVED",
        "message": "L’élève n’existe plus",
    }


def test_inactive_student_accounts_lose_their_participation(environment) -> None:
    client = environment["client"]
    launched, headers, url = started(client, environment)
    with client.app.state.session_factory() as session:
        session.execute(
            update(StudentAccount)
            .where(StudentAccount.id == environment["account"]["id"])
            .values(is_active=False)
        )
        session.commit()
    assert client.get(url, headers=headers).status_code == 401


def test_review_and_navigation_rules(environment) -> None:
    client = environment["client"]
    environment = two_question_quiz(client, environment)
    launched, headers, url = started(client, environment)

    assert client.post(f"{url}/review", headers=headers).status_code == 409
    assert answer_current(client, url, headers).status_code == 200
    assert (
        client.post(f"{url}/navigate", headers=headers, json={"question_number": 2})
    ).status_code == 200
    assert (
        client.post(f"{url}/navigate", headers=headers, json={"question_number": 5})
    ).status_code == 409

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(allow_previous_questions=None)
        )
        session.commit()
    legacy = client.post(
        f"{url}/navigate", headers=headers, json={"question_number": 1}
    )
    assert legacy.status_code == 200

    client.post(f"{url}/navigate", headers=headers, json={"question_number": 2})
    assert answer_current(client, url, headers).status_code == 200
    reviewing = client.post(f"{url}/review", headers=headers)
    assert reviewing.status_code == 200
    assert reviewing.json()["awaiting_final_submission"] is True
    again = client.post(f"{url}/review", headers=headers)
    assert again.status_code == 200

    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="paused", paused_at=datetime.now(UTC))
        )
        session.commit()
    assert client.post(f"{url}/review", headers=headers).status_code == 409
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="in_progress", paused_at=None)
        )
        session.commit()

    submitted = hand_in_quiz(client, launched["join_code"], headers)
    assert submitted["status"] == "finished"
    assert client.post(f"{url}/review", headers=headers).status_code == 200


def test_student_images_require_a_running_session_and_an_image(environment) -> None:
    client = environment["client"]
    launched, headers, url = started(client, environment)
    question_id = environment["question"]["id"]
    assert (
        client.get(f"{url}/questions/{question_id}/image", headers=headers).status_code
        == 404
    )
    with client.app.state.session_factory() as session:
        session.execute(
            update(Question)
            .where(Question.id == question_id)
            .values(image_data=VALID_PNG, image_content_type="image/png")
        )
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="paused", paused_at=datetime.now(UTC))
        )
        session.commit()
    paused = client.get(f"{url}/questions/{question_id}/image", headers=headers)
    assert paused.status_code == 404


def test_teacher_views_tolerate_departed_and_legacy_participants(environment) -> None:
    client = environment["client"]
    teacher_headers = environment["teacher_headers"]
    environment = two_question_quiz(client, environment)
    launched, headers, url = started(client, environment)
    assert answer_current(client, url, headers).status_code == 200

    # The time runs out with one question left unanswered.
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        participant_id = session.scalar(
            select(QuizParticipant.id).where(
                QuizParticipant.session_id == launched["id"]
            )
        )
        session.commit()
    finished = client.get(
        f"/api/quizzes/sessions/{launched['id']}", headers=teacher_headers
    ).json()
    assert finished["status"] == "finished"

    # Answers written by older versions are read defensively.
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizAnswer)
            .where(QuizAnswer.session_id == launched["id"])
            .values(answer_data=json.dumps({"selected_choice_ids": "corrupted"}))
        )
        session.commit()
    answers = client.get(
        f"/api/quizzes/sessions/{launched['id']}/participants/{participant_id}/answers",
        headers=teacher_headers,
    )
    assert answers.status_code == 200
    assert answers.json()[0]["submitted_answers"] == []

    published = client.post(
        f"/api/quizzes/sessions/{launched['id']}/publish-grades",
        headers=teacher_headers,
    )
    assert published.status_code == 200
    history = client.get(
        "/api/quizzes/student/results", headers=environment["student_headers"]
    ).json()
    assert [len(item["answers"]) for item in history] == [2]
    assert [answer["submitted_answers"] for answer in history[0]["answers"]][1] == []

    # The class is gone: draws are found again by the student identifier.
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.session_id == launched["id"])
            .values(student_id=None)
        )
        session.execute(
            update(QuizSessionStudentQuestion)
            .where(QuizSessionStudentQuestion.session_id == launched["id"])
            .values(student_id=None)
        )
        session.execute(
            text("UPDATE quiz_sessions SET class_id = NULL WHERE id = :id"),
            {"id": launched["id"]},
        )
        session.commit()
    detached = client.get(
        f"/api/quizzes/sessions/{launched['id']}/participants/{participant_id}/answers",
        headers=teacher_headers,
    )
    assert detached.status_code == 200
    assert len(detached.json()) == 1
    results = client.get("/api/quizzes/sessions/results", headers=teacher_headers)
    assert results.json()[0]["participants"][0]["id"] == participant_id


def test_a_participant_who_left_before_the_start_is_hidden(environment) -> None:
    client = environment["client"]
    teacher_headers = environment["teacher_headers"]
    environment = two_question_quiz(client, environment)
    classmate = client.post(
        "/api/students",
        headers=teacher_headers,
        json={"first_name": "Class", "last_name": "Mate"},
    ).json()
    client.post(
        f"/api/classes/{environment['student_class']['id']}/accounts/{classmate['id']}",
        headers=teacher_headers,
    )
    classmate_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/student-auth/login",
            json={
                "identifier": classmate["identifier"],
                "password": classmate["generated_password"],
            },
        ).json()["access_token"]
    }
    launched, headers = launch_and_join(client, environment)
    joined = client.post(
        "/api/quizzes/join",
        headers=classmate_headers,
        json={"join_code": launched["join_code"]},
    ).json()
    leaver_headers = {"X-Quiz-Token": joined["participant_token"]}
    url = f"/api/quizzes/student/sessions/{launched['join_code']}"
    assert client.post(f"{url}/leave", headers=leaver_headers).status_code == 204
    client.post(
        f"/api/quizzes/sessions/{launched['id']}/start", headers=teacher_headers
    )
    for _ in range(2):
        assert answer_current(client, url, headers).status_code == 200
    hand_in_quiz(client, launched["join_code"], headers)

    with client.app.state.session_factory() as session:
        leaver_id = session.scalar(
            select(QuizParticipant.id).where(
                QuizParticipant.session_id == launched["id"],
                QuizParticipant.left_at.is_not(None),
            )
        )
    results = client.get("/api/quizzes/sessions/results", headers=teacher_headers)
    assert leaver_id not in [p["id"] for p in results.json()[0]["participants"]]
    hidden = client.get(
        f"/api/quizzes/sessions/{launched['id']}/participants/{leaver_id}/answers",
        headers=teacher_headers,
    )
    assert hidden.status_code == 404


def test_students_without_a_class_have_no_history_or_training(environment) -> None:
    client = environment["client"]
    loner = client.post(
        "/api/students",
        headers=environment["teacher_headers"],
        json={"first_name": "Lone", "last_name": "Wolf"},
    ).json()
    loner_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/student-auth/login",
            json={
                "identifier": loner["identifier"],
                "password": loner["generated_password"],
            },
        ).json()["access_token"]
    }
    bank_id = environment["question"]["question_bank_id"]
    assert (
        client.get("/api/quizzes/student/results", headers=loner_headers).json() == []
    )
    assert (
        client.get(
            f"/api/quizzes/training/{bank_id}/history", headers=loner_headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/quizzes/training/{bank_id}/start", headers=loner_headers
        ).status_code
        == 409
    )


def test_training_feedback_and_results_cover_written_and_empty_banks(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep the drawn order stable: the written question comes first.
    monkeypatch.setattr(quizzes.randomizer, "shuffle", lambda items: None)
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_headers = environment["student_headers"]
    class_id = environment["student_class"]["id"]

    written_bank = client.post(
        "/api/question-banks",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Written training"},
    ).json()
    written_environment = {
        **environment,
        "question": {**environment["question"], "question_bank_id": written_bank["id"]},
    }
    add_question(
        client,
        written_environment,
        prompt="Explain",
        answer_mode="written",
        choices=[{"label": "Because", "is_correct": True}],
    )
    add_question(client, written_environment)
    empty_bank = client.post(
        "/api/question-banks",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Empty training"},
    ).json()
    assert (
        client.put(
            f"/api/quizzes/training/classes/{class_id}/question-banks",
            headers=headers,
            json={"question_bank_ids": [written_bank["id"], empty_bank["id"]]},
        ).status_code
        == 200
    )

    assert (
        client.post(
            f"/api/quizzes/training/{empty_bank['id']}/start", headers=student_headers
        ).status_code
        == 409
    )
    training = client.post(
        f"/api/quizzes/training/{written_bank['id']}/start", headers=student_headers
    )
    assert training.status_code == 201
    token_headers = {"X-Quiz-Token": training.json()["participant_token"]}
    url = f"/api/quizzes/student/sessions/{training.json()['join_code']}"
    question = client.get(url, headers=token_headers).json()["question"]
    assert question["answer_mode"] == "written"
    answered = client.post(
        f"{url}/answer", headers=token_headers, json={"written_answer": "Because"}
    )
    assert answered.status_code == 200
    assert answered.json()["training_feedback"]["requires_manual_review"] is True
    # Leaving the second question unanswered still produces a result.
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.join_code == training.json()["join_code"])
            .values(started_at=datetime.now(UTC) - timedelta(days=1))
        )
        session.commit()
    finished = client.get(url, headers=token_headers).json()
    assert finished["status"] == "finished"
    assert finished["potential_score"] == 0
    assert finished["potential_maximum_score"] == 1
    assert finished["pending_manual_review_count"] == 1
