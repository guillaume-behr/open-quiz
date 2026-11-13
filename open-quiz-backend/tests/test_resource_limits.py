"""Slow work must not hold a database connection, and a full pool answers 503."""

import json
from base64 import b64encode
from pathlib import Path
from threading import Event, Semaphore, Thread

import pytest

from app import images, question_records, security
from app.routers import questions

from support import VALID_PNG, exam_environment, make_client, settings_for


def question_payload(prompt: str, *, choice_image: bool = False) -> dict:
    return {
        "prompt": prompt,
        "difficulty": "easy",
        "answer_mode": "single",
        "answer_mode_disclosed": True,
        "choices": [
            {
                "label": "Yes",
                "is_correct": True,
                "points": 1,
                **(
                    {
                        "image": {
                            "content_type": "image/png",
                            "data_base64": b64encode(VALID_PNG).decode(),
                        }
                    }
                    if choice_image
                    else {}
                ),
            },
            {"label": "No", "is_correct": False, "points": 0},
        ],
    }


def test_an_exhausted_pool_answers_503_with_a_code(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "exhausted-pool",
        database_pool_size=1,
        database_max_overflow=0,
        database_pool_timeout_seconds=1,
    )
    with make_client(settings) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        engine = client.app.state.session_factory.kw["bind"]
        assert engine.pool.size() == 1
        with engine.connect():
            listed = client.get("/api/question-banks", headers=headers)
            # The body limit checks the teacher before the route, outside it.
            created = client.post(
                f"/api/question-banks/{bank_id}/questions",
                headers=headers,
                data={"payload": json.dumps(question_payload("Busy"))},
            )
        for response in (listed, created):
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "SERVER_BUSY"
            assert response.headers["Retry-After"]
        assert client.get("/api/question-banks", headers=headers).status_code == 200


def test_pool_settings_are_bounded(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="DATABASE_POOL_SIZE"):
        settings_for(tmp_path / "pool-bounds", database_pool_size=0)
    with pytest.raises(ValueError, match="DATABASE_POOL_TIMEOUT_SECONDS"):
        settings_for(tmp_path / "pool-bounds", database_pool_timeout_seconds=0)


def test_images_decode_without_holding_a_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings_for(tmp_path / "decode-connection")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        pool = client.app.state.session_factory.kw["bind"].pool
        checked_out: list[int] = []
        normalize = images.normalize_image

        def recording_normalize(data: bytes, declared_type: str):
            checked_out.append(pool.checkedout())
            return normalize(data, declared_type)

        monkeypatch.setattr(questions, "normalize_image", recording_normalize)
        monkeypatch.setattr(question_records, "normalize_image", recording_normalize)

        created = client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=headers,
            data={
                "payload": json.dumps(question_payload("Pictured", choice_image=True))
            },
            files={"image": ("image.png", VALID_PNG, "image/png")},
        )
        assert created.status_code == 201
        imported = client.post(
            "/api/question-banks/import",
            headers=headers,
            json={
                "version": 1,
                "question_bank": {"grade_level": "5e", "chapter": "Imported"},
                "questions": [question_payload("Imported", choice_image=True)],
            },
        )
        assert imported.status_code == 201
        assert checked_out == [0, 0, 0]


def test_a_full_bank_is_checked_again_after_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bank is no longer locked while its images decode."""
    with make_client(settings_for(tmp_path / "bank-filled-meanwhile")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        normalize = images.normalize_image

        def filling_normalize(data: bytes, declared_type: str):
            monkeypatch.setattr(questions, "MAX_QUESTIONS_PER_BANK", 1)
            return normalize(data, declared_type)

        monkeypatch.setattr(questions, "normalize_image", filling_normalize)
        created = client.post(
            f"/api/question-banks/{bank_id}/questions",
            headers=headers,
            data={"payload": json.dumps(question_payload("Too many"))},
            files={"image": ("image.png", VALID_PNG, "image/png")},
        )
        assert created.status_code == 409
        assert created.json()["detail"]["code"] == "QUESTION_BANK_FULL"


def test_a_busy_image_decoder_answers_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(images, "IMAGE_DECODING_WAIT_SECONDS", 0.05)
    with make_client(settings_for(tmp_path / "busy-decoder")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        bank_id = environment["question"]["question_bank_id"]
        for _ in range(images.MAX_CONCURRENT_IMAGE_DECODES):
            images.image_decoding.acquire()
        try:
            created = client.post(
                f"/api/question-banks/{bank_id}/questions",
                headers=headers,
                data={"payload": json.dumps(question_payload("Waiting"))},
                files={"image": ("image.png", VALID_PNG, "image/png")},
            )
            imported = client.post(
                "/api/question-banks/import",
                headers=headers,
                json={
                    "version": 1,
                    "question_bank": {"grade_level": "5e", "chapter": "Waiting"},
                    "questions": [question_payload("Waiting", choice_image=True)],
                },
            )
        finally:
            for _ in range(images.MAX_CONCURRENT_IMAGE_DECODES):
                images.image_decoding.release()
        for response in (created, imported):
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "SERVER_BUSY"
            assert response.headers["Retry-After"]


def test_class_imports_hash_without_holding_a_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings_for(tmp_path / "import-hashing")) as client:
        environment = exam_environment(client)
        pool = client.app.state.session_factory.kw["bind"].pool
        checked_out: list[int] = []
        hash_password = security.password_hash.hash

        def recording_hash(password: str) -> str:
            checked_out.append(pool.checkedout())
            return hash_password(password)

        monkeypatch.setattr(security.password_hash, "hash", recording_hash)
        imported = client.post(
            "/api/classes/import",
            headers=environment["teacher_headers"],
            json={
                "classes": [
                    {
                        "name": "Imported",
                        "grade_level": "5e",
                        "students": [
                            {"identifier": f"pupil.{index}", "display_name": "Pupil"}
                            for index in range(3)
                        ],
                    }
                ]
            },
        )
        assert imported.status_code == 201
        assert imported.json()["student_count"] == 3
        assert checked_out == [0, 0, 0]


def test_bulk_hashing_leaves_a_slot_for_sign_ins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = Event()
    entered = Semaphore(0)
    hash_password = security.password_hash.hash

    def slow_hash(password: str) -> str:
        if password.startswith("bulk"):
            entered.release()
            release.wait(10)
        return hash_password(password)

    monkeypatch.setattr(security.password_hash, "hash", slow_hash)
    imports = [
        Thread(target=security.hash_passwords, args=([f"bulk-{index}"],))
        for index in range(security.MAX_CONCURRENT_PASSWORD_HASHES)
    ]
    for thread in imports:
        thread.start()
    try:
        for _ in range(security.MAX_CONCURRENT_PASSWORD_HASHES - 1):
            assert entered.acquire(timeout=10)
        # The last import waits for a bulk slot...
        assert not entered.acquire(timeout=0.2)
        # ...while a sign-in still finds a hashing slot.
        hashed: list[str] = []
        sign_in = Thread(target=lambda: hashed.append(security.hash_password("x")))
        sign_in.start()
        sign_in.join(timeout=10)
        assert hashed
    finally:
        release.set()
        for thread in imports:
            thread.join(timeout=10)
    assert entered.acquire(timeout=0)
