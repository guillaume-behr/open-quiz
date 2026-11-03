"""Question images live in stored_images, once per distinct content."""

import json
from pathlib import Path
from threading import Thread
from time import sleep

from sqlalchemy import event, func, select, update

import main
from app.models import Question, StoredImage
from app.stored_images import delete_unreferenced_images

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


def test_purging_skips_an_image_a_concurrent_save_reuses(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "stored-images-race")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        created = client.post(
            f"/api/question-banks/{environment['question']['question_bank_id']}/questions",
            headers=headers,
            data={"payload": question_payload("Illustrated")},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        ).json()
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            question = session.get(Question, created["id"])
            digest = question.image_sha256
            question.image_sha256 = None
            session.commit()

        # A save reuses the now unreferenced image and holds its row lock
        # while the purge runs.
        with session_factory() as saving, session_factory() as purging:
            saving.execute(
                update(Question)
                .where(Question.id == created["id"])
                .values(image_sha256=digest)
            )
            purged: list[int] = []
            purge = Thread(
                target=lambda: purged.append(delete_unreferenced_images(purging))
            )
            purge.start()
            sleep(0.3)
            saving.commit()
            purge.join(timeout=10)
            assert purged == [0]
            # The rest of the purging transaction is still usable.
            purging.execute(select(1))
            purging.commit()
        assert stored_image_count(client) == 1


def test_exporting_a_bank_streams_every_question_and_its_image(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "stored-images-export")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        for prompt, image in (("Pictured", True), ("Plain", False), ("Also", True)):
            client.post(
                f"/api/question-banks/{bank_id}/questions",
                headers=headers,
                data={"payload": question_payload(prompt)},
                files={"image": ("image.png", VALID_PNG, "image/png")}
                if image
                else None,
            )
        exported = client.get(f"/api/question-banks/{bank_id}/export", headers=headers)
        assert exported.status_code == 200
        questions = exported.json()["questions"]
        assert [question["prompt"] for question in questions][-3:] == [
            "Pictured",
            "Plain",
            "Also",
        ]
        images = [question["image"] for question in questions[-3:]]
        assert images[1] is None
        assert images[0] == images[2]
        assert images[0]["content_type"] == "image/png"
