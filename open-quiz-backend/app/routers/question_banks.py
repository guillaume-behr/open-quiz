import json
from base64 import b64decode, b64encode
from binascii import Error as Base64Error

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.dependencies import DbSession, ProfessorUser
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    QuizQuestionBank,
    QuizSessionQuestion,
)
from app.schemas import (
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBatchImport,
    QuestionBatchImportResponse,
    QuestionCreate,
    QuestionImportImage,
    QuestionImportItem,
    QuestionResponse,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_QUESTION_IMAGE_BYTES = 20 * 1024 * 1024


def downloadable_json(content: object, filename: str) -> Response:
    return Response(
        content=json.dumps(content, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("", response_model=list[QuestionBankResponse])
def list_question_banks(
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBankResponse]:
    """Return question banks owned by the authenticated professor."""
    rows = session.execute(
        select(QuestionBank, func.count(Question.id))
        .outerjoin(
            Question,
            Question.question_bank_id == QuestionBank.id,
        )
        .where(QuestionBank.owner_id == professor.id)
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
    )
    return [
        QuestionBankResponse.model_validate(question_bank).model_copy(
            update={"question_count": question_count}
        )
        for question_bank, question_count in rows
    ]


@router.post(
    "",
    response_model=QuestionBankResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question_bank(
    payload: QuestionBankCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBank:
    """Create a question bank classified by grade level and chapter."""
    question_bank = QuestionBank(
        owner_id=professor.id,
        grade_level=payload.grade_level,
        chapter=payload.chapter,
    )
    session.add(question_bank)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A question bank already exists for this grade level and chapter",
        ) from None
    session.refresh(question_bank)
    return question_bank


@router.delete(
    "/{question_bank_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_question_bank(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    """Delete a question bank and every question it contains."""
    owned_question_bank(question_bank_id, professor, session)
    if session.scalar(
        select(QuizQuestionBank.quiz_id).where(
            QuizQuestionBank.question_bank_id == question_bank_id
        )
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This question bank is used by a quiz",
        )
    question_ids = select(Question.id).where(
        Question.question_bank_id == question_bank_id
    )
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id.in_(question_ids))
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
    )
    session.execute(
        delete(Question).where(Question.question_bank_id == question_bank_id)
    )
    session.execute(delete(QuestionBank).where(QuestionBank.id == question_bank_id))
    session.commit()


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question bank not found",
        )
    return question_bank


def owned_question(
    question_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Question:
    question = session.scalar(
        select(Question)
        .join(QuestionBank, QuestionBank.id == Question.question_bank_id)
        .where(
            Question.id == question_id,
            QuestionBank.owner_id == professor.id,
        )
    )
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )
    return question


def question_response(
    question: Question,
    choices: list[QuestionChoice],
    code: QuestionCode | None = None,
) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        question_bank_id=question.question_bank_id,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        answer_mode_disclosed=question.answer_mode_disclosed,
        has_image=question.image_content_type is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=[
            {
                "id": choice.id,
                "label": choice.label,
                "is_correct": choice.is_correct,
                "points": choice.points,
                "position": choice.position,
                "has_image": choice.image_content_type is not None,
                "code_language": choice.code_language,
                "code_content": choice.code_content,
            }
            for choice in choices
        ],
        created_at=question.created_at,
    )


def add_question(
    question_bank_id: int,
    payload: QuestionCreate,
    session: DbSession,
    *,
    image_data: bytes | None = None,
    image_content_type: str | None = None,
    choice_images: list[tuple[bytes | None, str | None]] | None = None,
) -> tuple[Question, list[QuestionChoice], QuestionCode | None]:
    if choice_images is None:
        choice_images = [
            decode_image_payload(choice.image) for choice in payload.choices
        ]
    question = Question(
        question_bank_id=question_bank_id,
        prompt=payload.prompt,
        difficulty=payload.difficulty,
        answer_mode=payload.answer_mode,
        answer_mode_disclosed=payload.answer_mode_disclosed,
        correction_mode="automatic",
        image_data=image_data,
        image_content_type=image_content_type,
    )
    session.add(question)
    session.flush()
    choices = [
        QuestionChoice(
            question_id=question.id,
            label=choice.label,
            is_correct=choice.is_correct,
            points=choice.points,
            image_data=choice_image_data,
            image_content_type=choice_image_content_type,
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


@router.get(
    "/{question_bank_id}/questions",
    response_model=list[QuestionResponse],
)
def list_questions(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionResponse]:
    """Return the questions in one of the professor's banks."""
    owned_question_bank(question_bank_id, professor, session)
    questions = list(
        session.scalars(
            select(Question)
            .options(defer(Question.image_data))
            .where(Question.question_bank_id == question_bank_id)
            .order_by(Question.created_at.desc(), Question.id.desc())
        )
    )
    if not questions:
        return []
    question_ids = [question.id for question in questions]
    choices_by_question: dict[int, list[QuestionChoice]] = {
        question_id: [] for question_id in question_ids
    }
    for choice in session.scalars(
        select(QuestionChoice)
        .options(defer(QuestionChoice.image_data))
        .where(QuestionChoice.question_id.in_(question_ids))
        .order_by(QuestionChoice.question_id, QuestionChoice.position)
    ):
        choices_by_question[choice.question_id].append(choice)
    codes_by_question = {
        code.question_id: code
        for code in session.scalars(
            select(QuestionCode).where(
                QuestionCode.question_id.in_(question_ids)
            )
        )
    }
    return [
        question_response(
            question,
            choices_by_question[question.id],
            codes_by_question.get(question.id),
        )
        for question in questions
    ]


@router.get("/example")
def download_import_example(_: ProfessorUser) -> Response:
    """Download a complete versioned example of the question batch format."""
    example = {
        "version": 1,
        "question_bank": {
            "grade_level": "2de",
            "chapter": "Exemple complet",
        },
        "questions": [
            {
                "prompt": "Quelle est la capitale de la France ?",
                "difficulty": "easy",
                "answer_mode": "single",
                "answer_mode_disclosed": True,
                "choices": [
                    {
                        "label": "Paris",
                        "is_correct": True,
                        "points": 1,
                        "image": None,
                        "code_language": None,
                        "code_content": None,
                    },
                    {
                        "label": "Lyon",
                        "is_correct": False,
                        "points": -0.25,
                        "image": None,
                        "code_language": None,
                        "code_content": None,
                    },
                ],
                "code_language": None,
                "code_content": None,
                "image": None,
            },
            {
                "prompt": "Quels nombres sont premiers ?",
                "difficulty": "medium",
                "answer_mode": "multiple",
                "answer_mode_disclosed": False,
                "choices": [
                    {
                        "label": "2",
                        "is_correct": True,
                        "points": 0.5,
                        "image": None,
                        "code_language": "python",
                        "code_content": "print(2)",
                    },
                    {
                        "label": "3",
                        "is_correct": True,
                        "points": 0.5,
                        "image": {
                            "content_type": "image/png",
                            "data_base64": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                                "AAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
                            ),
                        },
                        "code_language": None,
                        "code_content": None,
                    },
                    {
                        "label": "4",
                        "is_correct": False,
                        "points": -0.25,
                        "image": {
                            "content_type": "image/png",
                            "data_base64": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                                "AAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
                            ),
                        },
                        "code_language": "javascript",
                        "code_content": "console.log(4)",
                    },
                ],
                "code_language": "python",
                "code_content": "numbers = [2, 3, 4]\nprint(numbers)",
                "image": {
                    "content_type": "image/png",
                    "data_base64": (
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                        "AAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
                    ),
                },
            },
            {
                "prompt": "Expliquez pourquoi la Terre tourne autour du Soleil.",
                "difficulty": "hard",
                "answer_mode": "written",
                "answer_mode_disclosed": True,
                "choices": [
                    {
                        "label": "La gravitation maintient la Terre en orbite autour du Soleil.",
                        "is_correct": True,
                        "points": 1,
                        "image": None,
                        "code_language": None,
                        "code_content": None,
                    },
                ],
                "code_language": None,
                "code_content": None,
                "image": None,
            },
        ],
    }
    return downloadable_json(
        example,
        "open-quiz-questions-example.json",
    )


@router.get("/{question_bank_id}/export")
def export_questions(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Export every question in a bank as a versioned JSON document."""
    question_bank = owned_question_bank(question_bank_id, professor, session)
    questions = list(
        session.scalars(
            select(Question)
            .where(Question.question_bank_id == question_bank_id)
            .order_by(Question.created_at, Question.id)
        )
    )
    question_ids = [question.id for question in questions]
    choices_by_question: dict[int, list[QuestionChoice]] = {
        question_id: [] for question_id in question_ids
    }
    codes_by_question: dict[int, QuestionCode] = {}
    if question_ids:
        for choice in session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id.in_(question_ids))
            .order_by(QuestionChoice.question_id, QuestionChoice.position)
        ):
            choices_by_question[choice.question_id].append(choice)
        codes_by_question = {
            code.question_id: code
            for code in session.scalars(
                select(QuestionCode).where(
                    QuestionCode.question_id.in_(question_ids)
                )
            )
        }
    exported_questions = []
    for question in questions:
        code = codes_by_question.get(question.id)
        exported_questions.append(
            {
                "prompt": question.prompt,
                "difficulty": question.difficulty,
                "answer_mode": question.answer_mode,
                "answer_mode_disclosed": question.answer_mode_disclosed,
                "choices": [
                    {
                        "label": choice.label,
                        "is_correct": choice.is_correct,
                        "points": choice.points,
                        "image": (
                            {
                                "content_type": choice.image_content_type,
                                "data_base64": b64encode(
                                    choice.image_data
                                ).decode(),
                            }
                            if choice.image_data is not None
                            and choice.image_content_type is not None
                            else None
                        ),
                        "code_language": choice.code_language,
                        "code_content": choice.code_content,
                    }
                    for choice in choices_by_question[question.id]
                ],
                "code_language": code.language if code else None,
                "code_content": code.content if code else None,
                "image": (
                    {
                        "content_type": question.image_content_type,
                        "data_base64": b64encode(question.image_data).decode(),
                    }
                    if question.image_data is not None
                    and question.image_content_type is not None
                    else None
                ),
            }
        )
    return downloadable_json(
        {
            "version": 1,
            "question_bank": {
                "grade_level": question_bank.grade_level,
                "chapter": question_bank.chapter,
            },
            "questions": exported_questions,
        },
        f"question-bank-{question_bank.id}.json",
    )


def decode_image_payload(
    image: QuestionImportImage | None,
) -> tuple[bytes | None, str | None]:
    if image is None:
        return None, None
    try:
        image_data = b64decode(image.data_base64, validate=True)
    except (Base64Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An imported image is not valid base64",
        ) from None
    if not image_data or len(image_data) > MAX_QUESTION_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An imported image is empty or too large",
        )
    return image_data, image.content_type


def decode_import_image(
    payload: QuestionImportItem,
) -> tuple[bytes | None, str | None]:
    return decode_image_payload(payload.image)


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
    decoded_images = [decode_import_image(question) for question in payload.questions]
    decoded_choice_images = [
        [decode_image_payload(choice.image) for choice in question.choices]
        for question in payload.questions
    ]
    question_bank = QuestionBank(
        owner_id=professor.id,
        grade_level=payload.question_bank.grade_level,
        chapter=payload.question_bank.chapter,
    )
    session.add(question_bank)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A question bank already exists for this grade level and chapter",
        ) from None

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
    session.refresh(question_bank)
    for question, _, _ in created:
        session.refresh(question)
    questions = [
        question_response(question, choices, code)
        for question, choices, code in created
    ]
    return QuestionBatchImportResponse(
        question_bank=QuestionBankResponse.model_validate(question_bank).model_copy(
            update={"question_count": len(questions)}
        ),
        questions=questions,
    )


@router.post(
    "/{question_bank_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
    payload: str = Form(),
    image: UploadFile | None = File(default=None),
) -> QuestionResponse:
    """Create a choice question, optionally with a private image."""
    owned_question_bank(question_bank_id, professor, session)
    try:
        question_payload = QuestionCreate.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid question",
        ) from None

    image_data = None
    image_content_type = None
    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image format",
            )
        image_data = await image.read(MAX_QUESTION_IMAGE_BYTES + 1)
        if len(image_data) > MAX_QUESTION_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The image is too large",
            )
        if not image_data:
            image_data = None
        else:
            image_content_type = image.content_type

    question, choices, code = add_question(
        question_bank_id,
        question_payload,
        session,
        image_data=image_data,
        image_content_type=image_content_type,
    )
    session.commit()
    session.refresh(question)
    return question_response(question, choices, code)


@router.post(
    "/questions/{question_id}/update",
    response_model=QuestionResponse,
)
async def update_question(
    question_id: int,
    professor: ProfessorUser,
    session: DbSession,
    payload: str = Form(),
    image: UploadFile | None = File(default=None),
) -> QuestionResponse:
    """Update a professor's question and replace its answer configuration."""
    question = owned_question(question_id, professor, session)
    try:
        question_payload = QuestionUpdate.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid question",
        ) from None

    image_data = None
    image_content_type = None
    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image format",
            )
        image_data = await image.read(MAX_QUESTION_IMAGE_BYTES + 1)
        if len(image_data) > MAX_QUESTION_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The image is too large",
            )
        if image_data:
            image_content_type = image.content_type

    question.prompt = question_payload.prompt
    question.difficulty = question_payload.difficulty
    question.answer_mode = question_payload.answer_mode
    question.answer_mode_disclosed = question_payload.answer_mode_disclosed
    question.correction_mode = "automatic"
    if image_data and image_content_type:
        question.image_data = image_data
        question.image_content_type = image_content_type
    elif question_payload.remove_image:
        question.image_data = None
        question.image_content_type = None

    existing_choices = list(
        session.scalars(
            select(QuestionChoice).where(
                QuestionChoice.question_id == question.id
            )
        )
    )
    existing_choices_by_id = {choice.id: choice for choice in existing_choices}
    submitted_choice_ids = {
        choice.id for choice in question_payload.choices if choice.id is not None
    }
    if not submitted_choice_ids.issubset(existing_choices_by_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid answer choice",
        )
    replacement_choice_images = []
    for choice in question_payload.choices:
        new_image_data, new_image_content_type = decode_image_payload(choice.image)
        existing_choice = (
            existing_choices_by_id.get(choice.id)
            if choice.id is not None
            else None
        )
        if (
            new_image_data is None
            and not choice.remove_image
            and existing_choice is not None
        ):
            new_image_data = existing_choice.image_data
            new_image_content_type = existing_choice.image_content_type
        replacement_choice_images.append(
            (new_image_data, new_image_content_type)
        )

    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id == question.id)
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id == question.id)
    )
    choices = [
        QuestionChoice(
            question_id=question.id,
            label=choice.label,
            is_correct=choice.is_correct,
            points=choice.points,
            image_data=choice_image_data,
            image_content_type=choice_image_content_type,
            code_language=choice.code_language,
            code_content=choice.code_content,
            position=position,
        )
        for position, (
            choice,
            (choice_image_data, choice_image_content_type),
        ) in enumerate(
            zip(
                question_payload.choices,
                replacement_choice_images,
                strict=True,
            )
        )
    ]
    session.add_all(choices)
    code = None
    if (
        question_payload.code_language is not None
        and question_payload.code_content is not None
    ):
        code = QuestionCode(
            question_id=question.id,
            language=question_payload.code_language,
            content=question_payload.code_content,
        )
        session.add(code)
    session.commit()
    session.refresh(question)
    return question_response(question, choices, code)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_question(
    question_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    """Delete one question owned by the authenticated professor."""
    owned_question(question_id, professor, session)
    if session.scalar(
        select(QuizSessionQuestion.session_id).where(
            QuizSessionQuestion.question_id == question_id
        )
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This question is used by a launched quiz",
        )
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id == question_id)
    )
    session.execute(
        delete(QuestionCode).where(QuestionCode.question_id == question_id)
    )
    session.execute(delete(Question).where(Question.id == question_id))
    session.commit()


@router.get("/questions/{question_id}/image")
def get_question_image(
    question_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Return a private image attached to one of the professor's questions."""
    question = session.scalar(
        select(Question)
        .join(QuestionBank, QuestionBank.id == Question.question_bank_id)
        .where(
            Question.id == question_id,
            QuestionBank.owner_id == professor.id,
        )
    )
    if (
        question is None
        or question.image_data is None
        or question.image_content_type is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question image not found",
        )
    return Response(
        content=question.image_data,
        media_type=question.image_content_type,
    )


@router.get("/choices/{choice_id}/image")
def get_choice_image(
    choice_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Return a private image attached to one answer choice."""
    choice = session.scalar(
        select(QuestionChoice)
        .join(Question, Question.id == QuestionChoice.question_id)
        .join(QuestionBank, QuestionBank.id == Question.question_bank_id)
        .where(
            QuestionChoice.id == choice_id,
            QuestionBank.owner_id == professor.id,
        )
    )
    if (
        choice is None
        or choice.image_data is None
        or choice.image_content_type is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer image not found",
        )
    return Response(
        content=choice.image_data,
        media_type=choice.image_content_type,
    )
