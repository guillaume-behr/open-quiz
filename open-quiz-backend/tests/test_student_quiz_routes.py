"""Student exams and trainings: joining, answering, review and leaving."""

import json
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from fastapi import status
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select, text, update

from app.database import postgres_url
from app.models import (
    Question,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
)
from app.schemas import (
    StudentQuizAnswer,
)
from app.services import question_draws

from support import (
    VALID_PNG,
    assert_student_exam_payload_hides_answers,
    complete_first_login,
    concurrent_writes,
    correct_choice_id,
    database_connection,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    login_admin,
    make_client,
    settings_for,
    wrong_choice_id,
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
    monkeypatch.setattr(question_draws.randomizer, "shuffle", lambda items: None)
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


def test_quiz_join_requires_an_authenticated_student(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "quiz-auth.db")) as client:
        missing_session = client.post(
            "/api/quizzes/join",
            json={"join_code": "ABC123"},
        )
        assert missing_session.status_code == 401
        invalid_session = client.post(
            "/api/quizzes/join",
            headers={"Authorization": "Bearer invalid-token"},
            json={"join_code": "ABC123"},
        )
        assert invalid_session.status_code == 401


def test_invalid_participant_tokens_share_a_bounded_session_rate_limit(
    tmp_path: Path,
) -> None:
    settings = settings_for(
        tmp_path / "participant-auth-rate-limit.db",
        quiz_join_attempts=5,
        quiz_rate_window_seconds=60,
    )
    endpoint = "/api/quizzes/student/sessions/ABC123"
    with make_client(settings) as client:
        for _ in range(5):
            response = client.get(
                endpoint,
                headers={"X-Quiz-Token": "invalid-token"},
            )
            assert response.status_code == 401

        limited = client.get(
            endpoint,
            headers={"X-Quiz-Token": "invalid-token"},
        )
        assert limited.status_code == 429

        different_token = client.get(
            endpoint,
            headers={"X-Quiz-Token": "another-invalid-token"},
        )
        assert different_token.status_code == 429


def test_training_quiz_is_self_started_ungraded_and_returns_feedback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "training-quiz.db"
    with make_client(settings_for(database_path)) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "training.teacher",
                    "display_name": "Training Teacher",
                    "password": "a-secure-training-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "training.teacher", "a-secure-training-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "3e A", "grade_level": "3e"},
        ).json()
        account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Training",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "3e", "chapter": "Training"},
        ).json()
        question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Two plus two?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {"label": "Four", "is_correct": True},
                            {"label": "Five", "is_correct": False},
                        ],
                    }
                )
            },
        ).json()
        correct_choice_id = next(
            choice["id"] for choice in question["choices"] if choice["is_correct"]
        )
        manual_training = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "mode": "training",
                "title": "Mental arithmetic",
                "question_bank_ids": [bank["id"]],
                "duration_seconds": 60,
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert manual_training.status_code == 422
        training_banks = client.put(
            f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
            headers=teacher_headers,
            json={"question_bank_ids": [bank["id"]]},
        )
        assert training_banks.status_code == 200
        assert training_banks.json()[0]["id"] == bank["id"]
        other_level_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Wrong level"},
        ).json()
        assert (
            client.put(
                f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
                headers=teacher_headers,
                json={"question_bank_ids": [other_level_bank["id"]]},
            ).status_code
            == 422
        )
        assert client.get("/api/quizzes", headers=teacher_headers).json() == []
        assert (
            client.get(
                f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
                headers=teacher_headers,
            ).json()[0]["id"]
            == bank["id"]
        )
        other_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "3e B", "grade_level": "3e"},
        ).json()
        assert (
            client.get(
                f"/api/quizzes/training/classes/{other_class['id']}/question-banks",
                headers=teacher_headers,
            ).json()
            == []
        )
        mutable_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "3e", "chapter": "Changing level"},
        ).json()
        assert (
            client.put(
                f"/api/quizzes/training/classes/{student_class['id']}/question-banks",
                headers=teacher_headers,
                json={"question_bank_ids": [bank["id"], mutable_bank["id"]]},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/question-banks/{mutable_bank['id']}/update",
                headers=teacher_headers,
                json={"grade_level": "4e", "chapter": "Changing level"},
            ).status_code
            == 200
        )
        with database_connection(database_path) as database:
            assert (
                database.execute(
                    "SELECT COUNT(*) FROM class_training_question_banks "
                    "WHERE question_bank_id = %s",
                    (mutable_bank["id"],),
                ).fetchone()[0]
                == 0
            )
        other_class_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Other",
                "last_name": "Class Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{other_class['id']}/accounts/{other_class_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        other_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "other.class.student",
                "password": other_class_account["generated_password"],
            },
        ).json()
        other_student_headers = {
            "Authorization": f"Bearer {other_login['access_token']}"
        }
        assert (
            client.get("/api/quizzes/training", headers=other_student_headers).json()
            == []
        )
        assert (
            client.post(
                f"/api/quizzes/training/{bank['id']}/start",
                headers=other_student_headers,
            ).status_code
            == 404
        )

        login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "training.student",
                "password": account["generated_password"],
            },
        ).json()
        student_headers = {"Authorization": f"Bearer {login['access_token']}"}
        available = client.get("/api/quizzes/training", headers=student_headers)
        assert available.status_code == 200
        assert available.json()[0]["chapter"] == "Training"
        started = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert started.status_code == 201
        assert started.json()["status"] == "in_progress"
        assert started.json()["quiz_title"] == "Training"
        redrawn = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert redrawn.status_code == 201
        assert redrawn.json()["join_code"] != started.json()["join_code"]

        other_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Other",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        other_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": other_account["identifier"],
                "password": other_account["generated_password"],
            },
        )
        assert other_login.status_code == 200
        other_training = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers={"Authorization": f"Bearer {other_login.json()['access_token']}"},
        )
        assert other_training.status_code == 201
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        with database_connection(database_path) as database:
            assert (
                database.execute(
                    "SELECT COUNT(*) FROM quiz_sessions WHERE join_code = %s",
                    (other_training.json()["join_code"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                database.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM quiz_session_questions"
                ).fetchone()[0]
                == 1
            )
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        transferred_training = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers={"Authorization": f"Bearer {other_login.json()['access_token']}"},
        )
        assert transferred_training.status_code == 201
        assert (
            client.post(
                f"/api/classes/{other_class['id']}/accounts/{other_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        with database_connection(database_path) as database:
            assert (
                database.execute(
                    "SELECT COUNT(*) FROM quiz_sessions WHERE join_code = %s",
                    (transferred_training.json()["join_code"],),
                ).fetchone()[0]
                == 0
            )
        replaced_attempt = client.post(
            f"/api/quizzes/student/sessions/{started.json()['join_code']}/answer",
            headers={"X-Quiz-Token": started.json()["participant_token"]},
            json={"selected_choice_ids": [correct_choice_id]},
        )
        assert replaced_attempt.status_code == 401
        updated_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Two plus two, exactly?",
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {
                                "id": choice["id"],
                                "label": choice["label"],
                                "is_correct": choice["is_correct"],
                            }
                            for choice in question["choices"]
                        ],
                    }
                )
            },
        )
        assert updated_question.status_code == 200
        redrawn_answered = client.post(
            f"/api/quizzes/student/sessions/{redrawn.json()['join_code']}/answer",
            headers={"X-Quiz-Token": redrawn.json()["participant_token"]},
            json={"selected_choice_ids": [correct_choice_id]},
        )
        assert redrawn_answered.status_code == 200
        assert redrawn_answered.json()["status"] == "finished"
        assert redrawn_answered.json()["training_feedback"] == {
            "question_id": question["id"],
            "is_correct": True,
            "correct_choice_ids": [correct_choice_id],
            "expected_answer": None,
            "submitted_answer": None,
            "requires_manual_review": False,
        }
        assert (
            client.get("/api/quizzes/sessions/results", headers=teacher_headers).json()
            == []
        )
        class_after_training = client.get(
            "/api/classes", headers=teacher_headers
        ).json()[0]
        assert class_after_training["completed_quiz_count"] == 0
        assert class_after_training["latest_quiz_title"] is None
        with database_connection(database_path) as database:
            assert (
                database.execute("SELECT COUNT(*) FROM quiz_answers").fetchone()[0] == 1
            )
            assert (
                database.execute("SELECT COUNT(*) FROM quiz_sessions").fetchone()[0]
                == 1
            )
        history = client.get(
            f"/api/quizzes/training/{bank['id']}/history",
            headers=student_headers,
        )
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["score"] == 1
        assert history.json()[0]["maximum_score"] == 1

        second_question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Three plus three?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "choices": [
                            {"label": "Six", "is_correct": True},
                            {"label": "Seven", "is_correct": False},
                        ],
                    }
                )
            },
        )
        assert second_question.status_code == 201
        disposable_training = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert disposable_training.status_code == 201
        drawn_question_id = disposable_training.json()["question"]["id"]
        assert (
            client.delete(
                f"/api/question-banks/questions/{drawn_question_id}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        discarded_state = client.get(
            f"/api/quizzes/student/sessions/{disposable_training.json()['join_code']}",
            headers={"X-Quiz-Token": disposable_training.json()["participant_token"]},
        )
        assert discarded_state.status_code == 401
        replacement_question = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Four plus four?",
                        "points": 7.5,
                        "difficulty": "easy",
                        "answer_mode": "single",
                        "choices": [
                            {"label": "Eight", "is_correct": True},
                            {"label": "Nine", "is_correct": False},
                        ],
                    }
                )
            },
        )
        assert replacement_question.status_code == 201
        pre_exam_training = client.post(
            f"/api/quizzes/training/{bank['id']}/start",
            headers=student_headers,
        )
        assert pre_exam_training.status_code == 201
        exam = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Scored arithmetic",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert exam.status_code == 201
        launched_exam = client.post(
            f"/api/quizzes/{exam.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched_exam.status_code == 201
        assert (
            client.get(
                "/api/quizzes/student/sessions/"
                f"{pre_exam_training.json()['join_code']}",
                headers={"X-Quiz-Token": pre_exam_training.json()["participant_token"]},
            ).status_code
            == 401
        )
        assert client.get("/api/quizzes/training", headers=student_headers).json() == []
        assert (
            client.post(
                f"/api/quizzes/training/{bank['id']}/start",
                headers=student_headers,
            ).status_code
            == 404
        )
        joined_exam = client.post(
            "/api/quizzes/join",
            headers=student_headers,
            json={"join_code": launched_exam.json()["join_code"]},
        )
        assert joined_exam.status_code == 201
        engine = create_engine(postgres_url(settings_for(database_path).database_url))
        try:
            assert "points" not in {
                column["name"] for column in inspect(engine).get_columns("questions")
            }
            assert "points" not in {
                column["name"]
                for column in inspect(engine).get_columns("quiz_session_questions")
            }
        finally:
            engine.dispose()
        with database_connection(database_path) as database:
            common_question_ids = {
                row[0]
                for row in database.execute(
                    "SELECT question_id FROM quiz_session_questions "
                    "WHERE session_id = %s",
                    (launched_exam.json()["id"],),
                )
            }
            student_question_ids = [
                row[0]
                for row in database.execute(
                    "SELECT question_id FROM quiz_session_student_questions "
                    "WHERE session_id = %s AND student_identifier = %s ORDER BY position",
                    (launched_exam.json()["id"], account["identifier"]),
                )
            ]
        assert common_question_ids == set()
        assert len(student_question_ids) == 2
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched_exam.json()['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        student_exam_state = client.get(
            f"/api/quizzes/student/sessions/{launched_exam.json()['join_code']}",
            headers={"X-Quiz-Token": joined_exam.json()["participant_token"]},
        )
        assert student_exam_state.status_code == 200
        assert student_exam_state.json()["question"]["id"] == student_question_ids[0]


def test_written_answers_have_an_application_level_size_limit() -> None:
    assert StudentQuizAnswer(written_answer="a" * 20000).written_answer
    with pytest.raises(ValidationError):
        StudentQuizAnswer(written_answer="a" * 20001)


def test_join_and_start_race_never_strands_a_participant(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "join-start-race.db")) as client:
        environment = exam_environment(client)
        launched = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/launch",
            headers=environment["teacher_headers"],
            json={"class_id": environment["student_class"]["id"]},
        ).json()
        barrier = Barrier(2)
        responses: dict[str, Any] = {}

        def join() -> int:
            barrier.wait()
            response = client.post(
                "/api/quizzes/join",
                headers=environment["student_headers"],
                json={"join_code": launched["join_code"]},
            )
            responses["join"] = response
            return response.status_code

        def start() -> int:
            barrier.wait()
            response = client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            )
            responses["start"] = response
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            join_status = pool.submit(join)
            start_status = pool.submit(start)
            assert join_status.result() == status.HTTP_201_CREATED
            assert start_status.result() in {
                status.HTTP_200_OK,
                status.HTTP_409_CONFLICT,
            }

        joined = responses["join"].json()
        state = client.get(
            f"/api/quizzes/student/sessions/{launched['join_code']}",
            headers={"X-Quiz-Token": joined["participant_token"]},
        )
        assert state.status_code == status.HTTP_200_OK
        if responses["start"].status_code == status.HTTP_200_OK:
            assert state.json()["status"] == "in_progress"
            assert state.json()["question"] is not None
        else:
            assert state.json()["status"] == "waiting"
            assert state.json()["question"] is None


def test_answer_review_precedes_the_final_submission(tmp_path: Path) -> None:
    """A reviewed paper is only handed in once the student confirms it."""
    with make_client(settings_for(tmp_path / "answer-review.db")) as client:
        environment = exam_environment(client)
        quiz = environment["quiz"]
        assert quiz["allow_answer_review"] is True
        updated = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": quiz["title"],
                "question_bank_ids": [bank["id"] for bank in quiz["question_banks"]],
                "allow_previous_questions": True,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["allow_answer_review"] is True
        environment["quiz"] = updated.json()

        launched, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        student_url = f"/api/quizzes/student/sessions/{launched['join_code']}"
        session_url = f"/api/quizzes/sessions/{launched['id']}"

        answered = client.post(
            f"{student_url}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [wrong_choice_id(environment["question"])]},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "in_progress"
        assert answered.json()["allow_answer_review"] is True
        assert answered.json()["awaiting_final_submission"] is True
        assert answered.json()["question"] is None
        assert answered.json()["answer_summaries"] == [
            {
                "question_number": 1,
                "question_id": environment["question"]["id"],
                "prompt": environment["question"]["prompt"],
                "answer_mode": "single",
                "submitted_answers": ["Three"],
            }
        ]
        assert_student_exam_payload_hides_answers(answered.json())

        # The teacher sees the answer but not a finished student.
        participant = client.get(
            session_url, headers=environment["teacher_headers"]
        ).json()["participants"][0]
        assert participant["answered_count"] == 1
        assert participant["has_finished"] is False

        # Reviewing may lead back to a question, and back to the summary.
        back = client.post(
            f"{student_url}/navigate",
            headers=participant_headers,
            json={"question_number": 1},
        )
        assert back.status_code == 200
        assert back.json()["question_number"] == 1
        assert back.json()["awaiting_final_submission"] is False
        corrected = client.post(
            f"{student_url}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert corrected.status_code == 200
        assert corrected.json()["answer_summaries"][0]["submitted_answers"] == ["Two"]
        assert (
            client.post(
                f"{student_url}/navigate",
                headers=participant_headers,
                json={"question_number": 1},
            ).status_code
            == 200
        )
        review = client.post(f"{student_url}/review", headers=participant_headers)
        assert review.status_code == 200
        assert review.json()["awaiting_final_submission"] is True
        assert review.json()["question"] is None

        handed_in = client.post(f"{student_url}/submit", headers=participant_headers)
        assert handed_in.status_code == 200
        assert handed_in.json()["status"] == "finished"
        assert handed_in.json()["awaiting_final_submission"] is False
        assert handed_in.json()["answer_summaries"] == []
        # Confirming twice must not fail a student whose paper is already in.
        assert (
            client.post(
                f"{student_url}/submit", headers=participant_headers
            ).status_code
            == 200
        )

        finished = client.get(
            session_url, headers=environment["teacher_headers"]
        ).json()
        assert finished["status"] == "finished"
        assert finished["participants"][0]["has_finished"] is True
        assert finished["participants"][0]["score"] == 2


def test_quiz_without_answer_review_finishes_on_the_last_answer(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "no-answer-review.db")) as client:
        environment = exam_environment(client)
        quiz = environment["quiz"]
        updated = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": quiz["title"],
                "question_bank_ids": [bank["id"] for bank in quiz["question_banks"]],
                "allow_answer_review": False,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["allow_answer_review"] is False
        environment["quiz"] = updated.json()

        launched, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        student_url = f"/api/quizzes/student/sessions/{launched['join_code']}"
        answered = client.post(
            f"{student_url}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "finished"
        assert answered.json()["allow_answer_review"] is False
        assert answered.json()["awaiting_final_submission"] is False
        assert answered.json()["answer_summaries"] == []
        assert (
            client.post(
                f"{student_url}/submit", headers=participant_headers
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"{student_url}/review", headers=participant_headers
            ).status_code
            == 409
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{launched['id']}",
                headers=environment["teacher_headers"],
            ).json()["participants"][0]["has_finished"]
            is True
        )


def test_student_password_reset_revokes_an_active_quiz_capability(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "participant-revocation.db")) as client:
        environment = exam_environment(client)
        launched, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        account = environment["account"]
        replacement_password = "Replacement-42"
        changed = client.post(
            f"/api/students/{account['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "identifier": account["identifier"],
                "display_name": account["display_name"],
                "password": replacement_password,
                "is_active": True,
            },
        )
        assert changed.status_code == 200

        endpoint = f"/api/quizzes/student/sessions/{launched['join_code']}"
        assert client.get(endpoint, headers=participant_headers).status_code == 401
        assert (
            client.get(
                "/api/student-auth/me",
                headers=environment["student_headers"],
            ).status_code
            == 401
        )

        new_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": account["identifier"],
                "password": replacement_password,
            },
        )
        assert new_login.status_code == 200
        rejoined = client.post(
            "/api/quizzes/join",
            headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
            json={"join_code": launched["join_code"]},
        )
        assert rejoined.status_code == 201
        assert rejoined.json()["question"] is not None


def test_completed_student_waits_for_classmates_without_a_blank_state(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "completed-student-state.db")) as client:
        environment = exam_environment(client)
        other_account = client.post(
            "/api/students",
            headers=environment["teacher_headers"],
            json={"first_name": "Other", "last_name": "Student"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{environment['student_class']['id']}"
                f"/accounts/{other_account['id']}",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        other_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": other_account["identifier"],
                "password": other_account["generated_password"],
            },
        )
        assert other_login.status_code == 200
        other_student_headers = {
            "Authorization": f"Bearer {other_login.json()['access_token']}"
        }

        launched, first_participant_headers = launch_and_join(client, environment)
        other_join = client.post(
            "/api/quizzes/join",
            headers=other_student_headers,
            json={"join_code": launched["join_code"]},
        )
        assert other_join.status_code == 201
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        completed = client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
            headers=first_participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "in_progress"
        assert completed.json()["question"] is None
        assert completed.json()["has_answered"] is True
        violation_after_completion = client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/violation",
            headers=first_participant_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert violation_after_completion.status_code == 204
        teacher_state = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        ).json()
        completed_participant = next(
            item
            for item in teacher_state["participants"]
            if item["student_identifier"] == environment["account"]["identifier"]
        )
        assert completed_participant["violation_count"] == 0


def test_concurrent_answer_submissions_keep_a_single_answer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent-answers.db"
    with make_client(settings_for(database_path)) as client:
        environment = exam_environment(client)
        quiz_session, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        barrier = Barrier(4)
        answer_url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer"
        payload = {"selected_choice_ids": [correct_choice_id(environment["question"])]}

        def submit() -> int:
            barrier.wait()
            return client.post(
                answer_url,
                headers=participant_headers,
                json=payload,
            ).status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = [
                future.result() for future in [pool.submit(submit) for _ in range(4)]
            ]

        assert statuses == [200, 200, 200, 200]
        with database_connection(database_path) as connection:
            answer_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_answers WHERE session_id = %s",
                (quiz_session["id"],),
            ).fetchone()[0]
        assert answer_count == 1


def test_student_images_are_scoped_to_the_current_question(tmp_path: Path) -> None:
    """Private images must never leak past the question a student is on."""
    with make_client(settings_for(tmp_path / "student-images.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "image.teacher",
                    "display_name": "Image Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "image.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "5e A", "grade_level": "5e"},
        ).json()
        account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Iris", "last_name": "Petit"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "5e", "chapter": "Images"},
        ).json()
        encoded_image = {
            "content_type": "image/png",
            "data_base64": b64encode(VALID_PNG).decode(),
        }
        for index in range(2):
            created = client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": f"Question imagée {index}",
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {
                                    "label": "Correct",
                                    "is_correct": True,
                                    "image": encoded_image,
                                },
                                {"label": "Faux", "is_correct": False},
                            ],
                        }
                    )
                },
                files={"image": ("question.png", VALID_PNG, "image/png")},
            )
            assert created.status_code == 201

        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Quiz avec images",
                "question_bank_ids": [bank["id"]],
                "same_questions_for_all": True,
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        ).json()
        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        ).json()

        student_token = client.post(
            "/api/student-auth/login",
            json={
                "identifier": account["identifier"],
                "password": account["generated_password"],
            },
        ).json()["access_token"]
        student_headers = {"Authorization": f"Bearer {student_token}"}
        joined = client.post(
            "/api/quizzes/join",
            headers=student_headers,
            json={"join_code": launched["join_code"]},
        )
        assert joined.status_code == 201
        quiz_token = joined.json()["participant_token"]
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        join_code = launched["join_code"]
        state = client.get(
            f"/api/quizzes/student/sessions/{join_code}",
            headers={"X-Quiz-Token": quiz_token},
        ).json()
        current_question_id = state["question"]["id"]
        current_choice_ids = {choice["id"] for choice in state["question"]["choices"]}

        all_questions = client.get(
            f"/api/question-banks/{bank['id']}/questions", headers=teacher_headers
        ).json()
        other_question = next(
            question
            for question in all_questions
            if question["id"] != current_question_id
        )
        other_choice_id = next(
            choice["id"]
            for choice in other_question["choices"]
            if choice["id"] not in current_choice_ids and choice["has_image"]
        )

        image_url = (
            f"/api/quizzes/student/sessions/{join_code}"
            f"/questions/{current_question_id}/image"
        )
        served = client.get(image_url, headers={"X-Quiz-Token": quiz_token})
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/png"
        assert served.content.startswith(b"\x89PNG")

        choice_with_image = next(
            choice["id"]
            for choice in state["question"]["choices"]
            if choice["has_image"]
        )
        served_choice = client.get(
            f"/api/quizzes/student/sessions/{join_code}"
            f"/choices/{choice_with_image}/image",
            headers={"X-Quiz-Token": quiz_token},
        )
        assert served_choice.status_code == 200

        # A question the student has not reached must stay private.
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{join_code}"
                f"/questions/{other_question['id']}/image",
                headers={"X-Quiz-Token": quiz_token},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{join_code}"
                f"/choices/{other_choice_id}/image",
                headers={"X-Quiz-Token": quiz_token},
            ).status_code
            == 404
        )
        # The participant token is required, and a forged one is rejected.
        assert client.get(image_url).status_code == 401
        assert (
            client.get(
                image_url, headers={"X-Quiz-Token": "forged-participant-token"}
            ).status_code
            == 401
        )


def test_departed_participant_does_not_hold_the_session_open(tmp_path: Path) -> None:
    """A student who leaves must not keep a finished exam in progress.

    Their position is kept so a rejoin resumes where they stopped, but the
    teacher no longer sees them, so counting them would leave the session
    running until the timer expires with nobody left to answer.
    """
    with make_client(settings_for(tmp_path / "departed-participant.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "leave.teacher",
                    "display_name": "Leave Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "leave.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "4e B", "grade_level": "4e"},
        ).json()
        accounts = []
        for first_name in ("Alpha", "Beta"):
            account = client.post(
                "/api/students",
                headers=teacher_headers,
                json={"first_name": first_name, "last_name": "Partant"},
            ).json()
            assert (
                client.post(
                    f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                    headers=teacher_headers,
                ).status_code
                == 200
            )
            accounts.append(account)

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Départ"},
        ).json()
        assert (
            client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": "Seule question",
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Ok", "is_correct": True, "points": 1},
                                {"label": "No", "is_correct": False},
                            ],
                        }
                    )
                },
            ).status_code
            == 201
        )
        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Quiz avec départ",
                "question_bank_ids": [bank["id"]],
                "same_questions_for_all": True,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        ).json()
        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        ).json()

        quiz_tokens = []
        for account in accounts:
            student_token = client.post(
                "/api/student-auth/login",
                json={
                    "identifier": account["identifier"],
                    "password": account["generated_password"],
                },
            ).json()["access_token"]
            joined = client.post(
                "/api/quizzes/join",
                headers={"Authorization": f"Bearer {student_token}"},
                json={"join_code": launched["join_code"]},
            )
            assert joined.status_code == 201
            quiz_tokens.append(joined.json()["participant_token"])
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        join_code = launched["join_code"]
        assert (
            client.post(
                f"/api/quizzes/student/sessions/{join_code}/leave",
                headers={"X-Quiz-Token": quiz_tokens[0]},
            ).status_code
            == 204
        )
        # The teacher no longer counts the student who left.
        in_progress = client.get(
            f"/api/quizzes/sessions/{launched['id']}", headers=teacher_headers
        ).json()
        assert in_progress["participant_count"] == 1

        state = client.get(
            f"/api/quizzes/student/sessions/{join_code}",
            headers={"X-Quiz-Token": quiz_tokens[1]},
        ).json()
        answered = client.post(
            f"/api/quizzes/student/sessions/{join_code}/answer",
            headers={"X-Quiz-Token": quiz_tokens[1]},
            json={
                "selected_choice_ids": [state["question"]["choices"][0]["id"]],
            },
        )
        assert answered.status_code == 200
        hand_in_quiz(client, join_code, {"X-Quiz-Token": quiz_tokens[1]})

        finished = client.get(
            f"/api/quizzes/sessions/{launched['id']}", headers=teacher_headers
        ).json()
        assert finished["status"] == "finished"
        # Results keep everyone who took part, including the student who left.
        assert finished["participant_count"] == 2


def test_last_participant_leaving_finishes_the_session(tmp_path: Path) -> None:
    """Leaving must finish a session whose remaining students are all done.

    The answer endpoint already ends a session once nobody is left to answer,
    but a student can just as easily finish first and have the last active
    classmate leave afterwards. Without the same check there, the exam stays
    in progress with nobody able to advance it until the timer expires.
    """
    with make_client(settings_for(tmp_path / "last-leaver.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "leaver.teacher",
                    "display_name": "Leaver Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "leaver.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "4e C", "grade_level": "4e"},
        ).json()
        accounts = []
        for first_name in ("Gamma", "Delta"):
            account = client.post(
                "/api/students",
                headers=teacher_headers,
                json={"first_name": first_name, "last_name": "Sortant"},
            ).json()
            assert (
                client.post(
                    f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                    headers=teacher_headers,
                ).status_code
                == 200
            )
            accounts.append(account)

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Sortie"},
        ).json()
        assert (
            client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": "Seule question",
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Ok", "is_correct": True, "points": 1},
                                {"label": "No", "is_correct": False},
                            ],
                        }
                    )
                },
            ).status_code
            == 201
        )
        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Quiz avec sortie finale",
                "question_bank_ids": [bank["id"]],
                "same_questions_for_all": True,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        ).json()
        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        ).json()

        quiz_tokens = []
        for account in accounts:
            student_token = client.post(
                "/api/student-auth/login",
                json={
                    "identifier": account["identifier"],
                    "password": account["generated_password"],
                },
            ).json()["access_token"]
            joined = client.post(
                "/api/quizzes/join",
                headers={"Authorization": f"Bearer {student_token}"},
                json={"join_code": launched["join_code"]},
            )
            assert joined.status_code == 201
            quiz_tokens.append(joined.json()["participant_token"])
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        join_code = launched["join_code"]
        # The first student answers everything and is done.
        state = client.get(
            f"/api/quizzes/student/sessions/{join_code}",
            headers={"X-Quiz-Token": quiz_tokens[0]},
        ).json()
        assert (
            client.post(
                f"/api/quizzes/student/sessions/{join_code}/answer",
                headers={"X-Quiz-Token": quiz_tokens[0]},
                json={
                    "selected_choice_ids": [state["question"]["choices"][0]["id"]],
                },
            ).status_code
            == 200
        )
        hand_in_quiz(client, join_code, {"X-Quiz-Token": quiz_tokens[0]})
        # The session is still running for the classmate who has not answered.
        assert (
            client.get(
                f"/api/quizzes/sessions/{launched['id']}", headers=teacher_headers
            ).json()["status"]
            == "in_progress"
        )

        # That classmate leaves instead of answering: nobody can advance the
        # session any more, so it must finish now.
        assert (
            client.post(
                f"/api/quizzes/student/sessions/{join_code}/leave",
                headers={"X-Quiz-Token": quiz_tokens[1]},
            ).status_code
            == 204
        )
        finished = client.get(
            f"/api/quizzes/sessions/{launched['id']}", headers=teacher_headers
        ).json()
        assert finished["status"] == "finished"
        # The answered question is graded rather than left pending.
        assert finished["participants"][0]["score"] == 1


def test_leaving_without_answering_keeps_the_session_rejoinable(
    tmp_path: Path,
) -> None:
    """An abandoned session must stay open so its students can come back.

    Finishing when the last participant leaves is only right once someone has
    answered. With no answer there is nothing to grade, and finishing would
    lock out the student who left by mistake and wants to rejoin.
    """
    with make_client(settings_for(tmp_path / "abandoned.db")) as client:
        environment = exam_environment(client)
        launched, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )
        join_code = launched["join_code"]
        assert (
            client.post(
                f"/api/quizzes/student/sessions/{join_code}/leave",
                headers=participant_headers,
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{launched['id']}",
                headers=environment["teacher_headers"],
            ).json()["status"]
            == "in_progress"
        )
        # The student can still come back and take the exam.
        rejoined = client.post(
            "/api/quizzes/join",
            headers=environment["student_headers"],
            json={"join_code": join_code},
        )
        assert rejoined.status_code == 201
