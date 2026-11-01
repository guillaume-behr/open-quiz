"""Question bank paths outside the main flows."""

import json
from base64 import b64encode
from pathlib import Path
from typing import Any

import pytest

from app.models import MakeupSession, QuizSession, QuizSessionQuestion
from app.routers import question_bank_transfer, question_banks

from support import (
    VALID_PNG,
    exam_environment,
    make_client,
    settings_for,
)


def question_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "prompt": "Two plus two?",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [
            {"label": "Four", "is_correct": True},
            {"label": "Five", "is_correct": False},
        ],
        **overrides,
    }


def png_image() -> dict[str, str]:
    return {"content_type": "image/png", "data_base64": b64encode(VALID_PNG).decode()}


@pytest.fixture
def environment(tmp_path: Path):
    with make_client(settings_for(tmp_path / "question-banks")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        environment["bank_id"] = environment["question"]["question_bank_id"]
        yield environment


def test_question_bank_listing_and_updates(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    bank_id = environment["bank_id"]

    other = client.post(
        "/api/question-banks",
        headers=headers,
        json={"grade_level": "4e", "chapter": "Fractions"},
    ).json()
    filtered = client.get(
        "/api/question-banks",
        headers=headers,
        params={"search": "Fraction", "grade_level": "4e"},
    )
    assert [bank["id"] for bank in filtered.json()] == [other["id"]]

    renamed = client.post(
        f"/api/question-banks/{bank_id}/update",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Renamed"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["chapter"] == "Renamed"

    duplicate = client.post(
        f"/api/question-banks/{bank_id}/update",
        headers=headers,
        json={"grade_level": "4e", "chapter": "Fractions"},
    )
    assert duplicate.status_code == 409

    missing = client.post(
        "/api/question-banks/999999/questions",
        headers=headers,
        data={"payload": json.dumps(question_payload())},
    )
    assert missing.status_code == 404


def test_question_images_are_validated(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    url = f"/api/question-banks/{environment['bank_id']}/questions"
    payload = {"payload": json.dumps(question_payload())}

    unsupported = client.post(
        url,
        headers=headers,
        data=payload,
        files={"image": ("image.svg", b"<svg/>", "image/svg+xml")},
    )
    assert unsupported.status_code == 415

    empty = client.post(
        url,
        headers=headers,
        data=payload,
        files={"image": ("image.png", b"", "image/png")},
    )
    assert empty.status_code == 201
    assert empty.json()["has_image"] is False

    corrupted = client.post(
        url,
        headers=headers,
        data=payload,
        files={"image": ("image.png", b"not an image", "image/png")},
    )
    assert corrupted.status_code == 422

    def with_choice_image(data: str) -> dict[str, str]:
        choices = [
            {
                "label": "Four",
                "is_correct": True,
                "image": {"content_type": "image/png", "data_base64": data},
            },
            {"label": "Five", "is_correct": False},
        ]
        return {"payload": json.dumps(question_payload(choices=choices))}

    for data, status_code in [
        ("not base64!", 422),
        (b64encode(b"not an image").decode(), 422),
    ]:
        assert (
            client.post(url, headers=headers, data=with_choice_image(data)).status_code
            == status_code
        )

    monkeypatch.setattr(question_banks, "MAX_IMAGE_BYTES", len(VALID_PNG) - 1)
    too_large = client.post(
        url,
        headers=headers,
        data=payload,
        files={"image": ("image.png", VALID_PNG, "image/png")},
    )
    assert too_large.status_code == 413
    oversized_choice = client.post(
        url, headers=headers, data=with_choice_image(b64encode(VALID_PNG).decode())
    )
    assert oversized_choice.status_code == 422


def test_question_volume_limits(environment, monkeypatch: pytest.MonkeyPatch) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    url = f"/api/question-banks/{environment['bank_id']}/questions"
    choices = [
        {"label": "Four", "is_correct": True, "image": png_image()},
        {"label": "Five", "is_correct": False},
    ]
    payload = {"payload": json.dumps(question_payload(choices=choices))}

    for module in (question_banks, question_bank_transfer):
        monkeypatch.setattr(module, "MAX_IMPORT_IMAGE_BYTES", 1)
    assert client.post(url, headers=headers, data=payload).status_code == 413
    imported = client.post(
        "/api/question-banks/import",
        headers=headers,
        json={
            "version": 1,
            "question_bank": {"grade_level": "5e", "chapter": "Imported"},
            "questions": [question_payload(choices=choices)],
        },
    )
    assert imported.status_code == 413

    monkeypatch.setattr(question_banks, "MAX_QUESTIONS_PER_BANK", 1)
    full = client.post(
        url, headers=headers, data={"payload": json.dumps(question_payload())}
    )
    assert full.status_code == 409


def test_a_choice_needs_content_even_when_it_names_an_id(environment) -> None:
    client = environment["client"]
    response = client.post(
        f"/api/question-banks/{environment['bank_id']}/questions",
        headers=environment["teacher_headers"],
        data={
            "payload": json.dumps(
                question_payload(
                    choices=[
                        {"id": 1, "label": "", "is_correct": True},
                        {"label": "Five", "is_correct": False},
                    ]
                )
            )
        },
    )
    assert response.status_code == 422
    assert "texte, une image ou du code" in response.json()["detail"]


def test_question_updates_cover_every_branch(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    url = f"/api/question-banks/questions/{question['id']}/update"
    kept, removed = question["choices"]

    invalid = client.post(url, headers=headers, data={"payload": "{not json"})
    assert invalid.status_code == 422

    unknown_choice = question_payload(
        choices=[
            {"id": 999999, "label": "Four", "is_correct": True},
            {"label": "Five", "is_correct": False},
        ]
    )
    assert (
        client.post(
            url, headers=headers, data={"payload": json.dumps(unknown_choice)}
        ).status_code
        == 422
    )

    blank_choice = question_payload(
        choices=[
            {"id": kept["id"], "label": "", "is_correct": True},
            {"label": "Five", "is_correct": False},
        ]
    )
    assert (
        client.post(
            url, headers=headers, data={"payload": json.dumps(blank_choice)}
        ).status_code
        == 422
    )

    with_image = client.post(
        url,
        headers=headers,
        data={
            "payload": json.dumps(
                question_payload(
                    choices=[
                        {"id": kept["id"], "label": "Two", "is_correct": True},
                        {"label": "Six", "is_correct": False},
                    ]
                )
            )
        },
        files={"image": ("image.png", VALID_PNG, "image/png")},
    )
    assert with_image.status_code == 200
    updated = with_image.json()
    assert updated["has_image"] is True
    assert kept["id"] in [choice["id"] for choice in updated["choices"]]
    assert removed["id"] not in [choice["id"] for choice in updated["choices"]]

    monkeypatch.setattr(question_banks, "MAX_IMPORT_IMAGE_BYTES", 1)
    too_large = client.post(
        url,
        headers=headers,
        data={"payload": json.dumps(question_payload())},
    )
    assert too_large.status_code == 413


def test_shared_draw_questions_cannot_be_deleted_and_regrade_makeups(
    environment,
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    student_class = environment["student_class"]
    with client.app.state.session_factory() as session:
        owner_id = client.get("/api/users/me", headers=headers).json()["id"]
        makeup = MakeupSession(
            owner_id=owner_id,
            class_id=student_class["id"],
            class_name=student_class["name"],
            join_code="MAKEUP02",
            status="finished",
        )
        session.add(makeup)
        session.flush()
        child = QuizSession(
            quiz_id=environment["quiz"]["id"],
            class_id=student_class["id"],
            class_name=student_class["name"],
            join_code="CHILD002",
            status="finished",
            makeup_session_id=makeup.id,
        )
        session.add(child)
        session.flush()
        session.add(
            QuizSessionQuestion(
                session_id=child.id, question_id=question["id"], position=0
            )
        )
        session.commit()

    refused = client.delete(
        f"/api/question-banks/questions/{question['id']}", headers=headers
    )
    assert refused.status_code == 409

    regraded = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={
            "payload": json.dumps(
                question_payload(
                    choices=[
                        {"id": choice["id"], "label": choice["label"], **flags}
                        for choice, flags in zip(
                            question["choices"],
                            [{"is_correct": True}, {"is_correct": False}],
                            strict=True,
                        )
                    ]
                )
            )
        },
    )
    assert regraded.status_code == 200
