"""The whole journey: an administrator creates a teacher, who builds banks,
classes and quizzes that students then take, from grading to deletion."""

import json
from base64 import b64encode
from pathlib import Path

from support import (
    ADMIN_PASSWORD,
    VALID_PNG,
    assert_student_exam_payload_hides_answers,
    complete_first_login,
    database_connection,
    expire_due_sessions,
    login_admin,
    make_client,
    settings_for,
)


def test_admin_can_login_and_create_professor(tmp_path: Path) -> None:
    # A fixed account limit keeps the failed login loop below independent from
    # the shipped default.
    with make_client(settings_for(tmp_path / "test.db", login_attempts=5)) as client:
        headers = login_admin(client)
        assert client.get("/api/quizzes", headers=headers).status_code == 403

        created = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.one",
                "display_name": "Teacher One",
                "password": "another-strong-password",
            },
        )
        assert created.status_code == 201
        assert created.json()["username"] == "teacher.one"
        assert created.json()["is_admin"] is False
        assert "password" not in created.json()

        predictable_password = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.weak",
                "display_name": "Teacher Weak",
                "password": "a" * 16,
            },
        )
        assert predictable_password.status_code == 422

        duplicate = client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "teacher.one",
                "display_name": "Another",
                "password": "another-strong-password",
            },
        )
        assert duplicate.status_code == 409

        teacher_headers, _ = complete_first_login(
            client,
            "teacher.one",
            "another-strong-password",
        )
        assert client.get("/api/users/me", headers=teacher_headers).status_code == 200
        assert client.get("/api/quizzes", headers=teacher_headers).json() == []
        assert (
            client.get("/api/admin/users", headers=teacher_headers).status_code == 403
        )

        professor_login = client.post(
            "/api/auth/login",
            json={
                "username": "root-admin",
                "password": ADMIN_PASSWORD,
                "audience": "professor",
            },
        )
        assert professor_login.status_code == 403

        admin_login = client.post(
            "/api/auth/login",
            json={
                "username": "teacher.one",
                "password": "another-strong-password",
                "audience": "admin",
            },
        )
        assert admin_login.status_code == 403

        created_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": " 5e   B ", "grade_level": " 5e "},
        )
        assert created_class.status_code == 201
        student_class = created_class.json()
        assert student_class["name"] == "5e B"
        assert student_class["grade_level"] == "5e"
        assert student_class["students"] == []
        assert student_class["completed_quiz_count"] == 0
        assert student_class["latest_quiz_title"] is None
        assert student_class["latest_quiz_at"] is None
        grade_levels = client.get("/api/grade-levels", headers=teacher_headers).json()
        assert [level["name"] for level in grade_levels] == [
            "2nd",
            "1ere",
            "Tle",
            "5e",
        ]
        class_example = client.get(
            "/api/classes/example",
            headers=teacher_headers,
        )
        assert class_example.status_code == 200
        example_class = class_example.json()["classes"][0]
        assert "Niveaux de classe disponibles" in example_class["_comment_grade_level"]
        assert all(
            level["name"] in example_class["_comment_grade_level"]
            for level in grade_levels
        )
        assert example_class["grade_level"] == "2nd"
        duplicate_grade_level = client.post(
            "/api/grade-levels",
            headers=teacher_headers,
            json={"name": " 5E "},
        )
        assert duplicate_grade_level.status_code == 201
        fifth_grade = next(level for level in grade_levels if level["name"] == "5e")
        assert duplicate_grade_level.json()["id"] == fifth_grade["id"]
        assert (
            client.delete(
                f"/api/grade-levels/{fifth_grade['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )
        unused_level = client.post(
            "/api/grade-levels",
            headers=teacher_headers,
            json={"name": " 4e "},
        )
        assert unused_level.status_code == 201
        assert unused_level.json()["name"] == "4e"
        assert (
            client.delete(
                f"/api/grade-levels/{unused_level.json()['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/api/classes",
                headers=teacher_headers,
                json={"name": "5e B", "grade_level": "5e"},
            ).status_code
            == 409
        )

        student_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Martin",
                "last_name": "Giraud",
            },
        ).json()
        assigned_class = client.post(
            f"/api/classes/{student_class['id']}/accounts/{student_account['id']}",
            headers=teacher_headers,
        )
        assert assigned_class.status_code == 200
        assert (
            assigned_class.json()["students"][0]["account_id"] == student_account["id"]
        )
        exam_student_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "martin.giraud",
                "password": student_account["generated_password"],
            },
        )
        assert exam_student_login.status_code == 200
        exam_account_headers = {
            "Authorization": f"Bearer {exam_student_login.json()['access_token']}"
        }
        updated_class = client.post(
            f"/api/classes/{student_class['id']}/update",
            headers=teacher_headers,
            json={"name": "5e B", "grade_level": "Cinquième"},
        )
        assert updated_class.status_code == 200
        assert updated_class.json()["grade_level"] == "Cinquième"
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/students",
                headers=teacher_headers,
                json={"display_name": "Legacy student"},
            ).status_code
            == 404
        )
        listed_classes = client.get(
            "/api/classes",
            headers=teacher_headers,
        )
        assert listed_classes.status_code == 200
        assert listed_classes.json()[0]["student_count"] == 1

        first_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": " 5e ", "chapter": " Les   fractions "},
        )
        assert first_bank.status_code == 201
        assert first_bank.json()["grade_level"] == "5e"
        assert first_bank.json()["chapter"] == "Les fractions"

        second_bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "4e", "chapter": "Calcul littéral"},
        )
        assert second_bank.status_code == 201

        question_banks = client.get(
            "/api/question-banks",
            headers=teacher_headers,
        )
        assert question_banks.status_code == 200
        assert [
            (bank["grade_level"], bank["chapter"]) for bank in question_banks.json()
        ] == [("4e", "Calcul littéral"), ("5e", "Les fractions")]

        duplicate = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": "5e", "chapter": "Les fractions"},
        )
        assert duplicate.status_code == 409
        assert client.get("/api/question-banks", headers=headers).status_code == 403

        question_payload = {
            "prompt": "Quelle fraction est égale à un demi ?",
            "difficulty": "easy",
            "answer_mode": "single",
            "answer_mode_disclosed": False,
            "code_language": "python",
            "code_content": "def half(value):\n    return value / 2",
            "choices": [
                {
                    "label": "1/2",
                    "is_correct": True,
                    "image": {
                        "content_type": "image/png",
                        "data_base64": b64encode(VALID_PNG).decode(),
                    },
                    "code_language": "python",
                    "code_content": "print(1 / 2)",
                },
                {"label": "1/3", "is_correct": False},
            ],
        }
        created_question = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_payload)},
            files={
                "image": (
                    "fraction.png",
                    VALID_PNG,
                    "image/png",
                )
            },
        )
        assert created_question.status_code == 201
        question = created_question.json()
        assert "points" not in question
        assert question["has_image"] is True
        assert "correction_mode" not in question
        assert question["answer_mode_disclosed"] is False
        assert question["code_language"] == "python"
        assert "return value / 2" in question["code_content"]
        assert [choice["is_correct"] for choice in question["choices"]] == [
            True,
            False,
        ]
        assert [choice["points"] for choice in question["choices"]] == [1, 0]
        assert question["choices"][0]["has_image"] is True
        assert question["choices"][0]["code_language"] == "python"
        assert question["choices"][0]["code_content"] == "print(1 / 2)"
        invalid_image = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_payload)},
            files={
                "image": (
                    "not-an-image.png",
                    b"\x89PNG\r\n\x1a\nnot-a-real-image",
                    "image/png",
                )
            },
        )
        assert invalid_image.status_code == 422
        reordered_payload = {
            **question_payload,
            "choices": [
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][1]["id"],
                },
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][0]["id"],
                },
            ],
        }
        reordered_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(reordered_payload)},
        )
        assert reordered_question.status_code == 200
        question = reordered_question.json()
        assert [choice["label"] for choice in question["choices"]] == [
            "1/3",
            "1/2",
        ]
        restored_payload = {
            **question_payload,
            "choices": [
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][1]["id"],
                },
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][0]["id"],
                },
            ],
        }
        restored_question = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(restored_payload)},
        )
        assert restored_question.status_code == 200
        question = restored_question.json()
        bank_with_question = next(
            bank
            for bank in client.get(
                "/api/question-banks",
                headers=teacher_headers,
            ).json()
            if bank["id"] == first_bank.json()["id"]
        )
        assert bank_with_question["question_count"] == 1

        listed_questions = client.get(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
        )
        assert listed_questions.status_code == 200
        assert listed_questions.json()[0]["prompt"] == question_payload["prompt"]

        image = client.get(
            f"/api/question-banks/questions/{question['id']}/image",
            headers=teacher_headers,
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG")
        choice_image = client.get(
            f"/api/question-banks/choices/{question['choices'][0]['id']}/image",
            headers=teacher_headers,
        )
        assert choice_image.status_code == 200
        assert choice_image.headers["content-type"] == "image/png"
        assert choice_image.content.startswith(b"\x89PNG")

        question_without_correct_answer = {
            **question_payload,
            "choices": [
                {"label": "1/2", "is_correct": False},
                {"label": "1/3", "is_correct": False},
            ],
        }
        invalid_question = client.post(
            f"/api/question-banks/{first_bank.json()['id']}/questions",
            headers=teacher_headers,
            data={"payload": json.dumps(question_without_correct_answer)},
        )
        assert invalid_question.status_code == 422

        exported = client.get(
            f"/api/question-banks/{first_bank.json()['id']}/export",
            headers=teacher_headers,
        )
        assert exported.status_code == 200
        assert "attachment;" in exported.headers["content-disposition"]
        assert exported.text.startswith('{\n  "version": 1,')
        assert '"prompt": "Quelle fraction' in exported.text
        exported_batch = exported.json()
        assert exported_batch["version"] == 1
        assert exported_batch["question_bank"] == {
            "grade_level": "5e",
            "chapter": "Les fractions",
        }
        assert exported_batch["questions"][0]["image"]["content_type"] == "image/png"
        assert "correction_mode" not in exported_batch["questions"][0]
        assert "points" not in exported_batch["questions"][0]
        assert exported_batch["questions"][0]["code_language"] == "python"
        assert [
            choice["points"] for choice in exported_batch["questions"][0]["choices"]
        ] == [1, 0]
        assert exported_batch["questions"][0]["choices"][0]["image"] is not None
        assert (
            exported_batch["questions"][0]["choices"][0]["code_content"]
            == "print(1 / 2)"
        )

        exported_batch["question_bank"] = {
            "grade_level": "3e",
            "chapter": "Fractions importées",
        }
        imported = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=exported_batch,
        )
        assert imported.status_code == 201
        imported_payload = imported.json()
        assert imported_payload["question_bank"]["grade_level"] == "3e"
        assert imported_payload["question_bank"]["chapter"] == "Fractions importées"
        assert imported_payload["question_bank"]["question_count"] == 1
        assert len(imported_payload["questions"]) == 1
        assert imported_payload["questions"][0]["prompt"] == question_payload["prompt"]
        assert imported_payload["questions"][0]["has_image"] is True
        assert imported_payload["questions"][0]["choices"][0]["has_image"] is True
        assert (
            imported_payload["questions"][0]["choices"][0]["code_language"] == "python"
        )

        duplicate_import = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=exported_batch,
        )
        assert duplicate_import.status_code == 409

        empty_import = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json={
                "version": 1,
                "question_bank": {
                    "grade_level": "6e",
                    "chapter": "Banque vide",
                },
                "questions": [],
            },
        )
        assert empty_import.status_code == 201
        assert empty_import.json()["question_bank"]["question_count"] == 0
        assert empty_import.json()["questions"] == []

        example = client.get(
            "/api/question-banks/example",
            headers=teacher_headers,
        )
        assert example.status_code == 200
        assert example.text.startswith('{\n  "version": 1,')
        assert '"prompt": "Quelle est la capitale' in example.text
        example_batch = example.json()
        assert example_batch["version"] == 1
        assert (
            "Niveaux de classe disponibles"
            in example_batch["question_bank"]["_comment_grade_level"]
        )
        assert "3e" in example_batch["question_bank"]["_comment_grade_level"]
        assert {item["answer_mode"] for item in example_batch["questions"]} == {
            "single",
            "multiple",
            "written",
        }
        assert all("correction_mode" not in item for item in example_batch["questions"])
        assert all("points" not in item for item in example_batch["questions"])
        assert all("response_language" in item for item in example_batch["questions"])
        assert any(item["image"] for item in example_batch["questions"])
        assert any(item["code_content"] for item in example_batch["questions"])
        written_example = next(
            item
            for item in example_batch["questions"]
            if item["answer_mode"] == "written"
        )
        assert written_example["response_language"] == "python"
        assert written_example["allow_code_execution"] is True
        assert written_example["choices"][0]["label"] == "print(2 + 3)"
        assert any(
            choice["image"]
            for item in example_batch["questions"]
            for choice in item["choices"]
        )
        assert any(
            choice["code_content"]
            for item in example_batch["questions"]
            for choice in item["choices"]
        )
        assert all(
            "points" in choice
            for item in example_batch["questions"]
            for choice in item["choices"]
        )

        example_batch["question_bank"] = {
            "grade_level": "Terminale",
            "chapter": "Import de l’exemple",
        }
        imported_example = client.post(
            "/api/question-banks/import",
            headers=teacher_headers,
            json=example_batch,
        )
        assert imported_example.status_code == 201
        assert imported_example.json()["question_bank"]["question_count"] == 3
        assert {
            question["answer_mode"] for question in imported_example.json()["questions"]
        } == {"single", "multiple", "written"}
        assert (
            next(
                question
                for question in imported_example.json()["questions"]
                if question["answer_mode"] == "written"
            )["response_language"]
            == "python"
        )

        invalid_quiz_counts = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": "Révisions invalides",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "easy_question_count": 2,
                "medium_question_count": 1,
                "hard_question_count": 0,
            },
        )
        assert invalid_quiz_counts.status_code == 422

        created_quiz = client.post(
            "/api/quizzes",
            headers=teacher_headers,
            json={
                "title": " Révisions   générales ",
                "source_language": "en",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert created_quiz.status_code == 201
        quiz = created_quiz.json()
        assert quiz["title"] == "Révisions générales"
        assert quiz["source_language"] == "en"
        assert quiz["question_count"] == 3
        assert quiz["easy_question_count"] == 1
        assert quiz["medium_question_count"] == 1
        assert quiz["hard_question_count"] == 1
        assert {
            "easy_points",
            "medium_points",
            "hard_points",
        }.isdisjoint(quiz)
        assert quiz["duration_seconds"] == 900
        assert quiz["allow_previous_questions"] is False
        assert quiz["same_questions_for_all"] is False
        assert len(quiz["question_banks"]) == 1
        assert quiz["question_banks"][0]["easy_question_count"] == 1
        assert quiz["question_banks"][0]["medium_question_count"] == 1
        assert quiz["question_banks"][0]["hard_question_count"] == 1
        assert (
            client.get("/api/quizzes", headers=teacher_headers).json()[0]["id"]
            == quiz["id"]
        )
        updated_quiz = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=teacher_headers,
            json={
                "title": "Révisions générales modifiées",
                "source_language": "en",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "duration_seconds": 2400,
                "allow_previous_questions": True,
                "same_questions_for_all": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert updated_quiz.status_code == 200
        quiz = updated_quiz.json()
        assert quiz["title"] == "Révisions générales modifiées"
        assert quiz["source_language"] == "en"
        assert quiz["duration_seconds"] == 2400
        assert quiz["allow_previous_questions"] is True
        assert quiz["same_questions_for_all"] is False

        preview = client.get(
            f"/api/quizzes/{quiz['id']}/preview",
            headers=teacher_headers,
        )
        assert preview.status_code == 200
        assert len(preview.json()) == 3
        assert {question["difficulty"] for question in preview.json()} == {
            "easy",
            "medium",
            "hard",
        }

        late_student = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Late",
                "last_name": "Student",
            },
        )
        assert late_student.status_code == 201
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/"
                f"{late_student.json()['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        late_student_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "late.student",
                "password": late_student.json()["generated_password"],
            },
        )
        late_account_headers = {
            "Authorization": f"Bearer {late_student_login.json()['access_token']}"
        }

        launched = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert launched.status_code == 201
        quiz_session = launched.json()
        assert quiz_session["class_name"] == "Cinquième 5e B"
        assert quiz_session["status"] == "waiting"
        assert len(quiz_session["join_code"]) == 6
        with database_connection(tmp_path / "test.db") as connection:
            student_count = connection.execute(
                "SELECT COUNT(*) FROM students WHERE class_id = %s",
                (student_class["id"],),
            ).fetchone()[0]
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = %s",
                    (quiz_session["id"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM quiz_session_student_questions "
                    "WHERE session_id = %s",
                    (quiz_session["id"],),
                ).fetchone()[0]
                == student_count * quiz["question_count"]
            )
            assigned_points = connection.execute(
                "SELECT assigned.student_id, SUM(CASE WHEN choices.points > 0 "
                "THEN choices.points ELSE 0 END) "
                "FROM quiz_session_student_questions AS assigned "
                "JOIN question_choices AS choices "
                "ON choices.question_id = assigned.question_id "
                "WHERE assigned.session_id = %s GROUP BY assigned.student_id",
                (quiz_session["id"],),
            ).fetchall()
            assert assigned_points
            assert all(total == 18 for _, total in assigned_points)
            assert {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT question_total FROM ("
                    "SELECT assigned.student_id, assigned.question_id, "
                    "SUM(CASE WHEN choices.points > 0 THEN choices.points "
                    "ELSE 0 END) AS question_total "
                    "FROM quiz_session_student_questions AS assigned "
                    "JOIN question_choices AS choices "
                    "ON choices.question_id = assigned.question_id "
                    "WHERE assigned.session_id = %s "
                    "GROUP BY assigned.student_id, assigned.question_id)",
                    (quiz_session["id"],),
                )
            } == {3, 6, 9}
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()[0]["id"]
            == quiz_session["id"]
        )
        assert (
            client.post(
                f"/api/quizzes/{quiz['id']}/update",
                headers=teacher_headers,
                json={
                    "title": quiz["title"],
                    "source_language": "en",
                    "question_bank_ids": [
                        imported_example.json()["question_bank"]["id"]
                    ],
                    "duration_seconds": 2400,
                    "allow_previous_questions": True,
                    "easy_question_count": 1,
                    "medium_question_count": 1,
                    "hard_question_count": 1,
                },
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )

        legacy_join_payload = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={
                "join_code": quiz_session["join_code"],
                "student_identifier": "martin.giraud",
            },
        )
        assert legacy_join_payload.status_code == 422
        joined = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"].lower()},
        )
        assert joined.status_code == 201
        assert joined.json()["quiz_title"] == quiz["title"]
        assert joined.json()["source_language"] == "en"
        assert joined.json()["student_name"] == "Martin Giraud"
        assert "participants" not in joined.json()
        assert_student_exam_payload_hides_answers(joined.json())
        with database_connection(tmp_path / "test.db") as connection:
            successful_join_limits = connection.execute(
                "SELECT COUNT(*) FROM login_rate_limits "
                "WHERE limiter_key LIKE 'quiz-join:%'"
            ).fetchone()[0]
        assert successful_join_limits == 0
        assert (
            client.post(
                "/api/quizzes/join",
                json={"join_code": quiz_session["join_code"]},
            ).status_code
            == 401
        )
        joined_again = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert joined_again.status_code == 403
        assert joined_again.json()["detail"]["code"] == "QUIZ_JOIN_REJECTED"
        participant_token = joined.json()["participant_token"]
        student_headers = {"X-Quiz-Token": participant_token}
        assert (
            client.get(
                f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
            ).status_code
            == 401
        )

        waiting_room = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        )
        assert waiting_room.status_code == 200
        assert waiting_room.json()["participant_count"] == 1
        assert (
            waiting_room.json()["participants"][0]["student_display_name"]
            == "Martin Giraud"
        )
        student_state_url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        left = client.post(f"{student_state_url}/leave", headers=student_headers)
        assert left.status_code == 204
        assert client.get(student_state_url, headers=student_headers).status_code == 401
        waiting_room_after_leave = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        )
        assert waiting_room_after_leave.status_code == 200
        assert waiting_room_after_leave.json()["participant_count"] == 0
        assert waiting_room_after_leave.json()["participants"] == []

        rejoined = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert rejoined.status_code == 201
        assert rejoined.json()["participant_token"] != participant_token
        participant_token = rejoined.json()["participant_token"]
        student_headers = {"X-Quiz-Token": participant_token}
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()["participant_count"]
            == 1
        )
        assert (
            client.get(student_state_url, headers=student_headers).json()[
                "source_language"
            ]
            == "en"
        )
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "waiting"
        )
        waiting_violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert waiting_violation.status_code == 204
        assert (
            client.post(
                f"{student_state_url}/violation",
                headers=student_headers,
                json={"event_type": "copy_attempt", "forged_count": 100},
            ).status_code
            == 422
        )
        waiting_participant = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert waiting_participant["violation_count"] == 0

        started = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start",
            headers=teacher_headers,
        )
        assert started.status_code == 200
        assert started.json()["status"] == "in_progress"
        assert started.json()["started_at"] is not None
        assert started.json()["ends_at"] is not None
        active_leave = client.post(
            f"{student_state_url}/leave", headers=student_headers
        )
        assert active_leave.status_code == 204
        active_rejoin = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert active_rejoin.status_code == 201
        assert active_rejoin.json()["status"] == "in_progress"
        assert active_rejoin.json()["participant_token"] != participant_token
        participant_token = active_rejoin.json()["participant_token"]
        student_headers = {"X-Quiz-Token": participant_token}
        late_join = client.post(
            "/api/quizzes/join",
            headers=late_account_headers,
            json={"join_code": quiz_session["join_code"]},
        )
        assert late_join.status_code == 403
        assert late_join.json()["detail"]["code"] == "QUIZ_JOIN_REJECTED"
        original_ends_at = started.json()["ends_at"]
        paused = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/pause",
            headers=teacher_headers,
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        paused_student_state = client.get(
            student_state_url,
            headers=student_headers,
        ).json()
        assert paused_student_state["status"] == "paused"
        assert paused_student_state["question"] is None
        assert (
            client.post(
                f"{student_state_url}/answer",
                headers=student_headers,
                json={},
            ).status_code
            == 409
        )
        resumed = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/resume",
            headers=teacher_headers,
        )
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "in_progress"
        assert resumed.json()["ends_at"] >= original_ends_at
        violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert violation.status_code == 204
        monitored = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert monitored["violation_count"] == 1
        assert monitored["last_violation_type"] == "fullscreen_exit"
        assert monitored["last_violation_at"] is not None
        duplicate_violation = client.post(
            f"{student_state_url}/violation",
            headers=student_headers,
            json={"event_type": "fullscreen_exit"},
        )
        assert duplicate_violation.status_code == 204
        monitored = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()["participants"][0]
        assert monitored["violation_count"] == 1
        assert (
            client.post(
                "/api/quizzes/join",
                json={"join_code": quiz_session["join_code"]},
            ).status_code
            == 401
        )
        assert (
            client.delete(
                f"/api/question-banks/{imported_example.json()['question_bank']['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/question-banks/questions/{preview.json()[0]['id']}",
                headers=teacher_headers,
            ).status_code
            == 409
        )

        expected_by_prompt = {
            item["prompt"]: item for item in example_batch["questions"]
        }
        for question_number in range(1, 4):
            student_state = client.get(student_state_url, headers=student_headers)
            assert student_state.status_code == 200
            state_payload = student_state.json()
            assert state_payload["question_number"] == question_number
            assert state_payload["question"] is not None
            repeated_state = client.get(
                student_state_url,
                headers=student_headers,
            ).json()
            assert [
                choice["id"] for choice in repeated_state["question"]["choices"]
            ] == [choice["id"] for choice in state_payload["question"]["choices"]]
            assert [
                choice["position"] for choice in state_payload["question"]["choices"]
            ] == list(range(len(state_payload["question"]["choices"])))

            assert_student_exam_payload_hides_answers(state_payload)
            safe_question = state_payload["question"]
            expected = expected_by_prompt[safe_question["prompt"]]
            if safe_question["answer_mode"] == "written":
                assert safe_question["choices"] == []
                expected_answer = expected["choices"][0]["label"]
                assert expected_answer not in json.dumps(
                    state_payload,
                    ensure_ascii=False,
                )
                answer_payload = {
                    "written_answer": "Réponse rédactionnelle très longue. " * 200
                }
            else:
                missing_answer = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json={},
                )
                assert missing_answer.status_code == 422
                empty_answer = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json={"selected_choice_ids": []},
                )
                assert empty_answer.status_code == 422
                correct_labels = {
                    choice["label"]
                    for choice in expected["choices"]
                    if choice["is_correct"]
                }
                answer_payload = {
                    "selected_choice_ids": [
                        choice["id"]
                        for choice in safe_question["choices"]
                        if choice["label"] in correct_labels
                    ]
                }
            submitted = client.post(
                f"{student_state_url}/answer",
                headers=student_headers,
                json=answer_payload,
            )
            assert submitted.status_code == 200
            assert_student_exam_payload_hides_answers(submitted.json())
            if question_number < 3:
                assert submitted.json()["question_number"] == question_number + 1
                assert submitted.json()["question"] is not None
            else:
                # The quiz offers the review step by default: the last answer
                # opens the summary instead of ending the session.
                assert submitted.json()["status"] == "in_progress"
                assert submitted.json()["awaiting_final_submission"] is True
                assert submitted.json()["question"] is None
                assert [
                    summary["question_number"]
                    for summary in submitted.json()["answer_summaries"]
                ] == [1, 2, 3]
                handed_in = client.post(
                    f"{student_state_url}/submit",
                    headers=student_headers,
                )
                assert handed_in.status_code == 200
                assert handed_in.json()["status"] == "finished"
                assert handed_in.json()["awaiting_final_submission"] is False
                assert handed_in.json()["question"] is None
                assert_student_exam_payload_hides_answers(handed_in.json())
            teacher_state = client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()
            assert teacher_state["participants"][0]["answered_count"] == question_number
            assert teacher_state["participants"][0]["has_finished"] is (
                question_number == 3
            )
            if question_number < 3:
                assert teacher_state["participants"][0]["score"] == 0
            if question_number == 2:
                previous = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 2},
                )
                assert previous.status_code == 200
                assert previous.json()["question_number"] == 2
                assert previous.json()["accessible_question_numbers"] == [1, 2, 3]
                assert previous.json()["has_answered"] is True
                assert (
                    previous.json()["selected_choice_ids"] is not None
                    or previous.json()["written_answer"] is not None
                )
                assert_student_exam_payload_hides_answers(previous.json())
                returned_to_current = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 3},
                )
                assert returned_to_current.status_code == 200
                assert returned_to_current.json()["question_number"] == 3
                previous = client.post(
                    f"{student_state_url}/navigate",
                    headers=student_headers,
                    json={"question_number": 2},
                )
                assert previous.status_code == 200
                paused_with_answer = client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/pause",
                    headers=teacher_headers,
                )
                assert paused_with_answer.status_code == 200
                answer_during_pause = client.get(
                    student_state_url,
                    headers=student_headers,
                ).json()
                assert answer_during_pause["status"] == "paused"
                assert answer_during_pause["question"] is None
                assert (
                    answer_during_pause["selected_choice_ids"]
                    == previous.json()["selected_choice_ids"]
                )
                assert (
                    answer_during_pause["written_answer"]
                    == previous.json()["written_answer"]
                )
                resumed_with_answer = client.post(
                    f"/api/quizzes/sessions/{quiz_session['id']}/resume",
                    headers=teacher_headers,
                )
                assert resumed_with_answer.status_code == 200
                answer_after_resume = client.get(
                    student_state_url,
                    headers=student_headers,
                ).json()
                assert (
                    answer_after_resume["selected_choice_ids"]
                    == previous.json()["selected_choice_ids"]
                )
                assert (
                    answer_after_resume["written_answer"]
                    == previous.json()["written_answer"]
                )
                resubmitted = client.post(
                    f"{student_state_url}/answer",
                    headers=student_headers,
                    json=answer_payload,
                )
                assert resubmitted.status_code == 200
                assert resubmitted.json()["question_number"] == 3

        assert teacher_state["status"] == "finished"
        assert teacher_state["participants"][0]["score"] > 0
        partial_history = client.get(
            "/api/quizzes/student/results",
            headers=exam_account_headers,
        )
        assert partial_history.status_code == 200
        partial_item = partial_history.json()[0]
        assert partial_item["session_id"] == quiz_session["id"]
        assert partial_item["grades_published"] is False
        assert partial_item["score"] == teacher_state["participants"][0]["score"]
        assert 0 < partial_item["score"] < partial_item["maximum_score"]
        partial_written = next(
            answer
            for answer in partial_item["answers"]
            if answer["answer_mode"] == "written"
        )
        assert partial_written["is_correct"] is None
        assert partial_written["score"] == 0
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
            == []
        )
        results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        )
        assert results.status_code == 200
        assert [result["id"] for result in results.json()] == [quiz_session["id"]]
        assert results.json()[0]["quiz_title"] == quiz["title"]
        assert results.json()[0]["class_name"] == "Cinquième 5e B"
        assert results.json()[0]["participants"][0]["score"] > 0
        maximum_score = results.json()[0]["participants"][0]["maximum_score"]
        assert maximum_score > 0
        assert results.json()[0]["median_maximum_score"] == maximum_score
        assert results.json()[0]["participants"][0]["pending_manual_grading_count"] == 1
        original_ends_at = results.json()[0]["ends_at"]

        exported_results = client.get(
            "/api/quizzes/sessions/results/export",
            headers=teacher_headers,
            params={"class_id": student_class["id"], "quiz_id": quiz["id"]},
        )
        assert exported_results.status_code == 200
        assert exported_results.headers["content-type"].startswith("text/csv")
        assert "attachment;" in exported_results.headers["content-disposition"]
        assert exported_results.text.startswith("\ufeffclass,quiz,date,")
        assert quiz["title"] in exported_results.text
        assert teacher_state["participants"][0]["student_identifier"] in (
            exported_results.text
        )

        all_quiz_results = client.get(
            "/api/quizzes/sessions/results/export",
            headers=teacher_headers,
            params={"class_id": student_class["id"]},
        )
        assert all_quiz_results.status_code == 200
        assert quiz["title"] in all_quiz_results.text

        edited_quiz = client.post(
            f"/api/quizzes/{quiz['id']}/update",
            headers=teacher_headers,
            json={
                "title": "Nouveau titre pour les prochaines sessions",
                "source_language": "de",
                "question_bank_ids": [imported_example.json()["question_bank"]["id"]],
                "duration_seconds": 60,
                "allow_previous_questions": False,
                "easy_question_count": 1,
                "medium_question_count": 1,
                "hard_question_count": 1,
            },
        )
        assert edited_quiz.status_code == 200
        historical_result = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()[0]
        assert historical_result["quiz_title"] == quiz["title"]
        assert historical_result["ends_at"] == original_ends_at
        historical_search = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
            params={"quiz_search": quiz["title"]},
        )
        assert [result["id"] for result in historical_search.json()] == [
            quiz_session["id"]
        ]
        renamed_search = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
            params={"quiz_search": edited_quiz.json()["title"]},
        )
        assert renamed_search.json() == []
        historical_student_state = client.get(
            student_state_url,
            headers=student_headers,
        ).json()
        assert historical_student_state["quiz_title"] == quiz["title"]
        assert historical_student_state["source_language"] == "en"
        assert historical_student_state["allow_previous_questions"] is True
        assert (
            client.get("/api/quizzes/sessions/results", headers=headers).status_code
            == 403
        )
        reviewed_answers = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}/participants/"
            f"{teacher_state['participants'][0]['id']}/answers",
            headers=teacher_headers,
        )
        assert reviewed_answers.status_code == 200
        assert len(reviewed_answers.json()) == 3
        assert all(
            answer["is_correct"] is True
            for answer in reviewed_answers.json()
            if answer["answer_mode"] != "written"
        )
        written_review = next(
            answer
            for answer in reviewed_answers.json()
            if answer["answer_mode"] == "written"
        )
        assert written_review["submitted_answers"]
        assert len(written_review["submitted_answers"][0]) > 4000
        assert written_review["expected_answers"]
        assert written_review["score"] == 0
        assert written_review["is_graded"] is False
        assert written_review["is_correct"] is None
        unpublished = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
            headers=teacher_headers,
        )
        assert unpublished.status_code == 409
        manually_graded = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/answers/"
            f"{written_review['id']}/grade",
            headers=teacher_headers,
            json={"score": written_review["max_score"]},
        )
        assert manually_graded.status_code == 200
        assert manually_graded.json()["is_graded"] is True
        assert manually_graded.json()["score"] == written_review["max_score"]
        assert manually_graded.json()["is_correct"] is True
        graded_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        assert graded_results[0]["participants"][0]["pending_manual_grading_count"] == 0
        published = client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/publish-grades",
            headers=teacher_headers,
        )
        assert published.status_code == 200
        assert published.json()["grades_published_at"] is not None
        graded_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        published_history = client.get(
            "/api/quizzes/student/results",
            headers=exam_account_headers,
        ).json()[0]
        assert published_history["session_id"] == quiz_session["id"]
        assert published_history["quiz_title"] == quiz["title"]
        assert published_history["grades_published"] is True
        assert (
            published_history["score"] == published.json()["participants"][0]["score"]
        )
        assert published_history["maximum_score"] == maximum_score
        assert len(published_history["answers"]) == 3
        assert all(answer["is_correct"] for answer in published_history["answers"])
        assert all(
            {"is_graded"}.isdisjoint(answer) for answer in published_history["answers"]
        )
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/answers/"
                f"{written_review['id']}/grade",
                headers=teacher_headers,
                json={"score": 0},
            ).status_code
            == 409
        )
        regraded_question = next(
            question
            for question in preview.json()
            if question["answer_mode"] != "written"
        )
        regraded_payload = {
            "prompt": regraded_question["prompt"],
            "difficulty": regraded_question["difficulty"],
            "answer_mode": regraded_question["answer_mode"],
            "answer_mode_disclosed": regraded_question["answer_mode_disclosed"],
            "code_language": regraded_question["code_language"],
            "code_content": regraded_question["code_content"],
            "choices": [
                {
                    "id": choice["id"],
                    "label": choice["label"],
                    "is_correct": choice["is_correct"],
                    "points": choice["points"],
                    "code_language": choice["code_language"],
                    "code_content": choice["code_content"],
                }
                for choice in regraded_question["choices"]
            ],
        }
        regraded = client.post(
            f"/api/question-banks/questions/{regraded_question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(regraded_payload)},
        )
        assert regraded.status_code == 200
        refreshed_results = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        ).json()
        assert refreshed_results == graded_results

        blocked_delete = client.delete(
            f"/api/question-banks/questions/{regraded_question['id']}",
            headers=teacher_headers,
        )
        assert blocked_delete.status_code == 409
        assert blocked_delete.json()["detail"] == {
            "code": "QUESTION_IN_LAUNCHED_QUIZ",
            "message": "Cette question est utilisée par un quiz déjà lancé",
        }

        makeup_created = client.post(
            "/api/quizzes/makeup/sessions",
            headers=teacher_headers,
            json={
                "class_id": student_class["id"],
                "quiz_ids": [quiz["id"]],
            },
        )
        assert makeup_created.status_code == 201
        makeup = makeup_created.json()
        assert (
            makeup["quizzes"][0]["duration_seconds"]
            == edited_quiz.json()["duration_seconds"]
        )
        makeup_joined = client.post(
            "/api/quizzes/makeup/join",
            headers=exam_account_headers,
            json={"join_code": makeup["join_code"]},
        )
        assert makeup_joined.status_code == 200
        assert [item["id"] for item in makeup_joined.json()["quizzes"]] == [quiz["id"]]
        makeup_selected = client.post(
            f"/api/quizzes/makeup/{makeup['join_code']}/select",
            headers=exam_account_headers,
            json={"quiz_id": quiz["id"]},
        )
        assert makeup_selected.status_code == 201
        assert makeup_selected.json()["status"] == "waiting"
        assert makeup_selected.json()["quiz_title"] == edited_quiz.json()["title"]
        assert (
            client.post(
                f"/api/quizzes/makeup/{makeup['join_code']}/select",
                headers=exam_account_headers,
                json={"quiz_id": quiz["id"]},
            ).status_code
            == 409
        )
        makeup_started = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/start",
            headers=teacher_headers,
        )
        assert makeup_started.status_code == 200
        assert makeup_started.json()["status"] == "in_progress"
        makeup_state = client.get(
            f"/api/quizzes/student/sessions/{makeup_selected.json()['join_code']}",
            headers={"X-Quiz-Token": makeup_selected.json()["participant_token"]},
        )
        assert makeup_state.status_code == 200
        assert makeup_state.json()["status"] == "in_progress"
        assert makeup_state.json()["question"] is not None
        makeup_finished = client.post(
            f"/api/quizzes/makeup/sessions/{makeup['id']}/finish",
            headers=teacher_headers,
        )
        assert makeup_finished.status_code == 200
        assert makeup_finished.json()["status"] == "finished"

        cancelled_launch = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert cancelled_launch.status_code == 201
        cancelled_session = cancelled_launch.json()
        cancelled_join = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": cancelled_session["join_code"]},
        )
        assert cancelled_join.status_code == 201
        cancelled_headers = {"X-Quiz-Token": cancelled_join.json()["participant_token"]}
        cancelled = client.post(
            f"/api/quizzes/sessions/{cancelled_session['id']}/cancel",
            headers=teacher_headers,
        )
        assert cancelled.status_code == 204
        cancelled_student_state = client.get(
            f"/api/quizzes/student/sessions/{cancelled_session['join_code']}",
            headers=cancelled_headers,
        )
        assert cancelled_student_state.status_code == 401
        assert cancelled_session["id"] not in {
            item["id"]
            for item in client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
        }
        assert (
            client.get(
                f"/api/quizzes/sessions/{cancelled_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        expiring_launch = client.post(
            f"/api/quizzes/{quiz['id']}/launch",
            headers=teacher_headers,
            json={"class_id": student_class["id"]},
        )
        assert expiring_launch.status_code == 201
        expiring_session = expiring_launch.json()
        expiring_join = client.post(
            "/api/quizzes/join",
            headers=exam_account_headers,
            json={"join_code": expiring_session["join_code"]},
        )
        assert expiring_join.status_code == 201
        assert (
            client.post(
                f"/api/quizzes/sessions/{expiring_session['id']}/start",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        with database_connection(tmp_path / "test.db") as connection:
            connection.execute(
                "UPDATE quiz_sessions SET started_at = %s WHERE id = %s",
                ("2000-01-01 00:00:00", expiring_session["id"]),
            )
            connection.commit()

        expire_due_sessions(client)
        expired_session_details = client.get(
            f"/api/quizzes/sessions/{expiring_session['id']}",
            headers=teacher_headers,
        )
        assert expired_session_details.status_code == 200
        assert expired_session_details.json()["status"] == "finished"

        results_after_expiry = client.get(
            "/api/quizzes/sessions/results",
            headers=teacher_headers,
        )
        assert results_after_expiry.status_code == 200
        assert expiring_session["id"] not in {
            result["id"] for result in results_after_expiry.json()
        }
        assert (
            client.get(
                "/api/quizzes/sessions/active",
                headers=teacher_headers,
            ).json()
            == []
        )
        completed_class = client.get("/api/classes", headers=teacher_headers).json()[0]
        assert completed_class["completed_quiz_count"] == 2
        assert completed_class["latest_quiz_title"] == edited_quiz.json()["title"]
        assert completed_class["latest_quiz_at"] is not None
        assert (
            client.get(student_state_url, headers=student_headers).json()["status"]
            == "finished"
        )
        assert (
            client.delete(
                f"/api/students/{student_account['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        session_after_student_delete = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}",
            headers=teacher_headers,
        ).json()
        assert (
            session_after_student_delete["participants"][0]["student_display_name"]
            == "Martin Giraud"
        )
        assert (
            client.delete(
                f"/api/classes/{student_class['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).json()["class_id"]
            is None
        )
        assert (
            client.delete(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/quizzes/sessions/{quiz_session['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        updated_payload = {
            **question_payload,
            "prompt": "Quelle fraction représente exactement la moitié ?",
            "difficulty": "medium",
            "code_language": "javascript",
            "code_content": "const half = (value) => value / 2;",
            "remove_image": True,
            "choices": [
                {
                    **question_payload["choices"][0],
                    "id": question["choices"][0]["id"],
                    "image": None,
                },
                {
                    **question_payload["choices"][1],
                    "id": question["choices"][1]["id"],
                },
            ],
        }
        updated = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=teacher_headers,
            data={"payload": json.dumps(updated_payload)},
        )
        assert updated.status_code == 200
        assert updated.json()["prompt"] == updated_payload["prompt"]
        assert updated.json()["difficulty"] == "medium"
        assert updated.json()["code_language"] == "javascript"
        assert updated.json()["has_image"] is False
        updated_choice = updated.json()["choices"][0]
        assert updated_choice["has_image"] is True
        assert updated_choice["code_content"] == "print(1 / 2)"
        assert (
            client.get(
                f"/api/question-banks/choices/{updated_choice['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/question-banks/questions/{question['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        deleted_question = client.delete(
            f"/api/question-banks/questions/{question['id']}",
            headers=teacher_headers,
        )
        assert deleted_question.status_code == 204
        assert (
            client.get(
                f"/api/question-banks/{first_bank.json()['id']}/questions",
                headers=teacher_headers,
            ).json()
            == []
        )
        assert (
            client.get(
                f"/api/question-banks/choices/{updated_choice['id']}/image",
                headers=teacher_headers,
            ).status_code
            == 404
        )
        bank_after_question_delete = next(
            bank
            for bank in client.get(
                "/api/question-banks",
                headers=teacher_headers,
            ).json()
            if bank["id"] == first_bank.json()["id"]
        )
        assert bank_after_question_delete["question_count"] == 0
        assert (
            client.delete(
                f"/api/question-banks/questions/{question['id']}",
                headers=teacher_headers,
            ).status_code
            == 404
        )

        disabled = client.post(
            f"/api/admin/users/{created.json()['id']}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False
        assert client.get("/api/users/me", headers=teacher_headers).status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "teacher.one",
                    "password": "another-strong-password",
                    "audience": "professor",
                },
            ).status_code
            == 401
        )
        enabled = client.post(
            f"/api/admin/users/{created.json()['id']}/status",
            headers=headers,
            json={"is_active": True},
        )
        assert enabled.status_code == 200
        assert client.get("/api/users/me", headers=teacher_headers).status_code == 401
        for _ in range(4):
            failed_login = client.post(
                "/api/auth/login",
                json={
                    "username": "teacher.one",
                    "password": "incorrect-password",
                    "audience": "professor",
                },
            )
            assert failed_login.status_code == 401
            assert failed_login.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"
        rate_limited_login = client.post(
            "/api/auth/login",
            json={
                "username": "teacher.one",
                "password": "incorrect-password",
                "audience": "professor",
            },
        )
        assert rate_limited_login.status_code == 429
        assert rate_limited_login.json()["detail"]["code"] == "AUTH_RATE_LIMITED"
        reset_access = client.post(
            f"/api/admin/users/{created.json()['id']}/credentials",
            headers=headers,
            json={
                "password": "replacement-strong-password",
                "reset_two_factor": True,
            },
        )
        assert reset_access.status_code == 200
        recovery_login = client.post(
            "/api/auth/login",
            json={
                "username": "teacher.one",
                "password": "replacement-strong-password",
                "audience": "professor",
            },
        )
        assert recovery_login.status_code == 200
        assert recovery_login.json()["status"] == "setup_required"
