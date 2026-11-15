"""Score totals are reported to two decimals, never as a long float sum."""

import csv
import io
import json
from pathlib import Path
from typing import Any

from support import (
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


def add_question(
    client: Any, headers: dict[str, str], bank_id: int, prompt: str, choices: list
) -> dict[str, Any]:
    created = client.post(
        f"/api/question-banks/{bank_id}/questions",
        headers=headers,
        data={
            "payload": json.dumps(
                {
                    "prompt": prompt,
                    "difficulty": "easy",
                    "answer_mode": "single",
                    "answer_mode_disclosed": True,
                    "choices": choices,
                }
            )
        },
    )
    assert created.status_code == 201
    return created.json()


def test_totals_never_carry_float_noise(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "rounding")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank = client.post(
            "/api/question-banks",
            headers=headers,
            json={"grade_level": "5e", "chapter": "Rounding"},
        ).json()
        questions = [
            add_question(
                client,
                headers,
                bank["id"],
                "Tenth",
                [
                    {"label": "Yes", "is_correct": True, "points": 0.1},
                    {"label": "No", "is_correct": False},
                ],
            ),
            add_question(
                client,
                headers,
                bank["id"],
                "Fifth",
                [
                    {"label": "Yes", "is_correct": True, "points": 0.2},
                    {"label": "No", "is_correct": False},
                ],
            ),
            # A third of a point, as the editor's default split stores it.
            add_question(
                client,
                headers,
                bank["id"],
                "Third",
                [
                    {"label": "Yes", "is_correct": True, "points": 1 / 3},
                    {"label": "No", "is_correct": False},
                ],
            ),
        ]
        quiz = client.post(
            "/api/quizzes",
            headers=headers,
            json={
                "title": "Rounding quiz",
                "question_bank_ids": [bank["id"]],
                "easy_question_count": 3,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        ).json()
        environment["quiz"] = quiz
        quiz_session, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=headers,
            ).status_code
            == 200
        )
        student_url = f"/api/quizzes/student/sessions/{quiz_session['join_code']}"
        for _ in questions:
            state = client.get(student_url, headers=participant_headers).json()
            # Every question's right answer is labelled "Yes".
            correct = next(
                choice["id"]
                for choice in state["question"]["choices"]
                if choice["label"] == "Yes"
            )
            assert (
                client.post(
                    f"{student_url}/answer",
                    headers=participant_headers,
                    json={
                        "question_id": state["question"]["id"],
                        "selected_choice_ids": [correct],
                    },
                ).status_code
                == 200
            )
        hand_in_quiz(client, quiz_session["join_code"], participant_headers)

        # 0.1 + 0.2 + 0.33, which a float sum reports as 0.6300000000000001.
        results = client.get("/api/quizzes/sessions/results", headers=headers).json()
        participant = results[0]["participants"][0]
        assert participant["score"] == 0.63
        assert participant["maximum_score"] == 0.63
        assert results[0]["median_maximum_score"] == 0.63

        session_view = client.get(
            f"/api/quizzes/sessions/{quiz_session['id']}", headers=headers
        ).json()
        assert session_view["participants"][0]["score"] == 0.63

        export = client.get(
            "/api/quizzes/sessions/results/export",
            headers=headers,
            params={"class_id": environment["student_class"]["id"]},
        )
        rows = list(csv.DictReader(io.StringIO(export.text.lstrip("﻿"))))
        assert rows[0]["score"] == "0.63"

        history = client.get(
            "/api/quizzes/student/results",
            headers=environment["student_headers"],
        ).json()[0]
        assert history["score"] == 0.63
        assert history["maximum_score"] == 0.63
        assert sorted(answer["max_score"] for answer in history["answers"]) == [
            0.1,
            0.2,
            0.33,
        ]
