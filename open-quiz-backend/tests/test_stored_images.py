"""Question images live in stored_images, once per distinct content."""

import json
from collections.abc import Callable
from base64 import b64decode, b64encode
from hashlib import sha256
from pathlib import Path
from threading import Thread
from time import sleep

from sqlalchemy import event, func, select, update

from app import maintenance
from app.models import Question, StoredImage
from app.stored_images import delete_unreferenced_images, store_image

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
        maintenance.enforce_data_retention(session_factory, settings)
        assert stored_image_count(client) == 1
        image = client.get(
            f"/api/question-banks/questions/{created[1]['id']}/image", headers=headers
        )
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"

        client.delete(
            f"/api/question-banks/questions/{created[1]['id']}", headers=headers
        )
        maintenance.enforce_data_retention(session_factory, settings)
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


def test_reusing_an_image_keeps_it_from_a_concurrent_purge(tmp_path: Path) -> None:
    """The other order: the save stores the image first, then the purge runs.

    Storing an image that already exists must lock its row until the save
    commits, or the purge deletes it and the save fails on the foreign key.
    """
    with make_client(settings_for(tmp_path / "stored-images-reuse")) as client:
        environment = exam_environment(client)
        created = client.post(
            f"/api/question-banks/{environment['question']['question_bank_id']}/questions",
            headers=environment["teacher_headers"],
            data={"payload": question_payload("Illustrated")},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        ).json()
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            question = session.get(Question, created["id"])
            digest = question.image_sha256
            stored = session.get(StoredImage, digest)
            data, content_type = stored.data, stored.content_type
            question.image_sha256 = None
            session.commit()

        with session_factory() as saving, session_factory() as purging:
            assert store_image(saving, data, content_type) == digest
            purged: list[int] = []

            def purge() -> None:
                purged.append(delete_unreferenced_images(purging))
                purging.commit()

            purger = Thread(target=purge)
            purger.start()
            sleep(0.3)
            saving.execute(
                update(Question)
                .where(Question.id == created["id"])
                .values(image_sha256=digest)
            )
            saving.commit()
            purger.join(timeout=10)
            assert purged == [0]
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


def record_statements(client) -> tuple[list[str], Callable[[], None]]:
    engine = client.app.state.session_factory.kw["bind"]
    statements: list[str] = []

    def record(_connection, _cursor, statement, *_: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    return statements, lambda: event.remove(engine, "before_cursor_execute", record)


def test_images_are_revalidated_by_their_hash_without_loading_them(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "stored-images-etag")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        payload = json.loads(question_payload("Pictured"))
        payload["choices"][0]["image"] = {
            "content_type": "image/png",
            "data_base64": b64encode(VALID_PNG).decode(),
        }
        created = client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=headers,
            data={"payload": json.dumps(payload)},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        ).json()
        choice_id = next(
            choice["id"] for choice in created["choices"] if choice["has_image"]
        )
        for url in (
            f"/api/question-banks/questions/{created['id']}/image",
            f"/api/question-banks/choices/{choice_id}/image",
        ):
            served = client.get(url, headers=headers)
            assert served.status_code == 200
            etag = served.headers["ETag"]
            assert etag == f'"{sha256(served.content).hexdigest()}"'
            assert "no-store" not in served.headers["Cache-Control"]
            assert "private" in served.headers["Cache-Control"]

            statements, stop = record_statements(client)
            try:
                revalidated = client.get(
                    url, headers={**headers, "If-None-Match": etag}
                )
            finally:
                stop()
            assert revalidated.status_code == 304
            assert revalidated.content == b""
            assert revalidated.headers["ETag"] == etag
            assert statements
            assert not [
                statement for statement in statements if "stored_images" in statement
            ]
            changed = client.get(url, headers={**headers, "If-None-Match": '"other"'})
            assert changed.status_code == 200
            assert changed.content == served.content
        # Other API responses stay out of every cache.
        listed = client.get(f"/api/question-banks/{bank_id}/questions", headers=headers)
        assert listed.headers["Cache-Control"] == "no-store"


def test_exporting_a_bank_takes_as_many_queries_whatever_its_size(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "stored-images-export-n1")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        query_counts = []
        for size in (1, 4):
            bank = client.post(
                "/api/question-banks",
                headers=headers,
                json={"grade_level": "5e", "chapter": f"Size {size}"},
            ).json()
            for index in range(size):
                payload = json.loads(question_payload(f"Question {index}"))
                payload["code_language"] = "python"
                payload["code_content"] = "print(1)"
                assert (
                    client.post(
                        f"/api/question-banks/{bank['id']}/questions",
                        headers=headers,
                        data={"payload": json.dumps(payload)},
                    ).status_code
                    == 201
                )
            statements, stop = record_statements(client)
            try:
                exported = client.get(
                    f"/api/question-banks/{bank['id']}/export", headers=headers
                )
            finally:
                stop()
            assert exported.status_code == 200
            questions = exported.json()["questions"]
            assert len(questions) == size
            assert all(question["code_content"] == "print(1)" for question in questions)
            assert all(len(question["choices"]) == 2 for question in questions)
            query_counts.append(len(statements))
        assert query_counts[0] == query_counts[1]


def test_exporting_releases_the_request_connection_while_streaming(
    tmp_path: Path,
) -> None:
    settings = settings_for(
        tmp_path / "stored-images-export-pool",
        database_pool_size=1,
        database_max_overflow=0,
        database_pool_timeout_seconds=2,
    )
    with make_client(settings) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=headers,
            data={"payload": question_payload("Pictured")},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        )
        exported = client.get(f"/api/question-banks/{bank_id}/export", headers=headers)
        assert exported.status_code == 200
        questions = exported.json()["questions"]
        assert [question["prompt"] for question in questions] == [
            "One plus one?",
            "Pictured",
        ]
        assert b64decode(questions[1]["image"]["data_base64"]).startswith(b"\x89PNG")
