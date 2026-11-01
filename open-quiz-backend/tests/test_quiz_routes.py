"""Teacher quiz management: launches, draws, scores, results and join codes."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from fastapi import HTTPException, status
from sqlalchemy import event, select, update

from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionBank,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    QuizSessionStudentQuestion,
    Student,
    StudentClass,
    TrainingQuizProfile,
    User,
)
from app.routers.quizzes import (
    generate_join_code,
)
from app.services.grading import (
    participant_maximum_scores,
    question_maximum_scores,
    selected_choice_score,
)
from app.services.results import (
    safe_spreadsheet_cell,
)
from main import create_app

from support import (
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
    makeup_refusal = client.delete(
        f"/api/quizzes/{used_by_makeup['id']}", headers=headers
    )
    assert makeup_refusal.status_code == 409
    assert makeup_refusal.json()["detail"]["code"] == "QUIZ_USED_BY_MAKEUP"

    finished_exam(client, environment)
    results_refusal = client.delete(
        f"/api/quizzes/{environment['quiz']['id']}", headers=headers
    )
    assert results_refusal.status_code == 409
    assert results_refusal.json()["detail"]["code"] == "QUIZ_HAS_RESULTS"


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
    with_answers = client.post(f"{session_url}/cancel", headers=headers)
    assert with_answers.status_code == 409
    assert with_answers.json()["detail"]["code"] == "QUIZ_SESSION_HAS_ANSWERS"

    hand_in_quiz(client, launched["join_code"], participant_headers)
    paused = client.post(f"{session_url}/pause", headers=headers)
    assert paused.status_code == 409
    assert paused.json()["detail"]["code"] == "QUIZ_SESSION_NOT_RUNNING"
    cancelled = client.post(f"{session_url}/cancel", headers=headers)
    assert cancelled.status_code == 409
    assert cancelled.json()["detail"]["code"] == "QUIZ_SESSION_NOT_CANCELLABLE"


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
    assert too_high.json()["detail"]["code"] == "GRADE_ABOVE_MAXIMUM"


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


@pytest.mark.parametrize(
    "value",
    [
        '=HYPERLINK("https://attacker.example")',
        "+SUM(1, 1)",
        "-1+2",
        "@SUM(1, 1)",
        "\t=1+1",
        "\r=1+1",
        "  =1+1",
    ],
)
def test_csv_cells_neutralize_spreadsheet_formulas(value: str) -> None:
    assert safe_spreadsheet_cell(value) == f"'{value}"


def test_quiz_launches_when_question_points_overshoot_the_target(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "point-overshoot.db")) as client:
        admin_headers = login_admin(client)
        teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "overshoot.teacher",
                "display_name": "Overshoot Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client, "overshoot.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "6e C", "grade_level": "6e"},
        ).json()
        student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Lucas", "last_name": "Durand"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{student['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "6e", "chapter": "Overshoot"},
        ).json()
        for index in range(2):
            question = client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": f"Overshoot question {index}",
                            "points": 10,
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Correct", "is_correct": True},
                                {"label": "Wrong", "is_correct": False},
                            ],
                        }
                    )
                },
            )
            assert question.status_code == 201

        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Points trop élevés",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert quiz.status_code == 201

        launched = client.post(
            f"/api/quizzes/{quiz.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201


def test_quiz_launches_when_question_points_cannot_reach_the_target(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "point-fallback.db")) as client:
        admin_headers = login_admin(client)
        teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "fallback.teacher",
                "display_name": "Fallback Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client, "fallback.teacher", "a-secure-teacher-password"
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "6e B", "grade_level": "6e"},
        ).json()
        student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Emma", "last_name": "Martin"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{student['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "6e", "chapter": "Fallback"},
        ).json()
        for index in range(2):
            question = client.post(
                f"/api/question-banks/{bank['id']}/questions",
                headers=teacher_headers,
                data={
                    "payload": json.dumps(
                        {
                            "prompt": f"Fallback question {index}",
                            "points": 1,
                            "difficulty": "easy",
                            "answer_mode": "single",
                            "answer_mode_disclosed": True,
                            "choices": [
                                {"label": "Correct", "is_correct": True},
                                {"label": "Wrong", "is_correct": False},
                            ],
                        }
                    )
                },
            )
            assert question.status_code == 201

        quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Points inatteignables",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 2,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert quiz.status_code == 201

        launched = client.post(
            f"/api/quizzes/{quiz.json()['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201


def test_teacher_lists_use_constant_query_counts(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "list-performance.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "performance.teacher",
                    "display_name": "Performance Teacher",
                    "password": "a-secure-performance-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client,
            "performance.teacher",
            "a-secure-performance-password",
        )
        for index in range(6):
            student_class = client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": f"Class {index}", "grade_level": "6e"},
            ).json()
            account = client.post(
                "/api/students",
                headers=teacher_headers,
                json={"first_name": "Student", "last_name": str(index)},
            ).json()
            assert (
                client.post(
                    f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                    headers=teacher_headers,
                ).status_code
                == 200
            )

        with client.app.state.session_factory() as session:
            professor_id = session.scalar(
                select(User.id).where(User.username == "performance.teacher")
            )
            assert professor_id is not None
            bank = QuestionBank(
                owner_id=professor_id,
                grade_level="6e",
                chapter="Performance",
            )
            session.add(bank)
            session.flush()
            quizzes = [
                Quiz(
                    owner_id=professor_id,
                    mode="exam",
                    title=f"Quiz {index}",
                    question_count=0,
                )
                for index in range(6)
            ]
            session.add_all(quizzes)
            session.flush()
            session.add_all(
                QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank.id)
                for quiz in quizzes
            )
            session.commit()

        engine = client.app.state.session_factory.kw["bind"]
        statements: list[str] = []

        def record_statement(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_statement)
        try:
            assert (
                client.get("/api/students", headers=teacher_headers).status_code == 200
            )
            student_query_count = len(statements)
            statements.clear()
            assert (
                client.get("/api/classes", headers=teacher_headers).status_code == 200
            )
            class_query_count = len(statements)
            statements.clear()
            assert (
                client.get("/api/quizzes", headers=teacher_headers).status_code == 200
            )
            quiz_query_count = len(statements)
        finally:
            event.remove(engine, "before_cursor_execute", record_statement)

        assert student_query_count <= 4
        assert class_query_count <= 7
        assert quiz_query_count <= 5


def test_participant_maximum_scores_uses_constant_query_count(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "score-performance.db")) as client:
        with client.app.state.session_factory() as session:
            professor = User(
                username="score.teacher",
                display_name="Score Teacher",
                password_hash="unused",
            )
            session.add(professor)
            session.flush()
            student_class = StudentClass(
                owner_id=professor.id,
                name="Class",
                grade_level="6e",
            )
            bank = QuestionBank(
                owner_id=professor.id,
                grade_level="6e",
                chapter="Scores",
            )
            quiz = Quiz(
                owner_id=professor.id,
                mode="exam",
                title="Scores",
                question_count=1,
            )
            session.add_all([student_class, bank, quiz])
            session.flush()
            question = Question(
                question_bank_id=bank.id,
                prompt="Question",
                difficulty="easy",
                answer_mode="single",
                correction_mode="automatic",
            )
            session.add(question)
            session.flush()
            session.add(
                QuestionChoice(
                    question_id=question.id,
                    label="Answer",
                    is_correct=True,
                    points=2.5,
                    position=0,
                )
            )
            quiz_session = QuizSession(
                quiz_id=quiz.id,
                class_id=student_class.id,
                class_name="Class",
                join_code="SCORE1",
            )
            session.add(quiz_session)
            session.flush()
            participants = []
            for index in range(12):
                student = Student(
                    class_id=student_class.id,
                    identifier=f"student.{index}",
                    display_name=f"Student {index}",
                )
                session.add(student)
                session.flush()
                participant = QuizParticipant(
                    session_id=quiz_session.id,
                    student_id=student.id,
                    student_identifier=student.identifier,
                )
                session.add(participant)
                participants.append(participant)
                session.add(
                    QuizSessionStudentQuestion(
                        session_id=quiz_session.id,
                        student_id=student.id,
                        student_identifier=student.identifier,
                        question_id=question.id,
                        position=0,
                    )
                )
            session.commit()

            engine = client.app.state.session_factory.kw["bind"]
            statements: list[str] = []

            def record_statement(
                _connection, _cursor, statement, _parameters, _context, _executemany
            ) -> None:
                if statement.lstrip().upper().startswith("SELECT"):
                    statements.append(statement)

            event.listen(engine, "before_cursor_execute", record_statement)
            try:
                scores = participant_maximum_scores(quiz_session, participants, session)
            finally:
                event.remove(engine, "before_cursor_execute", record_statement)

        assert scores == {participant.id: 2.5 for participant in participants}
        assert len(statements) == 3


def test_quiz_can_assign_the_same_draw_to_every_student(tmp_path: Path) -> None:
    database_path = tmp_path / "common-quiz.db"
    with make_client(settings_for(database_path)) as client:
        environment = exam_environment(client)
        quiz = environment["quiz"]
        updated = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": quiz["title"],
                "source_language": quiz["source_language"],
                "question_bank_ids": [bank["id"] for bank in quiz["question_banks"]],
                "duration_seconds": quiz["duration_seconds"],
                "allow_previous_questions": quiz["allow_previous_questions"],
                "allow_negative_points": quiz["allow_negative_points"],
                "same_questions_for_all": True,
                "easy_question_count": quiz["easy_question_count"],
                "medium_question_count": quiz["medium_question_count"],
                "hard_question_count": quiz["hard_question_count"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["same_questions_for_all"] is True

        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=environment["teacher_headers"],
            json={"class_id": environment["student_class"]["id"]},
        )
        assert launched.status_code == 201

        with database_connection(database_path) as connection:
            common_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = %s",
                (launched.json()["id"],),
            ).fetchone()[0]
            personalized_count = connection.execute(
                "SELECT COUNT(*) FROM quiz_session_student_questions "
                "WHERE session_id = %s",
                (launched.json()["id"],),
            ).fetchone()[0]
        assert common_count == quiz["question_count"]
        assert personalized_count == 0


def test_concurrent_session_reads_finalize_an_expired_quiz_once(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "concurrent-expiry.db")) as client:
        environment = exam_environment(client)
        launched, participant_headers = launch_and_join(client, environment)
        started = client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        )
        assert started.status_code == status.HTTP_200_OK
        with client.app.state.session_factory() as session:
            quiz_session = session.get(QuizSession, launched["id"])
            assert quiz_session is not None
            quiz_session.started_at = datetime.now(UTC) - timedelta(hours=1)
            session.commit()

        barrier = Barrier(2)

        def teacher_state() -> tuple[int, str]:
            barrier.wait()
            response = client.get(
                f"/api/quizzes/sessions/{launched['id']}",
                headers=environment["teacher_headers"],
            )
            return response.status_code, response.json()["status"]

        def student_state() -> tuple[int, str]:
            barrier.wait()
            response = client.get(
                f"/api/quizzes/student/sessions/{launched['join_code']}",
                headers=participant_headers,
            )
            return response.status_code, response.json()["status"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result()
                for future in (
                    pool.submit(teacher_state),
                    pool.submit(student_state),
                )
            ]

        assert results == [(status.HTTP_200_OK, "finished")] * 2


def test_single_choice_maximum_uses_the_best_selectable_option(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "single-choice-maximum.db")) as client:
        environment = exam_environment(client)
        question = environment["question"]
        update_payload = {
            "prompt": question["prompt"],
            "difficulty": question["difficulty"],
            "answer_mode": question["answer_mode"],
            "answer_mode_disclosed": question["answer_mode_disclosed"],
            "response_language": question["response_language"],
            "allow_code_execution": question["allow_code_execution"],
            "code_language": question["code_language"],
            "code_content": question["code_content"],
            "choices": [
                {
                    "id": choice["id"],
                    "label": choice["label"],
                    "is_correct": choice["is_correct"],
                    "points": 2 if choice["is_correct"] else 1,
                    "code_language": choice["code_language"],
                    "code_content": choice["code_content"],
                }
                for choice in question["choices"]
            ],
        }
        updated = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=environment["teacher_headers"],
            data={"payload": json.dumps(update_payload)},
        )
        assert updated.status_code == 200
        environment["question"] = updated.json()

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
        hand_in_quiz(client, launched["join_code"], participant_headers)

        result = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        )
        assert result.status_code == 200
        participant = result.json()["participants"][0]
        assert participant["score"] == 2
        assert participant["maximum_score"] == 2


def test_answer_points_are_summed_and_negative_points_follow_quiz_setting(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "answer-points.db")) as client:
        environment = exam_environment(client)
        wrong_choice_id = next(
            choice["id"]
            for choice in environment["question"]["choices"]
            if not choice["is_correct"]
        )

        def complete_with_wrong_answer() -> float:
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
                    json={"selected_choice_ids": [wrong_choice_id]},
                ).status_code
                == 200
            )
            hand_in_quiz(client, quiz_session["join_code"], participant_headers)
            return client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=environment["teacher_headers"],
            ).json()["participants"][0]["score"]

        assert complete_with_wrong_answer() == 0
        updated = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": environment["quiz"]["title"],
                "question_bank_ids": [environment["question"]["question_bank_id"]],
                "allow_negative_points": True,
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        )
        assert updated.status_code == 200
        environment["quiz"] = updated.json()
        assert complete_with_wrong_answer() == -3


def test_join_code_reservations_prevent_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings_for(tmp_path / "join-code-reservations.db")
    app = create_app(app_settings)
    monkeypatch.setattr("app.routers.quizzes.randomizer.choice", lambda _: "A")

    with app.state.session_factory() as session:
        assert generate_join_code(session) == "AAAAAA"
        session.commit()

    with (
        app.state.session_factory() as session,
        pytest.raises(HTTPException) as error,
    ):
        generate_join_code(session)
    assert error.value.status_code == 503


def test_quiz_launch_uses_a_constant_query_count(tmp_path: Path) -> None:
    """Every student draws from the same pool, so it is read once per launch."""
    query_counts: dict[int, int] = {}
    for student_count in (4, 16):
        with make_client(
            settings_for(tmp_path / f"launch-{student_count}.db")
        ) as client:
            admin_headers = login_admin(client)
            assert (
                client.post(
                    "/api/admin/users",
                    headers=admin_headers,
                    json={
                        "username": "launch.teacher",
                        "display_name": "Launch Teacher",
                        "password": "a-secure-teacher-password",
                    },
                ).status_code
                == 201
            )
            teacher_headers, _ = complete_first_login(
                client, "launch.teacher", "a-secure-teacher-password"
            )
            student_class = client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": "3e A", "grade_level": "3e"},
            ).json()
            for index in range(student_count):
                account = client.post(
                    "/api/students",
                    headers=teacher_headers,
                    json={"first_name": f"Eleve{index}", "last_name": "Test"},
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
                json={"grade_level": "3e", "chapter": "Tirage"},
            ).json()
            for index in range(20):
                assert (
                    client.post(
                        f"/api/question-banks/{bank['id']}/questions",
                        headers=teacher_headers,
                        data={
                            "payload": json.dumps(
                                {
                                    "prompt": f"Question {index}",
                                    "difficulty": "easy",
                                    "answer_mode": "single",
                                    "answer_mode_disclosed": True,
                                    "choices": [
                                        {
                                            "label": "Ok",
                                            "is_correct": True,
                                            "points": 2,
                                        },
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
                    "title": "Tirage individuel",
                    "question_bank_ids": [bank["id"]],
                    "same_questions_for_all": False,
                    "easy_question_count": 5,
                    "medium_question_count": 0,
                    "hard_question_count": 0,
                },
            ).json()

            engine = client.app.state.session_factory.kw["bind"]
            statements = 0

            def count_statement(*_arguments: Any) -> None:
                nonlocal statements
                statements += 1

            event.listen(engine, "before_cursor_execute", count_statement)
            try:
                launched = client.post(
                    f"/api/quizzes/{quiz['id']}/launch",
                    headers=teacher_headers,
                    json={"class_id": student_class["id"]},
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_statement)
            assert launched.status_code == 201
            query_counts[student_count] = statements

    assert query_counts[4] == query_counts[16], (
        f"launch queries grow with class size: {query_counts}"
    )


def test_reported_maximum_score_is_actually_reachable(tmp_path: Path) -> None:
    """The ceiling must follow the same rule the grader applies.

    A distractor carrying positive points is only worth taking when the quiz
    awards negative points; otherwise selecting it scores zero, so it must not
    inflate the denominator.
    """
    with make_client(settings_for(tmp_path / "reachable-maximum.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "ceiling.teacher",
                    "display_name": "Ceiling Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "ceiling.teacher", "a-secure-teacher-password"
        )
        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "2nd", "chapter": "Barème"},
        ).json()
        created = client.post(
            f"/api/question-banks/{bank['id']}/questions",
            headers=teacher_headers,
            data={
                "payload": json.dumps(
                    {
                        "prompt": "Quels nombres sont premiers ?",
                        "difficulty": "medium",
                        "answer_mode": "multiple",
                        "answer_mode_disclosed": True,
                        "choices": [
                            {"label": "2", "is_correct": True, "points": 3},
                            {"label": "3", "is_correct": True, "points": 3},
                            {"label": "9", "is_correct": False, "points": 2},
                        ],
                    }
                )
            },
        )
        assert created.status_code == 201
        question_id = created.json()["id"]

        with client.app.state.session_factory() as session:
            choices = list(
                session.scalars(
                    select(QuestionChoice).where(
                        QuestionChoice.question_id == question_id
                    )
                )
            )
            every_choice = {choice.id for choice in choices}
            correct_only = {choice.id for choice in choices if choice.is_correct}

            # The ceiling is the key itself, so it does not depend on the mode,
            # but both modes still have to be able to reach it.
            reported = question_maximum_scores([question_id], session)[question_id]
            for allow_negative_points in (False, True):
                reachable = max(
                    selected_choice_score(
                        choices,
                        selection,
                        allow_negative_points=allow_negative_points,
                    )
                    for selection in (correct_only, every_choice)
                )
                assert reported == reachable, (
                    f"allow_negative_points={allow_negative_points}: "
                    f"reported {reported}, reachable {reachable}"
                )
