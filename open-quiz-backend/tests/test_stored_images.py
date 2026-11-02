"""Question images live in stored_images, once per distinct content."""

import json
from pathlib import Path

from sqlalchemy import event, func, select

import main
from app.models import StoredImage

from support import VALID_PNG, exam_environment, make_client, settings_for


def question_payload(prompt: str) -> str:
    return json.dumps(
        {
            "prompt": prompt,
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


def stored_image_count(client) -> int:
    with client.app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(StoredImage))


def test_an_image_used_twice_is_stored_once_and_purged_when_unused(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "stored-images")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        url = f"/api/question-banks/{environment['question']['question_bank_id']}/questions"
        created = [
            client.post(
                url,
                headers=headers,
                data={"payload": question_payload(prompt)},
                files={"image": ("image.png", VALID_PNG, "image/png")},
            ).json()
            for prompt in ("First illustrated", "Second illustrated")
        ]
        assert all(question["has_image"] for question in created)
        assert stored_image_count(client) == 1

        settings = client.app.state.settings
        session_factory = client.app.state.session_factory
        client.delete(
            f"/api/question-banks/questions/{created[0]['id']}", headers=headers
        )
        main.enforce_data_retention(session_factory, settings)
        assert stored_image_count(client) == 1
        image = client.get(
            f"/api/question-banks/questions/{created[1]['id']}/image", headers=headers
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

        client.delete(
            f"/api/question-banks/questions/{created[1]['id']}", headers=headers
        )
        main.enforce_data_retention(session_factory, settings)
        assert stored_image_count(client) == 0


def test_listing_a_bank_transfers_no_image(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "stored-images-list")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        for prompt in ("One", "Two", "Three"):
            client.post(
                f"/api/question-banks/{bank_id}/questions",
                headers=headers,
                data={"payload": question_payload(prompt)},
                files={"image": ("image.png", VALID_PNG, "image/png")},
            )
        engine = client.app.state.session_factory.kw["bind"]
        statements: list[str] = []

        def record(_connection, _cursor, statement, *_: object) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            listed = client.get(
                f"/api/question-banks/{bank_id}/questions", headers=headers
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert listed.status_code == 200
        assert sum(question["has_image"] for question in listed.json()) == 3
        assert statements
        assert not [
            statement for statement in statements if "stored_images" in statement
        ]
