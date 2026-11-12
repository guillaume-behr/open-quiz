"""Session questions: the copies a session draws from the banks.

A launch, a training or a make-up draws bank questions, then copies each one
into the session (Question.quiz_session_id) with its choices and its code.
Everything the session records afterwards (assignments, answers, the choice
ids inside answers) points at these copies, so a teacher can edit or delete
the bank questions at any time without changing what a session showed,
accepted or graded. A copy is deleted with its session, by the database
(ON DELETE CASCADE), and its choices and code with it.

Copies share their images with the bank: images are stored once per content
(app/stored_images.py) and kept while any question or choice references them.
"""

from collections.abc import Iterable

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode
from app.models import Question, QuestionChoice, QuestionCode


def copy_questions_into_session(
    session_id: int,
    question_ids: Iterable[int],
    session: Session,
) -> dict[int, int]:
    """Copy bank questions into a session and map each bank id to its copy.

    A question drawn several times in a session (one draw per student) is
    copied once. The queries do not grow with the number of questions. A
    question deleted from its bank after the draw refuses the copy: the
    caller's transaction is rolled back and nothing is launched.
    """
    source_ids = sorted(set(question_ids))
    if not source_ids:
        return {}
    sources = list(
        session.scalars(
            select(Question).where(
                Question.id.in_(source_ids),
                Question.question_bank_id.is_not(None),
            )
        )
    )
    copies = {
        source.id: Question(
            quiz_session_id=session_id,
            source_question_id=source.id,
            prompt=source.prompt,
            difficulty=source.difficulty,
            answer_mode=source.answer_mode,
            answer_mode_disclosed=source.answer_mode_disclosed,
            response_language=source.response_language,
            allow_code_execution=source.allow_code_execution,
            correction_mode=source.correction_mode,
            image_sha256=source.image_sha256,
            created_at=source.created_at,
        )
        for source in sources
    }
    if len(copies) != len(source_ids):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_QUESTIONS_INSUFFICIENT,
            "Les banques de questions ont changé pendant le tirage, réessayez",
        )
    session.add_all(copies.values())
    session.flush()
    session.add_all(
        QuestionChoice(
            question_id=copies[choice.question_id].id,
            label=choice.label,
            is_correct=choice.is_correct,
            points=choice.points,
            image_sha256=choice.image_sha256,
            code_language=choice.code_language,
            code_content=choice.code_content,
            position=choice.position,
        )
        for choice in session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id.in_(copies))
            .order_by(QuestionChoice.question_id, QuestionChoice.position)
        )
    )
    session.add_all(
        QuestionCode(
            question_id=copies[code.question_id].id,
            language=code.language,
            content=code.content,
        )
        for code in session.scalars(
            select(QuestionCode).where(QuestionCode.question_id.in_(copies))
        )
    )
    session.flush()
    return {source_id: copy.id for source_id, copy in copies.items()}


def source_question_ids(
    question_ids: Iterable[int], session: Session
) -> dict[int, int]:
    """Map session copies to the bank questions they were drawn from.

    Copies whose bank question was deleted since are left out: they can no
    longer be drawn anyway.
    """
    wanted = set(question_ids)
    if not wanted:
        return {}
    return {
        copy_id: source_id
        for copy_id, source_id in session.execute(
            select(Question.id, Question.source_question_id).where(
                Question.id.in_(wanted),
                Question.source_question_id.is_not(None),
            )
        )
        if source_id is not None
    }
