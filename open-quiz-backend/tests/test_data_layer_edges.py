"""Question limit under concurrency, imported names, class import budget."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import OperationalError

from app.models import Question
from app.schemas import MAX_QUESTIONS_PER_BANK

from support import (
    concurrent_writes,
    create_professor,
    exam_environment,
    login_admin,
    make_client,
    settings_for,
)

CHOICE_QUESTION = json.dumps(
    {
        "prompt": "Last one?",
        "points": 1,
        "difficulty": "easy",
        "answer_mode": "single",
        "answer_mode_disclosed": True,
        "choices": [
            {"label": "Yes", "is_correct": True, "points": 1},
            {"label": "No", "is_correct": False, "points": 0},
        ],
    }
)


def question_row(bank_id: int, prompt: str) -> dict[str, Any]:
    return {
        "question_bank_id": bank_id,
        "prompt": prompt,
        "difficulty": "easy",
        "answer_mode": "single",
        "correction_mode": "automatic",
    }


def test_the_question_limit_holds_against_a_concurrent_create(tmp_path: Path) -> None:
    """A create counting the bank's questions keeps others out until it commits."""
    with make_client(settings_for(tmp_path / "question-limit-race")) as client:
        environment = exam_environment(client)
        bank_id = environment["question"]["question_bank_id"]
        engine = client.app.state.session_factory.kw["bind"]
        with engine.begin() as connection:
            existing = connection.scalar(
                select(func.count()).where(Question.question_bank_id == bank_id)
            )
            connection.execute(
                insert(Question),
                [
                    question_row(bank_id, f"Filler {number}")
                    for number in range(MAX_QUESTIONS_PER_BANK - 1 - existing)
                ],
            )

        blocked: list[bool] = []

        def concurrent_create(connection: Any) -> None:
            connection.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                with connection.begin_nested():
                    connection.execute(
                        insert(Question).values(**question_row(bank_id, "Racer"))
                    )
            except OperationalError:
                blocked.append(True)

        with concurrent_writes(
            client, ("INSERT INTO questions", concurrent_create)
        ) as fired:
            created = client.post(
                f"/api/question-banks/{bank_id}/questions",
                headers=environment["teacher_headers"],
                data={"payload": CHOICE_QUESTION},
            )
        assert fired
        assert created.status_code == 201
        assert blocked == [True]
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count()).where(Question.question_bank_id == bank_id)
                )
                == MAX_QUESTIONS_PER_BANK
            )


def test_an_imported_name_of_only_spaces_is_refused(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "blank-import-name")) as client:
        _, headers = create_professor(client, login_admin(client))
        imported = client.post(
            "/api/classes/import",
            headers=headers,
            json={
                "classes": [
                    {
                        "name": "Blank",
                        "grade_level": "Tle",
                        "students": [
                            {"identifier": "blank.name", "display_name": "   "}
                        ],
                    }
                ]
            },
        )
        assert imported.status_code == 422
        assert "display_name" in json.dumps(imported.json())


def test_class_imports_are_rate_limited_per_teacher(tmp_path: Path) -> None:
    """Imports answer whether identifiers exist: bulk probing is bounded."""
    settings = settings_for(tmp_path / "import-budget", class_import_attempts=1)
    with make_client(settings) as client:
        admin_headers = login_admin(client)
        _, first = create_professor(client, admin_headers, username="first.teacher")
        _, second = create_professor(client, admin_headers, username="second.teacher")

        def import_class(headers: dict[str, str], name: str) -> Any:
            return client.post(
                "/api/classes/import",
                headers=headers,
                json={
                    "classes": [{"name": name, "grade_level": "Tle", "students": []}]
                },
            )

        assert import_class(first, "A").status_code == 201
        limited = import_class(first, "B")
        assert limited.status_code == 429
        assert limited.json()["detail"]["code"] == "CLASS_IMPORT_RATE_LIMITED"
        assert int(limited.headers["retry-after"]) > 0
        assert import_class(second, "A").status_code == 201
