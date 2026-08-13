import json
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from collections.abc import Iterator
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.grade_levels import ensure_grade_level, grade_level_import_context
from app.images import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    InvalidImage,
    normalize_image,
)
from app.models import (
    ClassTrainingQuestionBank,
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.question_responses import load_question_responses, question_response
from app.quiz_session_records import delete_quiz_session_records
from app.schemas import (
    MAX_QUESTIONS_PER_BANK,
    QuestionBankCreate,
    QuestionBankResponse,
    QuestionBankUpdate,
    QuestionBatchImport,
    QuestionBatchImportResponse,
    QuestionCreate,
    QuestionImportImage,
    QuestionImportItem,
    QuestionResponse,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])
MAX_IMPORT_IMAGE_BYTES = 64 * 1024 * 1024


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
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    search: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
) -> list[QuestionBankResponse]:
    """Return one filtered page of question banks owned by the professor."""
    filters = [QuestionBank.owner_id == professor.id]
    if search:
        filters.append(QuestionBank.chapter.ilike(f"%{search}%"))
    if grade_level:
        filters.append(QuestionBank.grade_level == grade_level)
    total = (
        session.scalar(select(func.count()).select_from(QuestionBank).where(*filters))
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    rows = session.execute(
        select(
            QuestionBank,
            func.count(Question.id),
            func.sum(case((Question.difficulty == "easy", 1), else_=0)),
            func.sum(case((Question.difficulty == "medium", 1), else_=0)),
            func.sum(case((Question.difficulty == "hard", 1), else_=0)),
        )
        .outerjoin(
            Question,
            Question.question_bank_id == QuestionBank.id,
        )
        .where(*filters)
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [
        QuestionBankResponse.model_validate(question_bank).model_copy(
            update={
                "question_count": question_count,
                "easy_question_count": easy_count or 0,
                "medium_question_count": medium_count or 0,
                "hard_question_count": hard_count or 0,
            }
        )
        for (
            question_bank,
            question_count,
            easy_count,
            medium_count,
            hard_count,
        ) in rows
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
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une banque existe déjà pour ce niveau et ce titre",
        ) from None
    session.refresh(question_bank)
    return question_bank


@router.post("/{question_bank_id}/update", response_model=QuestionBankResponse)
def update_question_bank(
    question_bank_id: int,
    payload: QuestionBankUpdate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuestionBankResponse:
    """Update the title and grade level of a question bank."""
    question_bank = owned_question_bank(question_bank_id, professor, session)
    if question_bank.grade_level != payload.grade_level:
        mismatched_class_ids = select(StudentClass.id).where(
            StudentClass.grade_level != payload.grade_level
        )
        session.execute(
            delete(ClassTrainingQuestionBank).where(
                ClassTrainingQuestionBank.question_bank_id == question_bank.id,
                ClassTrainingQuestionBank.class_id.in_(mismatched_class_ids),
            )
        )
    question_bank.grade_level = payload.grade_level
    question_bank.chapter = payload.chapter
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une banque existe déjà pour ce niveau et ce titre",
        ) from None
    session.refresh(question_bank)
    question_count, easy_count, medium_count, hard_count = session.execute(
        select(
            func.count(Question.id),
            func.sum(case((Question.difficulty == "easy", 1), else_=0)),
            func.sum(case((Question.difficulty == "medium", 1), else_=0)),
            func.sum(case((Question.difficulty == "hard", 1), else_=0)),
        ).where(Question.question_bank_id == question_bank.id)
    ).one()
    return QuestionBankResponse.model_validate(question_bank).model_copy(
        update={
            "question_count": question_count,
            "easy_question_count": easy_count or 0,
            "medium_question_count": medium_count or 0,
            "hard_question_count": hard_count or 0,
        }
    )


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
    if (
        session.scalar(
            select(QuizQuestionBank.quiz_id).where(
                QuizQuestionBank.question_bank_id == question_bank_id
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette banque est utilisée par un quiz",
        )
    question_ids = list(
        session.scalars(
            select(Question.id).where(Question.question_bank_id == question_bank_id)
        )
    )
    for question_id in question_ids:
        discard_training_sessions_using_question(question_id, session)
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.question_bank_id == question_bank_id
        )
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
            detail="Banque de questions introuvable",
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
            detail="Question introuvable",
        )
    return question


def question_is_in_launched_quiz(question_id: int, session: DbSession) -> bool:
    common_assignment = session.scalar(
        select(QuizSessionQuestion.session_id)
        .join(QuizSession, QuizSession.id == QuizSessionQuestion.session_id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSessionQuestion.question_id == question_id,
            Quiz.mode == "exam",
        )
    )
    if common_assignment is not None:
        return True
    return (
        session.scalar(
            select(QuizSessionStudentQuestion.session_id)
            .join(
                QuizSession,
                QuizSession.id == QuizSessionStudentQuestion.session_id,
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSessionStudentQuestion.question_id == question_id,
                Quiz.mode == "exam",
            )
        )
        is not None
    )


def discard_training_sessions_using_question(
    question_id: int,
    session: DbSession,
) -> None:
    common_session_ids = select(QuizSessionQuestion.session_id).where(
        QuizSessionQuestion.question_id == question_id
    )
    personalized_session_ids = select(QuizSessionStudentQuestion.session_id).where(
        QuizSessionStudentQuestion.question_id == question_id
    )
    training_session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.mode == "training",
                QuizSession.id.in_(common_session_ids.union(personalized_session_ids)),
            )
        )
    )
    if not training_session_ids:
        return
    delete_quiz_session_records(training_session_ids, session)


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
        response_language=payload.response_language,
        allow_code_execution=payload.allow_code_execution,
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
            points=(
                choice.points
                if choice.points is not None
                else 1 / sum(item.is_correct for item in payload.choices)
                if choice.is_correct
                else 0
            ),
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
    question_ids = list(
        session.scalars(
            select(Question.id)
            .where(Question.question_bank_id == question_bank_id)
            .order_by(Question.prompt, Question.id)
        )
    )
    return load_question_responses(question_ids, session)


@router.get("/example")
def download_import_example(
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    """Download a complete versioned example of the question batch format."""
    available_grade_levels, grade_level_comment = grade_level_import_context(
        professor.id, session
    )
    example = {
        "version": 1,
        "question_bank": {
            "_comment_grade_level": grade_level_comment,
            "grade_level": "2de",
            "chapter": "Exemple complet",
        },
        "questions": [
            {
                "prompt": "Quelle est la capitale de la France ?",
                "difficulty": "easy",
                "answer_mode": "single",
                "answer_mode_disclosed": True,
                "response_language": None,
                "allow_code_execution": False,
                "choices": [
                    {
                        "label": "Paris",
                        "is_correct": True,
                        "points": 3,
                        "image": None,
                        "code_language": None,
                        "code_content": None,
                    },
                    {
                        "label": "Lyon",
                        "is_correct": False,
                        "points": 0,
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
                "response_language": None,
                "allow_code_execution": False,
                "choices": [
                    {
                        "label": "2",
                        "is_correct": True,
                        "points": 3,
                        "image": None,
                        "code_language": "python",
                        "code_content": "print(2)",
                    },
                    {
                        "label": "3",
                        "is_correct": True,
                        "points": 3,
                        "image": {
                            "content_type": "image/png",
                            "data_base64": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
                                "AAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
                            ),
                        },
                        "code_language": None,
                        "code_content": None,
                    },
                    {
                        "label": "4",
                        "is_correct": False,
                        "points": -1,
                        "image": {
                            "content_type": "image/png",
                            "data_base64": (
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
                                "AAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
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
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
                        "AAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
                    ),
                },
            },
            {
                "prompt": "Écrivez un programme Python qui affiche la somme de 2 et 3.",
                "difficulty": "hard",
                "answer_mode": "written",
                "answer_mode_disclosed": True,
                "response_language": "python",
                "allow_code_execution": True,
                "choices": [
                    {
                        "label": "print(2 + 3)",
                        "is_correct": True,
                        "points": 9,
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
            questions = export_session.scalars(
                select(Question)
                .where(Question.question_bank_id == bank_id)
                .order_by(Question.created_at, Question.id)
            )
            for question in questions:
                choices = list(
                    export_session.scalars(
                        select(QuestionChoice)
                        .where(QuestionChoice.question_id == question.id)
                        .order_by(QuestionChoice.position)
                    )
                )
                code = export_session.scalar(
                    select(QuestionCode).where(QuestionCode.question_id == question.id)
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
                        for choice in choices
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
                yield (",\n" if not first else "\n") + json.dumps(
                    exported_question,
                    ensure_ascii=False,
                    indent=4,
                )
                first = False
                export_session.expunge_all()
        yield "\n  ]\n}\n"

    return StreamingResponse(
        stream_export(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="question-bank-{bank_id}.json"'
        },
    )


def decode_image_payload(
    image: QuestionImportImage | None,
) -> tuple[bytes | None, str | None]:
    if image is None:
        return None, None
    try:
        image_data = b64decode(image.data_base64, validate=True)
    except Base64Error, ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une image importée n’est pas encodée correctement",
        ) from None
    if not image_data or len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une image importée est vide ou trop volumineuse",
        )
    try:
        return normalize_image(image_data, image.content_type)
    except InvalidImage as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None


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
    decoded_images: list[tuple[bytes | None, str | None]] = []
    decoded_choice_images: list[list[tuple[bytes | None, str | None]]] = []
    total_image_bytes = 0
    for question in payload.questions:
        decoded_image = decode_import_image(question)
        choice_images = [
            decode_image_payload(choice.image) for choice in question.choices
        ]
        total_image_bytes += len(decoded_image[0] or b"") + sum(
            len(choice_image[0] or b"") for choice_image in choice_images
        )
        if total_image_bytes > MAX_IMPORT_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Le volume total des images importées est trop important",
            )
        decoded_images.append(decoded_image)
        decoded_choice_images.append(choice_images)
    question_bank = QuestionBank(
        owner_id=professor.id,
        grade_level=payload.question_bank.grade_level,
        chapter=payload.question_bank.chapter,
    )
    session.add(question_bank)
    ensure_grade_level(professor.id, payload.question_bank.grade_level, session)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une banque existe déjà pour ce niveau et ce titre",
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
                    question.difficulty == "easy" for question in payload.questions
                ),
                "medium_question_count": sum(
                    question.difficulty == "medium" for question in payload.questions
                ),
                "hard_question_count": sum(
                    question.difficulty == "hard" for question in payload.questions
                ),
            }
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
    question_count = session.scalar(
        select(func.count())
        .select_from(Question)
        .where(Question.question_bank_id == question_bank_id)
    )
    if (question_count or 0) >= MAX_QUESTIONS_PER_BANK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette banque a atteint le nombre maximal de questions",
        )
    try:
        question_payload = QuestionCreate.model_validate(json.loads(payload))
    except json.JSONDecodeError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question invalide",
        ) from None

    image_data = None
    image_content_type = None
    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Format d’image non pris en charge",
            )
        image_data = await image.read(MAX_IMAGE_BYTES + 1)
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="L’image est trop volumineuse",
            )
        if not image_data:
            image_data = None
        else:
            try:
                image_data, image_content_type = normalize_image(
                    image_data,
                    image.content_type,
                )
            except InvalidImage as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(error),
                ) from None

    choice_images = [
        decode_image_payload(choice.image) for choice in question_payload.choices
    ]
    if (
        len(image_data or b"")
        + sum(len(choice_image[0] or b"") for choice_image in choice_images)
        > MAX_IMPORT_IMAGE_BYTES
    ):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Le volume total des images de la question est trop important",
        )
    question, choices, code = add_question(
        question_bank_id,
        question_payload,
        session,
        image_data=image_data,
        image_content_type=image_content_type,
        choice_images=choice_images,
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
    if question_is_in_launched_quiz(question_id, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette question est utilisée par un quiz déjà lancé",
        )
    try:
        question_payload = QuestionUpdate.model_validate(json.loads(payload))
    except json.JSONDecodeError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question invalide",
        ) from None

    image_data = None
    image_content_type = None
    if image is not None:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Format d’image non pris en charge",
            )
        image_data = await image.read(MAX_IMAGE_BYTES + 1)
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="L’image est trop volumineuse",
            )
        if image_data:
            try:
                image_data, image_content_type = normalize_image(
                    image_data,
                    image.content_type,
                )
            except InvalidImage as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(error),
                ) from None

    question.prompt = question_payload.prompt
    question.difficulty = question_payload.difficulty
    question.answer_mode = question_payload.answer_mode
    question.answer_mode_disclosed = question_payload.answer_mode_disclosed
    question.response_language = question_payload.response_language
    question.allow_code_execution = question_payload.allow_code_execution
    question.correction_mode = "automatic"
    if image_data and image_content_type:
        question.image_data = image_data
        question.image_content_type = image_content_type
    elif question_payload.remove_image:
        question.image_data = None
        question.image_content_type = None

    existing_choices = list(
        session.scalars(
            select(QuestionChoice).where(QuestionChoice.question_id == question.id)
        )
    )
    # Move existing rows out of the final position range before applying a
    # reorder. SQLite checks the unique (question_id, position) constraint for
    # every row update, so swapping positions directly can fail transiently.
    temporary_position = (
        max((choice.position for choice in existing_choices), default=-1) + 1
    )
    for offset, choice in enumerate(existing_choices):
        choice.position = temporary_position + offset
    session.flush()
    existing_choices_by_id = {choice.id: choice for choice in existing_choices}
    submitted_choice_ids = {
        choice.id for choice in question_payload.choices if choice.id is not None
    }
    if not submitted_choice_ids.issubset(existing_choices_by_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Proposition de réponse invalide",
        )
    replacement_choice_images = []
    for choice in question_payload.choices:
        new_image_data, new_image_content_type = decode_image_payload(choice.image)
        existing_choice = (
            existing_choices_by_id.get(choice.id) if choice.id is not None else None
        )
        if (
            new_image_data is None
            and not choice.remove_image
            and existing_choice is not None
        ):
            new_image_data = existing_choice.image_data
            new_image_content_type = existing_choice.image_content_type
        replacement_choice_images.append((new_image_data, new_image_content_type))

    retained_question_image = (
        image_data
        if image_data
        else None
        if question_payload.remove_image
        else question.image_data
    )
    if (
        len(retained_question_image or b"")
        + sum(
            len(choice_image_data or b"")
            for choice_image_data, _ in replacement_choice_images
        )
        > MAX_IMPORT_IMAGE_BYTES
    ):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Le volume total des images de la question est trop important",
        )

    session.execute(delete(QuestionCode).where(QuestionCode.question_id == question.id))
    choices = []
    for position, (
        choice_payload,
        (choice_image_data, choice_image_content_type),
    ) in enumerate(
        zip(
            question_payload.choices,
            replacement_choice_images,
            strict=True,
        )
    ):
        choice = (
            existing_choices_by_id[choice_payload.id]
            if choice_payload.id is not None
            else QuestionChoice(question_id=question.id)
        )
        choice.label = choice_payload.label
        choice.is_correct = choice_payload.is_correct
        choice.points = (
            choice_payload.points
            if choice_payload.points is not None
            else 1 / sum(item.is_correct for item in question_payload.choices)
            if choice_payload.is_correct
            else 0
        )
        choice.image_data = choice_image_data
        choice.image_content_type = choice_image_content_type
        choice.code_language = choice_payload.code_language
        choice.code_content = choice_payload.code_content
        choice.position = position
        choices.append(choice)
        session.add(choice)
    removed_choice_ids = set(existing_choices_by_id) - submitted_choice_ids
    if removed_choice_ids:
        session.execute(
            delete(QuestionChoice).where(QuestionChoice.id.in_(removed_choice_ids))
        )
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
    session.flush()
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
    if question_is_in_launched_quiz(question_id, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette question est utilisée par un quiz déjà lancé",
        )
    discard_training_sessions_using_question(question_id, session)
    session.execute(
        delete(QuestionChoice).where(QuestionChoice.question_id == question_id)
    )
    session.execute(delete(QuestionCode).where(QuestionCode.question_id == question_id))
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
            detail="Image de la question introuvable",
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
    if choice is None or choice.image_data is None or choice.image_content_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la réponse introuvable",
        )
    return Response(
        content=choice.image_data,
        media_type=choice.image_content_type,
    )
