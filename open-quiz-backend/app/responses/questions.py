from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Question, QuestionChoice, QuestionCode
from app.records.questions import load_question_records
from app.schemas.questions import QuestionResponse


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
        has_image=question.image_sha256 is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=[
            {
                "id": choice.id,
                "label": choice.label,
                "is_correct": choice.is_correct,
                "points": choice.points,
                "position": choice.position,
                "has_image": choice.image_sha256 is not None,
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
    questions_by_id, choices_by_question = load_question_records(question_ids, session)
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
