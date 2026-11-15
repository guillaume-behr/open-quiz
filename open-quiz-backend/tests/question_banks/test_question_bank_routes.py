"""Question banks and questions: validation, images and regrading."""

import io
import json
import os
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import delete, event, select, text
from sqlalchemy.exc import OperationalError

from app.domain.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DIMENSION,
    InvalidImageError,
    image_pixel_count,
    normalize_image,
)
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)
from app.records import question_history
from app.records import questions as question_records
from app.routers.question_banks import questions
from app.routers.question_banks import transfer as question_bank_transfer
from app.schemas.questions import (
    QuestionBatchImport,
    QuestionChoiceCreate,
    QuestionCreate,
)
from app.services import maintenance

from support import (
    VALID_PNG,
    choice_answer,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
    training_banks,
    wrong_choice_id,
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
    assert unsupported.json()["detail"]["code"] == "IMAGE_TYPE_UNSUPPORTED"

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
    assert corrupted.json()["detail"]["code"] == "IMAGE_INVALID"

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

    # The question image is checked in the router, choice images on creation.
    for module in (questions, question_records):
        monkeypatch.setattr(module, "MAX_IMAGE_BYTES", len(VALID_PNG) - 1)
    too_large = client.post(
        url,
        headers=headers,
        data=payload,
        files={"image": ("image.png", VALID_PNG, "image/png")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "IMAGE_TOO_LARGE"
    oversized_choice = client.post(
        url, headers=headers, data=with_choice_image(b64encode(VALID_PNG).decode())
    )
    assert oversized_choice.status_code == 422
    assert oversized_choice.json()["detail"]["code"] == "IMAGE_INVALID"


def test_question_volume_limits(environment, monkeypatch: pytest.MonkeyPatch) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    url = f"/api/question-banks/{environment['bank_id']}/questions"
    choices = [
        {"label": "Four", "is_correct": True, "image": png_image()},
        {"label": "Five", "is_correct": False},
    ]
    payload = {"payload": json.dumps(question_payload(choices=choices))}

    for module in (questions, question_bank_transfer):
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
    assert imported.json()["detail"]["code"] == "IMPORT_IMAGES_TOO_LARGE"

    monkeypatch.setattr(questions, "MAX_QUESTIONS_PER_BANK", 1)
    full = client.post(
        url, headers=headers, data={"payload": json.dumps(question_payload())}
    )
    assert full.status_code == 409
    assert full.json()["detail"]["code"] == "QUESTION_BANK_FULL"


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
    assert response.json()["detail"]["code"] == "CHOICE_CONTENT_REQUIRED"
    assert "texte, une image ou du code" in response.json()["detail"]["message"]


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

    monkeypatch.setattr(questions, "MAX_IMPORT_IMAGE_BYTES", 1)
    too_large = client.post(
        url,
        headers=headers,
        data={"payload": json.dumps(question_payload())},
    )
    assert too_large.status_code == 413


def test_shared_draw_questions_regrade_makeups_and_are_detached_on_deletion(
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

    # The make-up drew it: deleting it detaches it instead.
    assert (
        client.delete(
            f"/api/question-banks/questions/{question['id']}", headers=headers
        ).status_code
        == 204
    )
    with client.app.state.session_factory() as session:
        detached = session.get(Question, question["id"])
        assert detached is not None
        assert detached.question_bank_id is None


def test_question_batch_import_has_a_fixed_question_limit() -> None:
    question = {
        "prompt": "Question",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [{"label": "Answer", "is_correct": True}],
    }

    with pytest.raises(ValidationError):
        QuestionBatchImport.model_validate(
            {
                "version": 1,
                "question_bank": {"grade_level": "2de", "chapter": "Limits"},
                "questions": [question] * 501,
            }
        )


def test_written_answer_mode_cannot_claim_to_be_hidden() -> None:
    with pytest.raises(ValidationError):
        QuestionBatchImport.model_validate(
            {
                "version": 1,
                "question_bank": {"grade_level": "2de", "chapter": "Hidden"},
                "questions": [
                    {
                        "prompt": "Explain",
                        "difficulty": "easy",
                        "answer_mode": "written",
                        "answer_mode_disclosed": False,
                        "choices": [{"label": "Expected", "is_correct": True}],
                    }
                ],
            }
        )


def test_question_choices_reject_repeated_existing_ids() -> None:
    with pytest.raises(ValidationError):
        QuestionCreate(
            prompt="Repeated choice",
            difficulty="easy",
            answer_mode="single",
            choices=[
                QuestionChoiceCreate(id=1, label="First", is_correct=True),
                QuestionChoiceCreate(id=1, label="Repeated"),
            ],
        )


def test_choice_text_is_optional_with_an_image_or_code() -> None:
    image_choice = QuestionChoiceCreate.model_validate(
        {
            "label": "",
            "image": {
                "content_type": "image/png",
                "data_base64": "AA==",
            },
        }
    )
    code_choice = QuestionChoiceCreate.model_validate(
        {
            "label": "",
            "code_language": "python",
            "code_content": "print('answer')",
        }
    )

    assert image_choice.label == ""
    assert code_choice.label == ""
    with pytest.raises(ValidationError):
        QuestionChoiceCreate.model_validate({"label": ""})


def test_hidden_single_choice_mode_is_not_disclosed_or_probeable(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "hidden-answer-mode")) as client:
        environment = exam_environment(client)
        question = environment["question"]
        hidden = client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=environment["teacher_headers"],
            data={
                "payload": json.dumps(
                    {
                        "prompt": question["prompt"],
                        "difficulty": question["difficulty"],
                        "answer_mode": "single",
                        "answer_mode_disclosed": False,
                        "choices": [
                            {
                                "id": choice["id"],
                                "label": choice["label"],
                                "is_correct": choice["is_correct"],
                                "points": choice["points"],
                            }
                            for choice in question["choices"]
                        ],
                    }
                )
            },
        )
        assert hidden.status_code == 200
        environment["question"] = hidden.json()
        launched, participant_headers = launch_and_join(client, environment)
        assert (
            client.post(
                f"/api/quizzes/sessions/{launched['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        student_state_url = f"/api/quizzes/student/sessions/{launched['join_code']}"
        state = client.get(student_state_url, headers=participant_headers)
        assert state.status_code == 200
        assert state.json()["question"]["answer_mode_disclosed"] is False
        assert state.json()["question"]["answer_mode"] == "multiple"

        all_choice_ids = [
            choice["id"] for choice in state.json()["question"]["choices"]
        ]
        submitted = client.post(
            f"{student_state_url}/answer",
            headers=participant_headers,
            json={
                "question_id": state.json()["question"]["id"],
                "selected_choice_ids": all_choice_ids,
            },
        )
        assert submitted.status_code == 200
        participant = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        ).json()["participants"][0]
        assert participant["score"] == 0


@pytest.mark.parametrize(
    ("data", "declared_type"),
    [
        (VALID_PNG, "image/svg+xml"),
        (VALID_PNG, "text/html"),
        (b"", "image/png"),
        (b"not an image at all", "image/png"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png"),
    ],
)
def test_normalize_image_rejects_unsupported_or_invalid_data(
    data: bytes, declared_type: str
) -> None:
    """Only decodable bytes in an allowed format may ever reach the database."""
    with pytest.raises(InvalidImageError):
        normalize_image(data, declared_type)


@pytest.mark.parametrize("disguise", ["BMP", "TIFF", "ICO"])
def test_normalize_image_only_decodes_the_accepted_formats(disguise: str) -> None:
    """A declared type never widens the decoders an upload can reach.

    Pillow reads dozens of formats and picks one from the bytes alone: left
    to itself it would decode this file whatever type the upload claims.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format=disguise)

    with pytest.raises(InvalidImageError):
        normalize_image(buffer.getvalue(), "image/png")
    assert image_pixel_count(buffer.getvalue()) == 0


def test_image_pixel_count_reads_the_size_without_decoding() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (7, 3), (0, 0, 0)).save(buffer, format="PNG")

    assert image_pixel_count(buffer.getvalue()) == 21
    assert image_pixel_count(b"not an image at all") == 0


def test_an_import_may_only_decode_so_many_pixels(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored bytes do not bound the decoding work of an import."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    pixels = image_pixel_count(VALID_PNG)
    batch = {
        "version": 1,
        "question_bank": {"grade_level": "5e", "chapter": "Pixels"},
        "questions": [
            {
                **question_payload(
                    choices=[
                        {"label": "Four", "is_correct": True, "image": png_image()},
                        {"label": "Five", "is_correct": False},
                    ]
                ),
                "image": png_image(),
            }
        ],
    }

    monkeypatch.setattr(question_records, "MAX_IMPORT_IMAGE_PIXELS", 2 * pixels - 1)
    refused = client.post("/api/question-banks/import", headers=headers, json=batch)
    assert refused.status_code == 413
    assert refused.json()["detail"]["code"] == "IMPORT_IMAGES_TOO_LARGE"

    monkeypatch.setattr(question_records, "MAX_IMPORT_IMAGE_PIXELS", 2 * pixels)
    accepted = client.post("/api/question-banks/import", headers=headers, json=batch)
    assert accepted.status_code == 201


def test_normalize_image_rejects_oversized_payloads() -> None:
    with pytest.raises(InvalidImageError):
        normalize_image(b"\x00" * (MAX_IMAGE_BYTES + 1), "image/png")


def test_normalize_image_reencodes_a_valid_png() -> None:
    normalized, content_type = normalize_image(VALID_PNG, "image/png")
    assert content_type == "image/png"
    assert normalized.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    ("declared_type", "magic"),
    [
        ("image/jpeg", b"\xff\xd8\xff"),
        ("image/webp", b"RIFF"),
        ("image/gif", b"\x89PNG"),
    ],
)
def test_normalize_image_reencodes_every_accepted_format(
    declared_type: str, magic: bytes
) -> None:
    """Stored bytes are always the re-encoded image, never what was uploaded.

    Re-encoding is what drops any payload smuggled beside the pixels, so each
    accepted format has to go through it. A GIF is stored as PNG because that
    is what the encoder writes for it.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="PNG")
    normalized, content_type = normalize_image(buffer.getvalue(), declared_type)

    assert normalized.startswith(magic)
    assert content_type == (
        "image/png" if declared_type == "image/gif" else declared_type
    )
    assert normalized != buffer.getvalue()


def test_normalize_image_rejects_images_that_are_too_large_on_screen() -> None:
    """Pixel count is bounded separately from the encoded byte size.

    A highly compressible image can be tiny on the wire and still exhaust
    memory once decoded.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (MAX_IMAGE_DIMENSION + 1, 2), (0, 0, 0)).save(buffer, format="PNG")
    assert len(buffer.getvalue()) < MAX_IMAGE_BYTES

    with pytest.raises(InvalidImageError):
        normalize_image(buffer.getvalue(), "image/png")


def test_update_question_in_used_bank_regrades_affected_sessions(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "regrade-bank.db")) as client:
        environment = exam_environment(client)
        quiz_session, participant_headers = launch_and_join(client, environment)

        assert (
            client.post(
                f"/api/quizzes/sessions/{quiz_session['id']}/start",
                headers=environment["teacher_headers"],
            ).status_code
            == 200
        )

        wrong_choice = next(
            c for c in environment["question"]["choices"] if not c["is_correct"]
        )
        correct_choice = next(
            c for c in environment["question"]["choices"] if c["is_correct"]
        )

        # Student picks the initially wrong choice
        answer_response = client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json=choice_answer(client, participant_headers, wrong_choice["id"]),
        )
        assert answer_response.status_code == 200

        hand_in_quiz(client, quiz_session["join_code"], participant_headers)

        # Initially, student has score 0.0 and max score 2.0
        results = client.get(
            "/api/quizzes/sessions/results",
            headers=environment["teacher_headers"],
        ).json()
        assert len(results) == 1
        assert results[0]["participants"][0]["score"] == 0.0
        assert results[0]["participants"][0]["maximum_score"] == 2.0

        history = client.get(
            "/api/quizzes/student/results",
            headers=environment["student_headers"],
        ).json()
        assert len(history) == 1
        assert history[0]["score"] == 0.0
        assert history[0]["maximum_score"] == 2.0
        assert history[0]["answers"][0]["is_correct"] is False

        # Teacher corrects the question in the question bank:
        # Changes the key so the chosen choice is now correct (3 points),
        # and the other choice is incorrect (0 points).
        updated_payload = {
            "prompt": "One plus one? (Updated)",
            "difficulty": "easy",
            "answer_mode": "single",
            "answer_mode_disclosed": True,
            "choices": [
                {
                    "id": correct_choice["id"],
                    "label": "Two",
                    "is_correct": False,
                    "points": 0.0,
                },
                {
                    "id": wrong_choice["id"],
                    "label": "Three (Corrected)",
                    "is_correct": True,
                    "points": 3.0,
                },
            ],
        }
        update_response = client.post(
            f"/api/question-banks/questions/{environment['question']['id']}/update",
            headers=environment["teacher_headers"],
            data={"payload": json.dumps(updated_payload)},
        )
        assert update_response.status_code == 200

        # Teacher results are regraded: student score is now 3.0, max score is 3.0
        regraded_results = client.get(
            "/api/quizzes/sessions/results",
            headers=environment["teacher_headers"],
        ).json()
        assert regraded_results[0]["participants"][0]["score"] == 3.0
        assert regraded_results[0]["participants"][0]["maximum_score"] == 3.0

        # Student results are regraded: student score is now 3.0 and answer is marked correct
        regraded_history = client.get(
            "/api/quizzes/student/results",
            headers=environment["student_headers"],
        ).json()
        assert regraded_history[0]["score"] == 3.0
        assert regraded_history[0]["maximum_score"] == 3.0
        assert regraded_history[0]["answers"][0]["is_correct"] is True

        # Export CSV reflects the updated score
        export = client.get(
            f"/api/quizzes/sessions/results/export?class_id={environment['student_class']['id']}",
            headers=environment["teacher_headers"],
        )
        assert export.status_code == 200
        assert "3.0" in export.text

        # Deleting the question takes it out of its bank; the finished exam
        # keeps it, with its regraded score and correction.
        delete_response = client.delete(
            f"/api/question-banks/questions/{environment['question']['id']}",
            headers=environment["teacher_headers"],
        )
        assert delete_response.status_code == 204
        assert (
            client.get(
                f"/api/question-banks/{environment['question']['question_bank_id']}"
                "/questions",
                headers=environment["teacher_headers"],
            ).json()
            == []
        )
        assert (
            client.get(
                "/api/quizzes/student/results",
                headers=environment["student_headers"],
            ).json()[0]["answers"]
            == regraded_history[0]["answers"]
        )


def test_listings_return_the_page_holding_a_focused_item(environment) -> None:
    """A client finds a new bank or quiz in one request, whatever its page."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    bank_ids = [
        client.post(
            "/api/question-banks",
            headers=headers,
            json={"grade_level": "5e", "chapter": f"Focus {index:02}"},
        ).json()["id"]
        for index in range(7)
    ]
    focused = client.get(
        "/api/question-banks",
        headers=headers,
        params={"page_size": 3, "search": "Focus", "focus": bank_ids[6]},
    )
    assert focused.headers["X-Page"] == "3"
    assert [bank["id"] for bank in focused.json()] == [bank_ids[6]]
    # A bank outside the filtered list leaves the requested page.
    filtered_out = client.get(
        "/api/question-banks",
        headers=headers,
        params={"page": 2, "page_size": 3, "search": "Focus 0", "focus": 999999},
    )
    assert filtered_out.headers["X-Page"] == "2"

    quiz_ids = [
        client.post(
            "/api/quizzes",
            headers=headers,
            json={
                "title": f"Focus quiz {index}",
                "question_bank_ids": [environment["question"]["question_bank_id"]],
                "easy_question_count": 1,
                "medium_question_count": 0,
                "hard_question_count": 0,
            },
        ).json()["id"]
        for index in range(4)
    ]
    focused_quizzes = client.get(
        "/api/quizzes",
        headers=headers,
        params={"page_size": 2, "search": "Focus quiz", "focus": quiz_ids[3]},
    )
    assert focused_quizzes.headers["X-Page"] == "2"
    assert quiz_ids[3] in [quiz["id"] for quiz in focused_quizzes.json()]
    missing_quiz = client.get("/api/quizzes", headers=headers, params={"focus": 999999})
    assert missing_quiz.headers["X-Page"] == "1"


def swapped_key_payload(question: dict[str, Any]) -> dict[str, Any]:
    """Make the wrong choice of the exam question the right one, worth 3."""
    return question_payload(
        choices=[
            {
                "id": correct_choice_id(question),
                "label": "Two",
                "is_correct": False,
                "points": 0,
            },
            {
                "id": wrong_choice_id(question),
                "label": "Three",
                "is_correct": True,
                "points": 3,
            },
        ]
    )


def finished_exam_with_a_wrong_answer(environment: dict[str, Any]) -> dict[str, Any]:
    client = environment["client"]
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
            json=choice_answer(
                client, participant_headers, wrong_choice_id(environment["question"])
            ),
        ).status_code
        == 200
    )
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    return quiz_session


def stored_scores(client: Any, session_id: int) -> list[tuple[float, bool]]:
    with client.app.state.session_factory() as session:
        return [
            (answer.score, answer.is_graded)
            for answer in session.query(QuizAnswer).filter_by(session_id=session_id)
        ]


def test_editing_a_question_leaves_published_grades_alone(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    published = finished_exam_with_a_wrong_answer(environment)
    assert (
        client.post(
            f"/api/quizzes/sessions/{published['id']}/publish-grades",
            headers=headers,
        ).status_code
        == 200
    )
    unpublished = finished_exam_with_a_wrong_answer(environment)
    assert stored_scores(client, published["id"]) == [(0.0, True)]
    assert stored_scores(client, unpublished["id"]) == [(0.0, True)]
    audit_events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        questions,
        "audit_event",
        lambda event, **details: audit_events.append((event, details)),
    )

    updated = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
    )

    assert updated.status_code == 200
    assert updated.json()["published_sessions_not_regraded"] == 1
    assert stored_scores(client, published["id"]) == [(0.0, True)]
    assert stored_scores(client, unpublished["id"]) == [(3.0, True)]
    teacher_id = client.get("/api/users/me", headers=headers).json()["id"]
    assert audit_events == [
        (
            "question.published_sessions_not_regraded",
            {
                "professor_id": teacher_id,
                "question_id": question["id"],
                "session_ids": [published["id"]],
            },
        )
    ]


def test_an_edit_without_published_sessions_writes_no_audit_event(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    question = environment["question"]
    finished = finished_exam_with_a_wrong_answer(environment)
    audit_events: list[str] = []
    monkeypatch.setattr(
        questions, "audit_event", lambda event, **_: audit_events.append(event)
    )

    updated = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=environment["teacher_headers"],
        data={"payload": json.dumps(swapped_key_payload(question))},
    )

    assert updated.status_code == 200
    assert updated.json()["published_sessions_not_regraded"] == 0
    assert stored_scores(client, finished["id"]) == [(3.0, True)]
    assert audit_events == []


def test_editing_a_question_an_active_exam_uses_is_refused(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    url = f"/api/question-banks/questions/{question['id']}/update"
    quiz_session, participant_headers = launch_and_join(client, environment)
    session_url = f"/api/quizzes/sessions/{quiz_session['id']}"

    for step in (None, "start", "pause"):
        if step is not None:
            started = client.post(f"{session_url}/{step}", headers=headers)
            assert started.status_code == 200
        refused = client.post(
            url,
            headers=headers,
            data={"payload": json.dumps(swapped_key_payload(question))},
        )
        assert refused.status_code == 409, step
        assert refused.json()["detail"]["code"] == "QUESTION_IN_ACTIVE_SESSION"

    # Nothing changed under the students.
    choices = client.get(
        f"/api/question-banks/{environment['bank_id']}/questions", headers=headers
    ).json()[0]["choices"]
    assert [(choice["label"], choice["is_correct"]) for choice in choices] == [
        ("Two", True),
        ("Three", False),
    ]

    assert client.post(f"{session_url}/resume", headers=headers).status_code == 200
    assert (
        client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json=choice_answer(client, participant_headers, wrong_choice_id(question)),
        ).status_code
        == 200
    )
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    assert (
        client.post(
            url,
            headers=headers,
            data={"payload": json.dumps(swapped_key_payload(question))},
        ).status_code
        == 200
    )


def test_an_active_makeup_child_also_blocks_question_edits(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    student_class = environment["student_class"]
    owner_id = client.get("/api/users/me", headers=headers).json()["id"]
    with client.app.state.session_factory() as session:
        makeup = MakeupSession(
            owner_id=owner_id,
            class_id=student_class["id"],
            class_name=student_class["name"],
            join_code="MAKEUP03",
            status="in_progress",
        )
        session.add(makeup)
        session.flush()
        child = QuizSession(
            quiz_id=environment["quiz"]["id"],
            class_id=student_class["id"],
            class_name=student_class["name"],
            join_code="CHILD003",
            status="in_progress",
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

    refused = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "QUESTION_IN_ACTIVE_SESSION"


def test_a_running_training_does_not_block_question_edits(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    assert (
        client.put(
            f"/api/quizzes/training/classes/{environment['student_class']['id']}"
            "/question-banks",
            headers=headers,
            json=training_banks(environment["bank_id"]),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/quizzes/training/{environment['bank_id']}/start",
            headers=environment["student_headers"],
        ).status_code
        == 201
    )

    updated = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
    )
    assert updated.status_code == 200


def test_regrading_an_edit_uses_a_constant_query_count(environment) -> None:
    """The regrade touches every affected answer in a fixed number of queries."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    engine = client.app.state.session_factory.kw["bind"]
    url = f"/api/question-banks/questions/{question['id']}/update"
    payload = {"payload": json.dumps(swapped_key_payload(question))}
    # Apply the edit once first, so the measured edits write the same choices.
    finished_exam_with_a_wrong_answer(environment)
    assert client.post(url, headers=headers, data=payload).status_code == 200
    query_counts: list[int] = []
    for session_count in (1, 4):
        while len(stored_sessions(client)) < session_count:
            finished_exam_with_a_wrong_answer(environment)
        statements = 0

        def count_statement(*_arguments: Any) -> None:
            nonlocal statements
            statements += 1

        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            updated = client.post(url, headers=headers, data=payload)
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)
        assert updated.status_code == 200
        assert all(
            stored_scores(client, session_id) == [(3.0, True)]
            for session_id in stored_sessions(client)
        )
        query_counts.append(statements)

    assert query_counts[0] == query_counts[1], (
        f"regrade queries grow with the number of sessions: {query_counts}"
    )


def stored_sessions(client: Any) -> list[int]:
    with client.app.state.session_factory() as session:
        return [quiz_session.id for quiz_session in session.query(QuizSession)]


def written_update(client: Any, environment: dict[str, Any]) -> Any:
    return client.post(
        f"/api/question-banks/questions/{environment['question']['id']}/update",
        headers=environment["teacher_headers"],
        data={
            "payload": json.dumps(
                question_payload(
                    answer_mode="written",
                    choices=[{"label": "Two", "is_correct": True, "points": 2}],
                )
            )
        },
    )


def test_turning_a_choice_question_written_sends_its_answers_to_grading(
    environment,
) -> None:
    """Automatic marks of the choice question no longer stand: a teacher marks."""
    client = environment["client"]
    finished = finished_exam_with_a_wrong_answer(environment)
    assert stored_scores(client, finished["id"]) == [(0.0, True)]

    assert written_update(client, environment).status_code == 200

    assert stored_scores(client, finished["id"]) == [(0.0, False)]
    participant = client.get(
        f"/api/quizzes/sessions/{finished['id']}",
        headers=environment["teacher_headers"],
    ).json()["participants"][0]
    assert participant["pending_manual_grading_count"] == 1


def test_editing_a_written_question_keeps_teacher_marks_and_zeroes_pending_ones(
    environment,
) -> None:
    """Rescoring a written question follows compute_final_scores' rule."""
    client = environment["client"]
    graded = finished_exam_with_a_wrong_answer(environment)
    pending = finished_exam_with_a_wrong_answer(environment)
    assert written_update(client, environment).status_code == 200
    with client.app.state.session_factory() as session:
        for session_id, score, is_graded in (
            (graded["id"], 1.5, True),
            (pending["id"], 1.5, False),
        ):
            answer = session.query(QuizAnswer).filter_by(session_id=session_id).one()
            answer.score = score
            answer.is_graded = is_graded
        session.commit()

    # Still written: the teacher's mark stands.
    assert written_update(client, environment).status_code == 200

    assert stored_scores(client, graded["id"]) == [(1.5, True)]
    assert stored_scores(client, pending["id"]) == [(0.0, False)]


def test_an_edit_decodes_its_image_without_holding_the_question(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow decode must not keep the question, or its sessions, locked."""
    client = environment["client"]
    question_id = environment["question"]["id"]
    locked_while_decoding: list[bool] = []

    def decode_and_probe(data: bytes, content_type: str) -> tuple[bytes, str]:
        with client.app.state.session_factory() as other:
            other.execute(text("SET lock_timeout = '100ms'"))
            try:
                other.execute(
                    select(Question.id)
                    .where(Question.id == question_id)
                    .with_for_update(nowait=True)
                )
                locked_while_decoding.append(False)
            except OperationalError:
                locked_while_decoding.append(True)
            other.rollback()
        return normalize_image(data, content_type)

    monkeypatch.setattr(questions, "normalize_image", decode_and_probe)

    choices = [
        {"label": "Four", "is_correct": True, "image_file": 0},
        {"label": "Five", "is_correct": False},
    ]
    updated = client.post(
        f"/api/question-banks/questions/{question_id}/update",
        headers=environment["teacher_headers"],
        data={"payload": json.dumps(question_payload(choices=choices))},
        files=[
            ("image", ("image.png", VALID_PNG, "image/png")),
            ("choice_images", ("choice.png", VALID_PNG, "image/png")),
        ],
    )

    assert updated.status_code == 200
    assert updated.json()["has_image"] is True
    assert updated.json()["choices"][0]["has_image"] is True
    assert locked_while_decoding == [False, False]


def noisy_png(side: int) -> bytes:
    """A PNG that compresses poorly: side 700 makes about 1.5 MB."""
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_choice_images_travel_as_file_parts(environment) -> None:
    """In base64 inside the payload field, one would hit the 1 MiB field cap."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    large = noisy_png(700)
    assert len(large) > 1024 * 1024
    choices = [
        {"label": "", "is_correct": True, "image_file": 1},
        {"label": "", "is_correct": False, "image_file": 0},
    ]
    created = client.post(
        f"/api/question-banks/{environment['bank_id']}/questions",
        headers=headers,
        data={"payload": json.dumps(question_payload(choices=choices))},
        files=[
            ("choice_images", ("small.png", VALID_PNG, "image/png")),
            ("choice_images", ("large.png", large, "image/png")),
        ],
    )
    assert created.status_code == 201, created.text
    first, second = created.json()["choices"]
    assert first["has_image"] is True
    assert second["has_image"] is True
    first_image = client.get(
        f"/api/question-banks/choices/{first['id']}/image", headers=headers
    )
    # The large image went to the first choice, which named file part 1.
    assert len(first_image.content) > len(VALID_PNG)

    # An edit keeps one image by id and replaces the other from a file part.
    kept = client.post(
        f"/api/question-banks/questions/{created.json()['id']}/update",
        headers=headers,
        data={
            "payload": json.dumps(
                question_payload(
                    choices=[
                        {"id": first["id"], "label": "", "is_correct": True},
                        {
                            "id": second["id"],
                            "label": "",
                            "is_correct": False,
                            "image_file": 0,
                        },
                    ]
                )
            )
        },
        files=[("choice_images", ("large.png", large, "image/png"))],
    )
    assert kept.status_code == 200, kept.text
    assert [choice["has_image"] for choice in kept.json()["choices"]] == [True, True]
    second_image = client.get(
        f"/api/question-banks/choices/{second['id']}/image", headers=headers
    )
    assert second_image.content == first_image.content


def test_choice_image_files_are_checked(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    url = f"/api/question-banks/{environment['bank_id']}/questions"

    def post(choices: list[dict[str, Any]], files: list[Any]) -> Any:
        return client.post(
            url,
            headers=headers,
            data={"payload": json.dumps(question_payload(choices=choices))},
            files=files,
        )

    one_file = [("choice_images", ("a.png", VALID_PNG, "image/png"))]
    missing = post(
        [
            {"label": "Four", "is_correct": True, "image_file": 1},
            {"label": "Five", "is_correct": False},
        ],
        one_file,
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "QUESTION_INVALID"

    shared = post(
        [
            {"label": "Four", "is_correct": True, "image_file": 0},
            {"label": "Five", "is_correct": False, "image_file": 0},
        ],
        one_file,
    )
    assert shared.status_code == 422
    assert shared.json()["detail"]["code"] == "QUESTION_INVALID"

    both = post(
        [
            {
                "label": "Four",
                "is_correct": True,
                "image_file": 0,
                "image": png_image(),
            },
            {"label": "Five", "is_correct": False},
        ],
        one_file,
    )
    assert both.status_code == 422
    assert both.json()["detail"]["code"] == "QUESTION_INVALID"

    unsupported = post(
        [
            {"label": "Four", "is_correct": True, "image_file": 0},
            {"label": "Five", "is_correct": False},
        ],
        [("choice_images", ("a.svg", b"<svg/>", "image/svg+xml"))],
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["code"] == "IMAGE_TYPE_UNSUPPORTED"

    image_only = post(
        [
            {"label": "", "is_correct": True, "image_file": 0},
            {"label": "Five", "is_correct": False},
        ],
        [("choice_images", ("a.png", b"", "image/png"))],
    )
    # An empty file is no image: the choice is left without content.
    assert image_only.status_code == 422
    assert image_only.json()["detail"]["code"] == "CHOICE_CONTENT_REQUIRED"


def test_a_json_import_cannot_name_a_file_part() -> None:
    with pytest.raises(ValidationError, match="encodée dans le fichier"):
        QuestionBatchImport.model_validate(
            {
                "version": 1,
                "question_bank": {"grade_level": "5e", "chapter": "Files"},
                "questions": [
                    question_payload(
                        choices=[
                            {"label": "Four", "is_correct": True, "image_file": 0},
                            {"label": "Five", "is_correct": False},
                        ]
                    )
                ],
            }
        )


def test_banks_say_how_many_quizzes_draw_from_them(environment) -> None:
    """The delete dialog warns when quizzes would lose the bank."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    unused = client.post(
        "/api/question-banks",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Unused"},
    ).json()
    assert unused["quiz_count"] == 0
    second_quiz = client.post(
        "/api/quizzes",
        headers=headers,
        json={
            "title": "Second quiz",
            "question_bank_ids": [environment["bank_id"]],
            "easy_question_count": 1,
            "medium_question_count": 0,
            "hard_question_count": 0,
        },
    )
    assert second_quiz.status_code == 201

    counts = {
        bank["id"]: (bank["quiz_count"], bank["question_count"])
        for bank in client.get("/api/question-banks", headers=headers).json()
    }

    # Two quizzes, and the question is still counted once.
    assert counts == {environment["bank_id"]: (2, 1), unused["id"]: (0, 0)}
    renamed = client.post(
        f"/api/question-banks/{environment['bank_id']}/update",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Renamed"},
    )
    assert renamed.json()["quiz_count"] == 2


def answer_reviews(client: Any, headers: dict[str, str], session_id: int) -> list:
    """The teacher's correction of the one participant of a finished exam."""
    participant = client.get(
        f"/api/quizzes/sessions/{session_id}", headers=headers
    ).json()["participants"][0]
    return client.get(
        f"/api/quizzes/sessions/{session_id}/participants/{participant['id']}/answers",
        headers=headers,
    ).json()


def detached_question_ids(client: Any) -> list[int]:
    with client.app.state.session_factory() as session:
        return list(
            session.scalars(
                select(Question.id)
                .where(Question.question_bank_id.is_(None))
                .order_by(Question.id)
            )
        )


def test_published_sessions_keep_the_question_as_they_asked_it(environment) -> None:
    """An edit changes the bank and unpublished results, never published ones."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    url = f"/api/question-banks/questions/{question['id']}/update"
    with_code = {
        **swapped_key_payload(question),
        "prompt": "One plus one?",
        "code_language": "python",
        "code_content": "print(1 + 1)",
    }
    for choice, (label, is_correct, points) in zip(
        with_code["choices"],
        [("Two", True, 2), ("Three", False, 0)],
        strict=True,
    ):
        choice.update(label=label, is_correct=is_correct, points=points)
    assert (
        client.post(
            url, headers=headers, data={"payload": json.dumps(with_code)}
        ).status_code
        == 200
    )
    assert detached_question_ids(client) == []

    published = finished_exam_with_a_wrong_answer(environment)
    assert (
        client.post(
            f"/api/quizzes/sessions/{published['id']}/publish-grades",
            headers=headers,
        ).status_code
        == 200
    )
    unpublished = finished_exam_with_a_wrong_answer(environment)
    published_before = answer_reviews(client, headers, published["id"])
    student_before = client.get(
        "/api/quizzes/student/results", headers=environment["student_headers"]
    ).json()
    edited = client.post(
        url,
        headers=headers,
        data={
            "payload": json.dumps(
                {**swapped_key_payload(question), "prompt": "One plus one, edited?"}
            )
        },
    )

    assert edited.status_code == 200
    assert edited.json()["id"] == question["id"]
    assert edited.json()["published_sessions_not_regraded"] == 1
    [frozen_id] = detached_question_ids(client)
    published_after = answer_reviews(client, headers, published["id"])
    assert [review["question_id"] for review in published_after] == [frozen_id]
    assert [{**review, "question_id": None} for review in published_after] == [
        {**review, "question_id": None} for review in published_before
    ]
    assert published_after[0]["prompt"] == "One plus one?"
    assert published_after[0]["code_content"] == "print(1 + 1)"
    assert published_after[0]["submitted_answers"] == ["Three"]
    assert published_after[0]["expected_answers"] == ["Two"]
    assert (published_after[0]["score"], published_after[0]["max_score"]) == (0, 2)

    [unpublished_review] = answer_reviews(client, headers, unpublished["id"])
    assert unpublished_review["question_id"] == question["id"]
    assert unpublished_review["prompt"] == "One plus one, edited?"
    assert unpublished_review["code_content"] is None
    assert unpublished_review["expected_answers"] == ["Three"]
    assert (unpublished_review["score"], unpublished_review["max_score"]) == (3, 3)

    student_after = {
        result["session_id"]: result
        for result in client.get(
            "/api/quizzes/student/results", headers=environment["student_headers"]
        ).json()
    }
    student_published_before = next(
        result for result in student_before if result["session_id"] == published["id"]
    )
    assert [
        {**answer, "question_id": None}
        for answer in student_after[published["id"]]["answers"]
    ] == [
        {**answer, "question_id": None}
        for answer in student_published_before["answers"]
    ]
    assert student_after[published["id"]]["score"] == 0
    assert student_after[unpublished["id"]]["score"] == 3

    with client.app.state.session_factory() as session:
        frozen_choices = {
            choice.id: choice.label
            for choice in session.scalars(
                select(QuestionChoice).where(QuestionChoice.question_id == frozen_id)
            )
        }
        answer = session.scalar(
            select(QuizAnswer).where(QuizAnswer.session_id == published["id"])
        )
        assert answer is not None
        assert [
            frozen_choices[choice_id]
            for choice_id in json.loads(answer.answer_data)["selected_choice_ids"]
        ] == ["Three"]

    # The bank lists the edited question alone.
    [listed] = client.get(
        f"/api/question-banks/{environment['bank_id']}/questions", headers=headers
    ).json()
    assert (listed["id"], listed["prompt"]) == (question["id"], "One plus one, edited?")

    # A session published since, where nobody answered.
    with client.app.state.session_factory() as session:
        unanswered = QuizSession(
            quiz_id=environment["quiz"]["id"],
            class_id=environment["student_class"]["id"],
            class_name=environment["student_class"]["name"],
            join_code="NOANSWR1",
            status="finished",
            grades_published_at=datetime.now(UTC),
        )
        session.add(unanswered)
        session.flush()
        session.add(
            QuizSessionQuestion(
                session_id=unanswered.id, question_id=question["id"], position=0
            )
        )
        session.commit()
        unanswered_id = unanswered.id

    # A further edit leaves the session already frozen on its copy, and
    # freezes another for the session published since, which has no answer.
    again = client.post(
        url,
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
    )
    assert again.status_code == 200
    assert again.json()["published_sessions_not_regraded"] == 1
    [_, second_frozen_id] = detached_question_ids(client)
    assert answer_reviews(client, headers, published["id"]) == published_after
    with client.app.state.session_factory() as session:
        assert (
            session.scalar(
                select(QuizSessionQuestion.question_id).where(
                    QuizSessionQuestion.session_id == unanswered_id
                )
            )
            == second_frozen_id
        )
        frozen = session.get(Question, second_frozen_id)
        assert frozen is not None
        assert frozen.prompt == "One plus one, edited?"


@pytest.mark.parametrize(
    ("answer_data", "expected"),
    [
        ('{"selected_choice_ids": [1, 2, true, "3", 9]}', None),
        ('{"written_answer": "x"}', '{"written_answer": "x"}'),
        ('{"selected_choice_ids": 1}', '{"selected_choice_ids": 1}'),
        ("[1, 2]", "[1, 2]"),
        ("not json", "not json"),
    ],
)
def test_frozen_answers_rename_only_the_choice_ids_they_hold(
    answer_data: str, expected: str | None
) -> None:
    remapped = question_history.remapped_answer_data(answer_data, {1: 11, 2: 12})
    if expected is None:
        assert json.loads(remapped) == {"selected_choice_ids": [11, 12, True, "3", 9]}
    else:
        assert remapped == expected


def test_a_deleted_question_stays_with_past_exams_until_they_go(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    finished = finished_exam_with_a_wrong_answer(environment)
    reviews = answer_reviews(client, headers, finished["id"])

    deleted = client.delete(
        f"/api/question-banks/questions/{question['id']}", headers=headers
    )

    assert deleted.status_code == 204
    assert detached_question_ids(client) == [question["id"]]
    [bank] = client.get("/api/question-banks", headers=headers).json()
    assert bank["question_count"] == 0
    assert answer_reviews(client, headers, finished["id"]) == reviews
    # Detached, it is no longer the teacher's to edit or delete.
    assert (
        client.post(
            f"/api/question-banks/questions/{question['id']}/update",
            headers=headers,
            data={"payload": json.dumps(swapped_key_payload(question))},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/question-banks/questions/{question['id']}", headers=headers
        ).status_code
        == 404
    )

    settings = client.app.state.settings
    maintenance.enforce_data_retention(client.app.state.session_factory, settings)
    assert detached_question_ids(client) == [question["id"]]
    audit_events: list[tuple[str, dict[str, object]]] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            maintenance,
            "audit_event",
            lambda event, **details: audit_events.append((event, details)),
        )
        maintenance.enforce_data_retention(
            client.app.state.session_factory,
            settings,
            now=datetime.now(UTC)
            + timedelta(days=settings.quiz_result_retention_days + 1),
        )
    assert detached_question_ids(client) == []
    assert audit_events[0][1]["detached_questions"] == 1


def test_an_open_exam_keeps_its_questions_and_their_bank(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    quiz_session, participant_headers = launch_and_join(client, environment)

    refused_question = client.delete(
        f"/api/question-banks/questions/{question['id']}", headers=headers
    )
    refused_bank = client.delete(
        f"/api/question-banks/{environment['bank_id']}", headers=headers
    )

    assert refused_question.status_code == 409
    assert refused_question.json()["detail"]["code"] == "QUESTION_IN_ACTIVE_SESSION"
    assert refused_bank.status_code == 409
    assert refused_bank.json()["detail"] == {
        "code": "QUESTION_BANK_IN_USE",
        "message": "Cette banque est utilisée par un examen en cours",
    }
    assert detached_question_ids(client) == []

    assert (
        client.post(
            f"/api/quizzes/sessions/{quiz_session['id']}/start", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json=choice_answer(client, participant_headers, wrong_choice_id(question)),
        ).status_code
        == 200
    )
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    assert (
        client.delete(
            f"/api/question-banks/{environment['bank_id']}", headers=headers
        ).status_code
        == 204
    )


def test_an_open_makeup_keeps_the_banks_of_its_quizzes(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    student_class = environment["student_class"]
    owner_id = client.get("/api/users/me", headers=headers).json()["id"]
    with client.app.state.session_factory() as session:
        makeup = MakeupSession(
            owner_id=owner_id,
            class_id=student_class["id"],
            class_name=student_class["name"],
            join_code="MAKEUP04",
            status="waiting",
        )
        session.add(makeup)
        session.flush()
        session.add(
            MakeupSessionQuiz(session_id=makeup.id, quiz_id=environment["quiz"]["id"])
        )
        session.commit()

    refused = client.delete(
        f"/api/question-banks/{environment['bank_id']}", headers=headers
    )

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "QUESTION_BANK_IN_USE"


def test_deleting_a_used_bank_keeps_past_exams_and_unlinks_its_quizzes(
    environment,
) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    unused = client.post(
        f"/api/question-banks/{environment['bank_id']}/questions",
        headers=headers,
        # Never drawn: the quiz asks for one easy question.
        data={"payload": json.dumps(question_payload(difficulty="hard"))},
    ).json()
    finished = finished_exam_with_a_wrong_answer(environment)
    reviews = answer_reviews(client, headers, finished["id"])

    deleted = client.delete(
        f"/api/question-banks/{environment['bank_id']}", headers=headers
    )

    assert deleted.status_code == 204
    assert client.get("/api/question-banks", headers=headers).json() == []
    [quiz] = client.get("/api/quizzes", headers=headers).json()
    assert quiz["question_banks"] == []
    assert detached_question_ids(client) == [question["id"]]
    with client.app.state.session_factory() as session:
        assert session.get(Question, unused["id"]) is None
    assert answer_reviews(client, headers, finished["id"]) == reviews

    empty_bank = client.post(
        "/api/question-banks",
        headers=headers,
        json={"grade_level": "5e", "chapter": "Empty"},
    ).json()
    assert (
        client.delete(
            f"/api/question-banks/{empty_bank['id']}", headers=headers
        ).status_code
        == 204
    )


def test_deleting_a_teacher_deletes_their_detached_questions(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    finished_exam_with_a_wrong_answer(environment)
    assert (
        client.delete(
            f"/api/question-banks/questions/{environment['question']['id']}",
            headers=headers,
        ).status_code
        == 204
    )
    assert detached_question_ids(client) == [environment["question"]["id"]]
    teacher_id = client.get("/api/users/me", headers=headers).json()["id"]

    assert (
        client.delete(
            f"/api/admin/users/{teacher_id}", headers=environment["admin_headers"]
        ).status_code
        == 204
    )

    assert detached_question_ids(client) == []


def test_the_sweep_skips_a_detached_question_a_launch_still_draws(
    environment,
) -> None:
    """A launch that read the question before its removal may commit after.

    Its reference holds a lock the sweep's deletion waits for, then the
    foreign key refuses it: the sweep gives up on that question only.
    """
    client = environment["client"]
    finished = finished_exam_with_a_wrong_answer(environment)
    assert (
        client.delete(
            f"/api/question-banks/questions/{environment['question']['id']}",
            headers=environment["teacher_headers"],
        ).status_code
        == 204
    )
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        session.execute(
            delete(QuizAnswer).where(QuizAnswer.session_id == finished["id"])
        )
        for table in (QuizSessionQuestion, QuizSessionStudentQuestion):
            session.execute(delete(table).where(table.session_id == finished["id"]))
        session.commit()
    assert detached_question_ids(client) == [environment["question"]["id"]]

    with session_factory() as launching, session_factory() as sweeping:
        launching.add(
            QuizSessionQuestion(
                session_id=finished["id"],
                question_id=environment["question"]["id"],
                position=0,
            )
        )
        launching.flush()
        swept: list[int] = []

        def sweep() -> None:
            swept.append(question_history.delete_unused_detached_questions(sweeping))
            # The rest of the sweeping transaction is still usable.
            sweeping.execute(select(1))
            sweeping.commit()

        sweeper = Thread(target=sweep)
        sweeper.start()
        sleep(0.3)
        launching.commit()
        sweeper.join(timeout=10)
        assert swept == [0]
    assert detached_question_ids(client) == [environment["question"]["id"]]
