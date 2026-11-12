"""Question banks and questions: validation, images and regrading."""

import io
import json
from base64 import b64encode
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import func, select

from app import question_records
from app.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DIMENSION,
    InvalidImageError,
    image_pixel_count,
    normalize_image,
)
from app.models import (
    Question,
    QuestionChoice,
    QuizAnswer,
    QuizQuestionBank,
    QuizSessionQuestion,
)
from app.quiz_session_records import delete_quiz_session_records
from app.routers import question_bank_transfer, questions
from app.schemas import (
    QuestionBatchImport,
    QuestionChoiceCreate,
    QuestionCreate,
)

from support import (
    VALID_PNG,
    choice_answer,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
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


def test_bank_edits_and_deletions_leave_launched_sessions_alone(
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

        # The teacher changes the key in the bank, then deletes the question:
        # the session graded its own copy, so its results do not move.
        update_response = client.post(
            f"/api/question-banks/questions/{environment['question']['id']}/update",
            headers=environment["teacher_headers"],
            data={"payload": json.dumps(swapped_key_payload(environment["question"]))},
        )
        assert update_response.status_code == 200
        delete_response = client.delete(
            f"/api/question-banks/questions/{environment['question']['id']}",
            headers=environment["teacher_headers"],
        )
        assert delete_response.status_code == 204

        unchanged_results = client.get(
            "/api/quizzes/sessions/results",
            headers=environment["teacher_headers"],
        ).json()
        assert [{**result, "server_now": None} for result in unchanged_results] == [
            {**result, "server_now": None} for result in results
        ]
        unchanged_history = client.get(
            "/api/quizzes/student/results",
            headers=environment["student_headers"],
        ).json()
        assert unchanged_history[0]["score"] == 0.0
        assert unchanged_history[0]["answers"][0]["is_correct"] is False


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


def session_copies(client: Any, session_id: int) -> list[Question]:
    with client.app.state.session_factory() as session:
        return list(
            session.scalars(
                select(Question).where(Question.quiz_session_id == session_id)
            )
        )


def test_a_launch_copies_the_drawn_questions_into_the_session(environment) -> None:
    client = environment["client"]
    question = environment["question"]
    quiz_session, _ = launch_and_join(client, environment)

    copies = session_copies(client, quiz_session["id"])
    assert [(copy.source_question_id, copy.prompt) for copy in copies] == [
        (question["id"], question["prompt"])
    ]
    assert copies[0].question_bank_id is None
    with client.app.state.session_factory() as session:
        assert session.scalars(
            select(QuizSessionQuestion.question_id).where(
                QuizSessionQuestion.session_id == quiz_session["id"]
            )
        ).all() == [copies[0].id]
        assert [
            (choice.label, choice.is_correct, choice.points)
            for choice in session.scalars(
                select(QuestionChoice)
                .where(QuestionChoice.question_id == copies[0].id)
                .order_by(QuestionChoice.position)
            )
        ] == [
            (choice["label"], choice["is_correct"], choice["points"])
            for choice in question["choices"]
        ]
    # The bank lists only its own questions, never the copies.
    listed = client.get(
        f"/api/question-banks/{environment['bank_id']}/questions",
        headers=environment["teacher_headers"],
    ).json()
    assert [item["id"] for item in listed] == [question["id"]]


def test_a_running_exam_does_not_block_bank_edits(environment) -> None:
    """Students keep answering, and being graded on, the question they drew."""
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    quiz_session, participant_headers = launch_and_join(client, environment)
    session_url = f"/api/quizzes/sessions/{quiz_session['id']}"
    assert client.post(f"{session_url}/start", headers=headers).status_code == 200

    updated = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
    )
    assert updated.status_code == 200

    (copy,) = session_copies(client, quiz_session["id"])
    with client.app.state.session_factory() as session:
        copied = [
            (choice.id, choice.label, choice.is_correct)
            for choice in session.scalars(
                select(QuestionChoice)
                .where(QuestionChoice.question_id == copy.id)
                .order_by(QuestionChoice.position)
            )
        ]
    assert [(label, is_correct) for _, label, is_correct in copied] == [
        ("Two", True),
        ("Three", False),
    ]
    assert (
        client.post(
            f"/api/quizzes/student/sessions/{quiz_session['join_code']}/answer",
            headers=participant_headers,
            json=choice_answer(client, participant_headers, copied[0][0]),
        ).status_code
        == 200
    )
    hand_in_quiz(client, quiz_session["join_code"], participant_headers)
    assert stored_scores(client, quiz_session["id"]) == [(2.0, True)]


def test_deleting_a_bank_used_by_a_quiz_keeps_its_sessions(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    finished = finished_exam_with_a_wrong_answer(environment)
    results = client.get("/api/quizzes/sessions/results", headers=headers).json()

    deleted = client.delete(
        f"/api/question-banks/{environment['bank_id']}", headers=headers
    )

    assert deleted.status_code == 204
    with client.app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuizQuestionBank)
                .where(QuizQuestionBank.quiz_id == environment["quiz"]["id"])
            )
            == 0
        )
    copies = session_copies(client, finished["id"])
    assert [copy.source_question_id for copy in copies] == [None]
    after = client.get("/api/quizzes/sessions/results", headers=headers).json()
    assert [{**result, "server_now": None} for result in after] == [
        {**result, "server_now": None} for result in results
    ]


def test_deleting_a_session_deletes_its_copies(environment) -> None:
    client = environment["client"]
    quiz_session, _ = launch_and_join(client, environment)
    (copy,) = session_copies(client, quiz_session["id"])
    with client.app.state.session_factory() as session:
        delete_quiz_session_records([quiz_session["id"]], session)
        session.commit()
    with client.app.state.session_factory() as session:
        assert session.get(Question, copy.id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuestionChoice)
                .where(QuestionChoice.question_id == copy.id)
            )
            == 0
        )
        assert session.get(Question, environment["question"]["id"]) is not None


def test_a_teacher_sees_the_images_of_their_session_copies(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    question = environment["question"]
    with_image = client.post(
        f"/api/question-banks/questions/{question['id']}/update",
        headers=headers,
        data={"payload": json.dumps(swapped_key_payload(question))},
        files={"image": ("q.png", VALID_PNG, "image/png")},
    )
    assert with_image.status_code == 200
    quiz_session, _ = launch_and_join(client, environment)
    (copy,) = session_copies(client, quiz_session["id"])

    image = client.get(
        f"/api/question-banks/questions/{copy.id}/image", headers=headers
    )
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
