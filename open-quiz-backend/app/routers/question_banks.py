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
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.dependencies import DbSession, ProfessorUser
from app.models import Question, QuestionBank, QuestionChoice, QuestionCode
from app.schemas import (
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBatchImport,
    QuestionCreate,
    QuestionImportItem,
    QuestionResponse,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_QUESTION_IMAGE_BYTES = 4 * 1024 * 1024


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
        correction_mode=question.correction_mode,
        has_image=question.image_content_type is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=choices,
        created_at=question.created_at,
    )


def add_question(
    question_bank_id: int,
    payload: QuestionCreate,
    session: DbSession,
    *,
    image_data: bytes | None = None,
    image_content_type: str | None = None,
) -> tuple[Question, list[QuestionChoice], QuestionCode | None]:
    question = Question(
        question_bank_id=question_bank_id,
        prompt=payload.prompt,
        difficulty=payload.difficulty,
        answer_mode=payload.answer_mode,
        answer_mode_disclosed=payload.answer_mode_disclosed,
        correction_mode=payload.correction_mode,
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
            position=position,
        )
        for position, choice in enumerate(payload.choices)
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
def download_import_example(_: ProfessorUser) -> JSONResponse:
    """Download a complete versioned example of the question batch format."""
    example = {
        "version": 1,
        "question_bank": {
            "grade_level": "5e",
            "chapter": "Exemple complet",
        },
        "questions": [
            {
                "prompt": "Quelle est la capitale de la France ?",
                "difficulty": "easy",
                "answer_mode": "single",
                "answer_mode_disclosed": True,
                "correction_mode": "automatic",
                "choices": [
                    {"label": "Paris", "is_correct": True},
                    {"label": "Lyon", "is_correct": False},
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
                "correction_mode": "automatic",
                "choices": [
                    {"label": "2", "is_correct": True},
                    {"label": "3", "is_correct": True},
                    {"label": "4", "is_correct": False},
                ],
                "code_language": None,
                "code_content": None,
                "image": None,
            },
            {
                "prompt": "Expliquez le résultat produit par ce code.",
                "difficulty": "hard",
                "answer_mode": "single",
                "answer_mode_disclosed": True,
                "correction_mode": "manual",
                "choices": [
                    {"label": "Réponse proposée A", "is_correct": False},
                    {"label": "Réponse proposée B", "is_correct": False},
                ],
                "code_language": "python",
                "code_content": "values = [1, 2, 3]\nprint(sum(values))",
                "image": None,
            },
            {
                "prompt": "Sélectionnez les éléments visibles sur l’image.",
                "difficulty": "medium",
                "answer_mode": "multiple",
                "answer_mode_disclosed": True,
                "correction_mode": "manual",
                "choices": [
                    {"label": "Élément A", "is_correct": False},
                    {"label": "Élément B", "is_correct": False},
                ],
                "code_language": None,
                "code_content": None,
                "image": {
                    "content_type": "image/png",
                    "data_base64": (
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                        "AAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
                    ),
                },
            },
        ],
    }
    return JSONResponse(
        content=example,
        headers={
            "Content-Disposition": (
                'attachment; filename="open-quiz-questions-example.json"'
            )
        },
    )


@router.get("/{question_bank_id}/export")
def export_questions(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> JSONResponse:
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
                "correction_mode": question.correction_mode,
                "choices": [
                    {
                        "label": choice.label,
                        "is_correct": choice.is_correct,
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
    return JSONResponse(
        content={
            "version": 1,
            "question_bank": {
                "grade_level": question_bank.grade_level,
                "chapter": question_bank.chapter,
            },
            "questions": exported_questions,
        },
        headers={
            "Content-Disposition": (
                f'attachment; filename="question-bank-{question_bank.id}.json"'
            )
        },
    )


def decode_import_image(
    payload: QuestionImportItem,
) -> tuple[bytes | None, str | None]:
    if payload.image is None:
        return None, None
    try:
        image_data = b64decode(payload.image.data_base64, validate=True)
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
    return image_data, payload.image.content_type


@router.post(
    "/{question_bank_id}/import",
    response_model=list[QuestionResponse],
    status_code=status.HTTP_201_CREATED,
)
def import_questions(
    question_bank_id: int,
    payload: QuestionBatchImport,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionResponse]:
    """Atomically import a batch of questions into a professor's bank."""
    owned_question_bank(question_bank_id, professor, session)
    decoded_images = [decode_import_image(question) for question in payload.questions]
    created = [
        add_question(
            question_bank_id,
            question,
            session,
            image_data=image_data,
            image_content_type=image_content_type,
        )
        for question, (image_data, image_content_type) in zip(
            payload.questions,
            decoded_images,
            strict=True,
        )
    ]
    session.commit()
    for question, _, _ in created:
        session.refresh(question)
    return [
        question_response(question, choices, code)
        for question, choices, code in created
    ]


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
    question.correction_mode = question_payload.correction_mode
    if image_data and image_content_type:
        question.image_data = image_data
        question.image_content_type = image_content_type
    elif question_payload.remove_image:
        question.image_data = None
        question.image_content_type = None

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
            position=position,
        )
        for position, choice in enumerate(question_payload.choices)
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
