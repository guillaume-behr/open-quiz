"""Questions of a bank: listing, creation, edits, deletion and images.

Editing a question regrades the finished sessions that used it, and a
question that any exam session has drawn cannot be deleted. Uploaded images
are normalized; these routes serve them only to the bank's owner, and students
load them through their participation (app/routers/student_sessions.py).
"""

import json

from fastapi import (
    APIRouter,
    File,
    Form,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import delete, func, select, union
from sqlalchemy.orm import Session

from app.dependencies import DbSession, ProfessorUser
from app.enums import CorrectionMode, QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.images import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    InvalidImageError,
    normalize_image,
)
from app.live_quiz import (
    active_quiz_sessions_topic,
    makeup_sessions_topic,
    quiz_session_topic,
    student_session_topic,
)
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)
from app.question_records import (
    MAX_IMPORT_IMAGE_BYTES,
    add_question,
    choice_points,
    decode_image_payload,
    discard_training_sessions_using_questions,
    owned_question_bank,
)
from app.question_responses import load_question_responses, question_response
from app.schemas import (
    MAX_QUESTIONS_PER_BANK,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
)
from app.services.grading import compute_final_scores
from app.stored_images import store_image, stored_image_sizes

router = APIRouter(prefix="/api/question-banks", tags=["question banks"])


def normalized_uploaded_image(
    image: UploadFile | None,
) -> tuple[bytes | None, str | None]:
    """Validate and normalize an optional uploaded question image."""
    if image is None:
        return None, None
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise ApiError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            ErrorCode.IMAGE_TYPE_UNSUPPORTED,
            "Format d’image non pris en charge",
        )
    image_data = image.file.read(MAX_IMAGE_BYTES + 1)
    if len(image_data) > MAX_IMAGE_BYTES:
        raise ApiError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            ErrorCode.IMAGE_TOO_LARGE,
            "L’image est trop volumineuse",
        )
    if not image_data:
        return None, None
    try:
        return normalize_image(image_data, image.content_type)
    except InvalidImageError as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.IMAGE_INVALID, str(error)
        ) from None


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
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.QUESTION_NOT_FOUND,
            "Question introuvable",
        )
    return question


def question_is_in_launched_quiz(question_id: int, session: DbSession) -> bool:
    common_assignment = session.scalar(
        select(QuizSessionQuestion.session_id)
        .join(QuizSession, QuizSession.id == QuizSessionQuestion.session_id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSessionQuestion.question_id == question_id,
            Quiz.mode == QuizMode.EXAM,
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
                Quiz.mode == QuizMode.EXAM,
            )
        )
        is not None
    )


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


@router.post(
    "/{question_bank_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    question_bank_id: int,
    professor: ProfessorUser,
    session: DbSession,
    payload: str = Form(),
    image: UploadFile | None = File(default=None),
) -> QuestionResponse:
    """Create a choice or written question, optionally with a private image."""
    owned_question_bank(question_bank_id, professor, session)
    question_count = session.scalar(
        select(func.count())
        .select_from(Question)
        .where(Question.question_bank_id == question_bank_id)
    )
    if (question_count or 0) >= MAX_QUESTIONS_PER_BANK:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUESTION_BANK_FULL,
            "Cette banque a atteint le nombre maximal de questions",
        )
    try:
        question_payload = QuestionCreate.model_validate(json.loads(payload))
    except json.JSONDecodeError, ValidationError:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.QUESTION_INVALID,
            "Question invalide",
        ) from None

    image_data, image_content_type = normalized_uploaded_image(image)

    choice_images = [
        decode_image_payload(choice.image) for choice in question_payload.choices
    ]
    if (
        len(image_data or b"")
        + sum(len(choice_image[0] or b"") for choice_image in choice_images)
        > MAX_IMPORT_IMAGE_BYTES
    ):
        raise ApiError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            ErrorCode.QUESTION_IMAGES_TOO_LARGE,
            "Le volume total des images de la question est trop important",
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


def regrade_affected_sessions(
    question_id: int,
    professor_id: int,
    request: Request,
    session: DbSession,
) -> None:
    session_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                QuizSession.id.in_(
                    union(
                        select(QuizSessionQuestion.session_id).where(
                            QuizSessionQuestion.question_id == question_id
                        ),
                        select(QuizSessionStudentQuestion.session_id).where(
                            QuizSessionStudentQuestion.question_id == question_id
                        ),
                        select(QuizAnswer.session_id).where(
                            QuizAnswer.question_id == question_id
                        ),
                    )
                )
            )
        )
    )
    if not session_ids:
        session.commit()
        return

    affected_sessions = list(
        session.scalars(select(QuizSession).where(QuizSession.id.in_(session_ids)))
    )

    has_makeup_child = False
    for quiz_session in affected_sessions:
        if quiz_session.status == SessionStatus.FINISHED:
            compute_final_scores(quiz_session, session)
        if quiz_session.makeup_session_id is not None:
            has_makeup_child = True

    session.commit()

    live_hub = request.app.state.live_quiz_hub
    for quiz_session in affected_sessions:
        live_hub.publish(quiz_session_topic(quiz_session.id))
        live_hub.publish(student_session_topic(quiz_session.join_code))
    live_hub.publish(active_quiz_sessions_topic(professor_id))
    if has_makeup_child:
        live_hub.publish(makeup_sessions_topic(professor_id))


# Per submitted choice: new image bytes and type, or the key of the image kept.
ChoiceImagePlan = tuple[bytes | None, str | None, str | None]


def parsed_question_update(payload: str) -> QuestionUpdate:
    try:
        return QuestionUpdate.model_validate(json.loads(payload))
    except json.JSONDecodeError, ValidationError:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.QUESTION_INVALID,
            "Question invalide",
        ) from None


def apply_question_fields(
    question: Question,
    question_payload: QuestionUpdate,
    image: tuple[bytes | None, str | None],
    session: Session,
) -> None:
    image_data, image_content_type = image
    question.prompt = question_payload.prompt
    question.difficulty = question_payload.difficulty
    question.answer_mode = question_payload.answer_mode
    question.answer_mode_disclosed = question_payload.answer_mode_disclosed
    question.response_language = question_payload.response_language
    question.allow_code_execution = question_payload.allow_code_execution
    question.correction_mode = CorrectionMode.AUTOMATIC
    if image_data and image_content_type:
        question.image_sha256 = store_image(session, image_data, image_content_type)
    elif question_payload.remove_image:
        question.image_sha256 = None


def parked_choices(question: Question, session: Session) -> dict[int, QuestionChoice]:
    """The question's current choices, moved out of the positions to reuse."""
    existing_choices = list(
        session.scalars(
            select(QuestionChoice).where(QuestionChoice.question_id == question.id)
        )
    )
    # Move existing rows out of the final position range before applying a
    # reorder. The unique (question_id, position) constraint is checked for
    # every row update, so swapping positions directly can fail transiently.
    temporary_position = (
        max((choice.position for choice in existing_choices), default=-1) + 1
    )
    for offset, choice in enumerate(existing_choices):
        choice.position = temporary_position + offset
    session.flush()
    return {choice.id: choice for choice in existing_choices}


def choice_image_plans(
    question_payload: QuestionUpdate,
    existing_choices_by_id: dict[int, QuestionChoice],
) -> list[ChoiceImagePlan]:
    submitted_choice_ids = {
        choice.id for choice in question_payload.choices if choice.id is not None
    }
    if not submitted_choice_ids.issubset(existing_choices_by_id):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.CHOICE_INVALID,
            "Proposition de réponse invalide",
        )
    # Each choice keeps its image (by key), replaces it (with new bytes) or
    # loses it.
    replacement_choice_images: list[ChoiceImagePlan] = []
    for submitted in question_payload.choices:
        new_image_data, new_image_content_type = decode_image_payload(submitted.image)
        existing_choice = (
            existing_choices_by_id.get(submitted.id)
            if submitted.id is not None
            else None
        )
        kept_image = (
            existing_choice.image_sha256
            if new_image_data is None
            and not submitted.remove_image
            and existing_choice is not None
            else None
        )
        replacement_choice_images.append(
            (new_image_data, new_image_content_type, kept_image)
        )
    return replacement_choice_images


def require_choice_content(
    question_payload: QuestionUpdate, plans: list[ChoiceImagePlan]
) -> None:
    if any(
        not choice.label
        and choice_image_data is None
        and kept_image is None
        and choice.code_content is None
        for choice, (choice_image_data, _, kept_image) in zip(
            question_payload.choices,
            plans,
            strict=True,
        )
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.CHOICE_CONTENT_REQUIRED,
            "Une proposition nécessite du texte, une image ou du code",
        )


def require_image_budget(
    question: Question, plans: list[ChoiceImagePlan], session: Session
) -> None:
    # question.image_sha256 already reflects the replacement or the removal
    # applied above, so it is the image this question will actually keep.
    kept_sizes = stored_image_sizes(
        session,
        [
            digest
            for digest in [
                question.image_sha256,
                *(kept for _, _, kept in plans),
            ]
            if digest is not None
        ],
    )
    if (
        kept_sizes.get(question.image_sha256 or "", 0)
        + sum(
            len(choice_image_data or b"") + kept_sizes.get(kept_image or "", 0)
            for choice_image_data, _, kept_image in plans
        )
        > MAX_IMPORT_IMAGE_BYTES
    ):
        raise ApiError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            ErrorCode.QUESTION_IMAGES_TOO_LARGE,
            "Le volume total des images de la question est trop important",
        )


def write_choices_and_code(
    question: Question,
    question_payload: QuestionUpdate,
    plans: list[ChoiceImagePlan],
    existing_choices_by_id: dict[int, QuestionChoice],
    session: Session,
) -> tuple[list[QuestionChoice], QuestionCode | None]:
    session.execute(delete(QuestionCode).where(QuestionCode.question_id == question.id))
    choices = []
    for position, (
        choice_payload,
        (choice_image_data, choice_image_content_type, kept_image),
    ) in enumerate(
        zip(
            question_payload.choices,
            plans,
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
        choice.points = choice_points(choice_payload, question_payload.choices)
        choice.image_sha256 = (
            store_image(session, choice_image_data, choice_image_content_type)
            if choice_image_data is not None
            else kept_image
        )
        choice.code_language = choice_payload.code_language
        choice.code_content = choice_payload.code_content
        choice.position = position
        choices.append(choice)
        session.add(choice)
    submitted_choice_ids = {
        choice.id for choice in question_payload.choices if choice.id is not None
    }
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
    return choices, code


@router.post(
    "/questions/{question_id}/update",
    response_model=QuestionResponse,
)
def update_question(
    question_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    payload: str = Form(),
    image: UploadFile | None = File(default=None),
) -> QuestionResponse:
    """Update a professor's question and replace its answer configuration."""
    question = owned_question(question_id, professor, session)
    question_payload = parsed_question_update(payload)
    uploaded_image = normalized_uploaded_image(image)
    apply_question_fields(question, question_payload, uploaded_image, session)
    existing_choices_by_id = parked_choices(question, session)
    plans = choice_image_plans(question_payload, existing_choices_by_id)
    require_choice_content(question_payload, plans)
    require_image_budget(question, plans, session)
    choices, code = write_choices_and_code(
        question, question_payload, plans, existing_choices_by_id, session
    )
    session.flush()
    regrade_affected_sessions(question.id, professor.id, request, session)
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
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUESTION_IN_LAUNCHED_QUIZ,
            "Cette question est utilisée par un quiz déjà lancé",
        )
    discard_training_sessions_using_questions([question_id], session)
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
    if question is None or question.image is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.IMAGE_NOT_FOUND,
            "Image de la question introuvable",
        )
    return Response(
        content=question.image.data,
        media_type=question.image.content_type,
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
    if choice is None or choice.image is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.IMAGE_NOT_FOUND,
            "Image de la réponse introuvable",
        )
    return Response(
        content=choice.image.data,
        media_type=choice.image.content_type,
    )
