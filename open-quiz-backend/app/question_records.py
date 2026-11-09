"""Question banks and their questions: ownership checks and creation."""

from base64 import b64decode
from binascii import Error as Base64Error

from fastapi import (
    status,
)
from sqlalchemy import select

from app.dependencies import DbSession, ProfessorUser
from app.enums import CorrectionMode, QuizMode
from app.errors import ApiError, ErrorCode
from app.images import (
    MAX_IMAGE_BYTES,
    InvalidImageError,
    image_pixel_count,
    normalize_image,
)
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)
from app.quiz_session_records import delete_quiz_session_records
from app.schemas import (
    QuestionChoiceCreate,
    QuestionCreate,
    QuestionImportImage,
)
from app.stored_images import store_image


def owned_question_bank(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBank:
    question_bank = session.scalar(
        select(QuestionBank).where(
            QuestionBank.id == question_bank_id,
            QuestionBank.owner_id == professor.id,
        )
    )
    if question_bank is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.QUESTION_BANK_NOT_FOUND,
            "Banque de questions introuvable",
        )
    return question_bank


def discard_training_sessions_using_questions(
    question_ids: list[int],
    session: DbSession,
) -> None:
    """Drop every training attempt that drew any of these questions."""
    if not question_ids:
        return
    common_session_ids = select(QuizSessionQuestion.session_id).where(
        QuizSessionQuestion.question_id.in_(question_ids)
    )
    personalized_session_ids = select(QuizSessionStudentQuestion.session_id).where(
        QuizSessionStudentQuestion.question_id.in_(question_ids)
    )
    training_session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == QuizMode.TRAINING,
                QuizSession.id.in_(common_session_ids.union(personalized_session_ids)),
            )
        )
    )
    if not training_session_ids:
        return
    delete_quiz_session_records(training_session_ids, session)


MAX_IMPORT_IMAGE_BYTES = 64 * 1024 * 1024
# The stored size alone does not bound the work of an import: an image of one
# flat colour is a few kilobytes on disk and twenty million pixels to decode,
# and a single request has room for thousands of them.
MAX_IMPORT_IMAGE_PIXELS = 1_000_000_000


class ImagePixelBudget:
    """The pixels one import may still decode."""

    def __init__(self) -> None:
        self.remaining = MAX_IMPORT_IMAGE_PIXELS

    def spend(self, image_data: bytes) -> None:
        """Count an image before it is decoded, refusing the one too many."""
        self.remaining -= image_pixel_count(image_data)
        if self.remaining < 0:
            raise ApiError(
                status.HTTP_413_CONTENT_TOO_LARGE,
                ErrorCode.IMPORT_IMAGES_TOO_LARGE,
                "Le volume total des images importées est trop important",
            )


def choice_points(
    choice: QuestionChoiceCreate,
    choices: list[QuestionChoiceCreate],
) -> float:
    """Split a single point evenly across correct choices when none is given."""
    if choice.points is not None:
        return choice.points
    if not choice.is_correct:
        return 0
    return 1 / sum(item.is_correct for item in choices)


def add_question(
    question_bank_id: int,
    payload: QuestionCreate,
    session: DbSession,
    *,
    image_data: bytes | None = None,
    image_content_type: str | None = None,
    choice_images: list[tuple[bytes | None, str | None]],
) -> tuple[Question, list[QuestionChoice], QuestionCode | None]:
    if any(
        not choice.label and choice_image_data is None and choice.code_content is None
        for choice, (choice_image_data, _) in zip(
            payload.choices, choice_images, strict=True
        )
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.CHOICE_CONTENT_REQUIRED,
            "Une proposition nécessite du texte, une image ou du code",
        )
    question = Question(
        question_bank_id=question_bank_id,
        prompt=payload.prompt,
        difficulty=payload.difficulty,
        answer_mode=payload.answer_mode,
        answer_mode_disclosed=payload.answer_mode_disclosed,
        response_language=payload.response_language,
        allow_code_execution=payload.allow_code_execution,
        correction_mode=CorrectionMode.AUTOMATIC,
        image_sha256=store_image(session, image_data, image_content_type),
    )
    session.add(question)
    session.flush()
    choices = [
        QuestionChoice(
            question_id=question.id,
            label=choice.label,
            is_correct=choice.is_correct,
            points=choice_points(choice, payload.choices),
            image_sha256=store_image(
                session, choice_image_data, choice_image_content_type
            ),
            code_language=choice.code_language,
            code_content=choice.code_content,
            position=position,
        )
        for position, (
            choice,
            (choice_image_data, choice_image_content_type),
        ) in enumerate(zip(payload.choices, choice_images, strict=True))
    ]
    session.add_all(choices)
    code = None
    if payload.code_language is not None and payload.code_content is not None:
        code = QuestionCode(
            question_id=question.id,
            language=payload.code_language,
            content=payload.code_content,
        )
        session.add(code)
    return question, choices, code


def decode_image_payload(
    image: QuestionImportImage | None,
    budget: ImagePixelBudget | None = None,
) -> tuple[bytes | None, str | None]:
    if image is None:
        return None, None
    try:
        image_data = b64decode(image.data_base64, validate=True)
    except Base64Error, ValueError:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.IMAGE_ENCODING_INVALID,
            "Une image importée n’est pas encodée correctement",
        ) from None
    if not image_data or len(image_data) > MAX_IMAGE_BYTES:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.IMAGE_INVALID,
            "Une image importée est vide ou trop volumineuse",
        )
    if budget is not None:
        budget.spend(image_data)
    try:
        return normalize_image(image_data, image.content_type)
    except InvalidImageError as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.IMAGE_INVALID, str(error)
        ) from None
