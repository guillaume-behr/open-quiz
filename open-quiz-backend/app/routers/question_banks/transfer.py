"""Question bank files: the import example, exports and imports.

A bank travels as one JSON document (version 1) holding its questions,
choices and images as base64. Exporting produces that document, importing
creates a new bank from it in one transaction, and the example shows the
format with sample questions.
"""

import json
from base64 import b64encode
from collections.abc import Iterator
from pathlib import Path

from fastapi import (
    APIRouter,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import DbSession, ProfessorUser
from app.core.errors import ApiError, ErrorCode
from app.domain.unique_names import (
    QUESTION_BANK_NAME_CONSTRAINT,
    QUESTION_BANK_NAME_TAKEN_MESSAGE,
    write_unique_name,
)
from app.enums import Difficulty
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    StoredImage,
)
from app.records.grade_levels import ensure_grade_level, grade_level_import_context
from app.records.questions import (
    MAX_IMPORT_IMAGE_BYTES,
    ImagePixelBudget,
    add_question,
    decode_image_payload,
    owned_question_bank,
)
from app.responses.questions import question_response
from app.schemas import (
    QuestionBankResponse,
    QuestionBatchImport,
    QuestionBatchImportResponse,
    QuestionImportItem,
)

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])
# The questions of the downloadable example; the route adds the grade level,
# which depends on the teacher's own levels.
EXAMPLE_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "question_bank_example.json"
)


def downloadable_json(content: object, filename: str) -> Response:
    return Response(
        content=json.dumps(content, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/example")
def download_import_example(
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Download a complete versioned example of the question batch format."""
    available_grade_levels, grade_level_comment = grade_level_import_context(
        professor.id, session
    )
    example = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
    return downloadable_json(
        {
            "version": example["version"],
            "question_bank": {
                "_comment_grade_level": grade_level_comment,
                "grade_level": (
                    available_grade_levels[0] if available_grade_levels else "Tle"
                ),
                **example["question_bank"],
            },
            "questions": example["questions"],
        },
        "open-quiz-questions-example.json",
    )


def exported_images(
    session: Session, hashes: list[str | None]
) -> dict[str | None, dict[str, str]]:
    """The images among ``hashes`` as exported, keyed by hash, in one query.

    Rows rather than StoredImage instances, so the session keeps no image
    once the question that needed it is written.
    """
    wanted = {image_hash for image_hash in hashes if image_hash is not None}
    if not wanted:
        return {}
    return {
        image_hash: {
            "content_type": content_type,
            "data_base64": b64encode(data).decode(),
        }
        for image_hash, content_type, data in session.execute(
            select(
                StoredImage.sha256, StoredImage.content_type, StoredImage.data
            ).where(StoredImage.sha256.in_(wanted))
        )
    }


@router.get("/{question_bank_id}/export")
def export_questions(
    question_bank_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Export every question in a bank as a versioned JSON document."""
    question_bank = owned_question_bank(question_bank_id, professor, session)
    bank_id = question_bank.id
    grade_level = question_bank.grade_level
    chapter = question_bank.chapter
    session_factory = request.app.state.session_factory
    # The response streams after the route returns, while the request's
    # session stays open until it is sent: release its connection now, since
    # the export reads through a session of its own.
    session.commit()

    def stream_export() -> Iterator[str]:
        yield '{\n  "version": 1,\n  "question_bank": '
        yield json.dumps(
            {"grade_level": grade_level, "chapter": chapter},
            ensure_ascii=False,
            indent=2,
        )
        yield ',\n  "questions": ['
        first = True
        with session_factory() as export_session:
            # Questions, choices and code in one query each; images, the bulk
            # of a bank, one question at a time so that memory holds a single
            # question's images.
            questions = list(
                export_session.scalars(
                    select(Question)
                    .where(Question.question_bank_id == bank_id)
                    .order_by(Question.created_at, Question.id)
                )
            )
            choices_by_question: dict[int, list[QuestionChoice]] = {}
            for choice in export_session.scalars(
                select(QuestionChoice)
                .join(Question, Question.id == QuestionChoice.question_id)
                .where(Question.question_bank_id == bank_id)
                .order_by(QuestionChoice.question_id, QuestionChoice.position)
            ):
                choices_by_question.setdefault(choice.question_id, []).append(choice)
            codes = {
                code.question_id: code
                for code in export_session.scalars(
                    select(QuestionCode)
                    .join(Question, Question.id == QuestionCode.question_id)
                    .where(Question.question_bank_id == bank_id)
                )
            }
            for question in questions:
                choices = choices_by_question.get(question.id, [])
                code = codes.get(question.id)
                images = exported_images(
                    export_session,
                    [question.image_sha256]
                    + [choice.image_sha256 for choice in choices],
                )
                exported_question = {
                    "prompt": question.prompt,
                    "difficulty": question.difficulty,
                    "answer_mode": question.answer_mode,
                    "answer_mode_disclosed": question.answer_mode_disclosed,
                    "response_language": question.response_language,
                    "allow_code_execution": question.allow_code_execution,
                    "choices": [
                        {
                            "label": choice.label,
                            "is_correct": choice.is_correct,
                            "points": choice.points,
                            "image": images.get(choice.image_sha256),
                            "code_language": choice.code_language,
                            "code_content": choice.code_content,
                        }
                        for choice in choices
                    ],
                    "code_language": code.language if code else None,
                    "code_content": code.content if code else None,
                    "image": images.get(question.image_sha256),
                }
                yield (",\n" if not first else "\n") + json.dumps(
                    exported_question,
                    ensure_ascii=False,
                    indent=4,
                )
                first = False
        yield "\n  ]\n}\n"

    return StreamingResponse(
        stream_export(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="question-bank-{bank_id}.json"'
        },
    )


def decode_import_image(
    payload: QuestionImportItem,
    budget: ImagePixelBudget,
) -> tuple[bytes | None, str | None]:
    return decode_image_payload(payload.image, budget)


@router.post(
    "/import",
    response_model=QuestionBatchImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_question_bank(
    payload: QuestionBatchImport,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBatchImportResponse:
    """Create a bank from a JSON batch and atomically import its questions."""
    # Decoding the images can take minutes: end the transaction the
    # authentication opened, so that no pooled connection waits on it.
    session.commit()
    decoded_images: list[tuple[bytes | None, str | None]] = []
    decoded_choice_images: list[list[tuple[bytes | None, str | None]]] = []
    total_image_bytes = 0
    pixel_budget = ImagePixelBudget()
    for question in payload.questions:
        decoded_image = decode_import_image(question, pixel_budget)
        choice_images = [
            decode_image_payload(choice.image, pixel_budget)
            for choice in question.choices
        ]
        total_image_bytes += len(decoded_image[0] or b"") + sum(
            len(choice_image[0] or b"") for choice_image in choice_images
        )
        if total_image_bytes > MAX_IMPORT_IMAGE_BYTES:
            raise ApiError(
                status.HTTP_413_CONTENT_TOO_LARGE,
                ErrorCode.IMPORT_IMAGES_TOO_LARGE,
                "Le volume total des images importées est trop important",
            )
        decoded_images.append(decoded_image)
        decoded_choice_images.append(choice_images)
    question_bank = QuestionBank(
        owner_id=professor.id,
        grade_level=ensure_grade_level(
            professor.id, payload.question_bank.grade_level, session
        ),
        chapter=payload.question_bank.chapter,
    )
    session.add(question_bank)
    write_unique_name(
        session,
        session.flush,
        QUESTION_BANK_NAME_CONSTRAINT,
        ErrorCode.QUESTION_BANK_NAME_TAKEN,
        QUESTION_BANK_NAME_TAKEN_MESSAGE,
    )

    created = [
        add_question(
            question_bank.id,
            question,
            session,
            image_data=image_data,
            image_content_type=image_content_type,
            choice_images=choice_images,
        )
        for question, (image_data, image_content_type), choice_images in zip(
            payload.questions,
            decoded_images,
            decoded_choice_images,
            strict=True,
        )
    ]
    session.commit()
    # expire_on_commit=False: instances stay populated, no refresh needed.
    questions = [
        question_response(question, choices, code)
        for question, choices, code in created
    ]
    return QuestionBatchImportResponse(
        question_bank=QuestionBankResponse.model_validate(question_bank).model_copy(
            update={
                "question_count": len(questions),
                "easy_question_count": sum(
                    question.difficulty == Difficulty.EASY
                    for question in payload.questions
                ),
                "medium_question_count": sum(
                    question.difficulty == Difficulty.MEDIUM
                    for question in payload.questions
                ),
                "hard_question_count": sum(
                    question.difficulty == Difficulty.HARD
                    for question in payload.questions
                ),
            }
        ),
        questions=questions,
    )
