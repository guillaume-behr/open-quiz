from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.models import Question, QuestionChoice, QuestionCode
from app.schemas import QuestionResponse


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
        response_language=question.response_language,
        allow_code_execution=question.allow_code_execution,
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


def load_question_responses(
    question_ids: list[int], session: Session
) -> list[QuestionResponse]:
    if not question_ids:
        return []
    questions_by_id = {
        question.id: question
        for question in session.scalars(
            select(Question)
            .options(defer(Question.image_data))
            .where(Question.id.in_(question_ids))
        )
    }
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
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
            select(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
        )
    }
    return [
        question_response(
            questions_by_id[question_id],
            choices_by_question[question_id],
            codes_by_question.get(question_id),
        )
        for question_id in question_ids
    ]
