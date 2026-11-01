"""Question banks and questions: validation, images and regrading."""

import io
import json
from base64 import b64encode
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from app.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DIMENSION,
    InvalidImage,
    normalize_image,
)
from app.models import (
    MakeupSession,
    QuizSession,
    QuizSessionQuestion,
)
from app.routers import question_bank_transfer, questions
from app.schemas import (
    QuestionBatchImport,
    QuestionChoiceCreate,
    QuestionCreate,
)

from support import (
    VALID_PNG,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
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

    monkeypatch.setattr(questions, "MAX_IMAGE_BYTES", len(VALID_PNG) - 1)
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
            json={"selected_choice_ids": all_choice_ids},
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
    with pytest.raises(InvalidImage):
        normalize_image(data, declared_type)


def test_normalize_image_rejects_oversized_payloads() -> None:
    with pytest.raises(InvalidImage):
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

    with pytest.raises(InvalidImage):
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
            json={"selected_choice_ids": [wrong_choice["id"]]},
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

        # Deleting the question is still blocked because it is used in a launched quiz
        delete_response = client.delete(
            f"/api/question-banks/questions/{environment['question']['id']}",
            headers=environment["teacher_headers"],
        )
        assert delete_response.status_code == 409
        assert delete_response.json()["detail"] == {
            "code": "QUESTION_IN_LAUNCHED_QUIZ",
            "message": "Cette question est utilisée par un quiz déjà lancé",
        }
