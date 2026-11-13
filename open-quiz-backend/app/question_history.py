"""Questions past sessions still need, kept out of the teacher's banks.

Sessions point at question rows: what an exam asked, how each answer scored
and what its correction shows are read from the current question. A bank
stays fully editable without rewriting those exams:

- deleting a question that an exam session drew or answered detaches it
  instead: its bank becomes NULL, so no bank, draw, export or teacher route
  sees it any more, while the sessions keep reading it;
- editing a question first freezes a detached copy for the sessions whose
  grades are published, so their content and marks never change, while
  unpublished sessions follow the edit and are regraded;
- a detached question goes once no session refers to it any more.

Changing a question under an exam that is still open stays refused: students
would be shown, and graded against, a question that changed mid-way.
"""

import json
from collections.abc import Collection

from sqlalchemy import (
    CompoundSelect,
    Select,
    delete,
    exists,
    inspect,
    select,
    union,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import affected_rows
from app.enums import QuizMode, SessionStatus
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
)
from app.question_records import discard_training_sessions_using_questions
from app.session_status import ACTIVE_SESSION_STATUSES

# The rows that tie a session to a question.
SESSION_QUESTION_REFERENCES = (
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    QuizAnswer,
)


def sessions_using_questions(question_ids: Collection[int]) -> CompoundSelect[int]:
    """Every session that drew one of the questions or holds an answer to it."""
    return union(
        *(
            select(table.session_id).where(table.question_id.in_(question_ids))
            for table in SESSION_QUESTION_REFERENCES
        )
    )


def questions_sessions_use(question_ids: Collection[int]) -> CompoundSelect[int]:
    """Those of the questions that a session drew or holds an answer to."""
    return union(
        *(
            select(table.question_id).where(table.question_id.in_(question_ids))
            for table in SESSION_QUESTION_REFERENCES
        )
    )


def active_exam_uses_questions(question_ids: Collection[int], session: Session) -> bool:
    """Whether an exam or make-up session that drew them is still open.

    Training attempts are disposable and never count.
    """
    if not question_ids:
        return False
    return (
        session.scalar(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.id.in_(sessions_using_questions(question_ids)),
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
                Quiz.mode == QuizMode.EXAM,
            )
            .limit(1)
        )
        is not None
    )


def open_makeup_draws_from_bank(question_bank_id: int, session: Session) -> bool:
    """Whether an open make-up session may still draw from the bank.

    A make-up draws each student's questions when the student picks a quiz,
    so its quizzes must keep their banks until it ends.
    """
    return (
        session.scalar(
            select(MakeupSession.id)
            .join(
                MakeupSessionQuiz,
                MakeupSessionQuiz.session_id == MakeupSession.id,
            )
            .join(
                QuizQuestionBank,
                QuizQuestionBank.quiz_id == MakeupSessionQuiz.quiz_id,
            )
            .where(
                QuizQuestionBank.question_bank_id == question_bank_id,
                MakeupSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
            .limit(1)
        )
        is not None
    )


def remove_questions(question_ids: list[int], session: Session) -> None:
    """Take questions out of their bank, keeping those a session still needs.

    Training attempts that drew them are discarded, as before. A question an
    exam session still refers to is detached; any other is deleted with its
    choices and code. The rows are locked first: a launch drawing one of them
    at the same moment either commits first, and the question is detached,
    or waits for this removal.
    """
    if not question_ids:
        return
    session.execute(
        select(Question.id).where(Question.id.in_(question_ids)).with_for_update()
    )
    discard_training_sessions_using_questions(question_ids, session)
    session.execute(
        update(Question)
        .where(Question.id.in_(questions_sessions_use(question_ids)))
        .values(question_bank_id=None)
    )
    # Choices and code cascade.
    session.execute(
        delete(Question).where(
            Question.id.in_(question_ids), Question.question_bank_id.is_not(None)
        )
    )


def copied_row[Row: (Question, QuestionChoice, QuestionCode)](
    row: Row, **overrides: object
) -> Row:
    """A new row of the same table with the same values but the overrides."""
    values = {
        column.key: getattr(row, column.key)
        for column in inspect(type(row)).column_attrs
        if column.key != "id"
    }
    return type(row)(**{**values, **overrides})


def remapped_answer_data(answer_data: str, choice_ids: dict[int, int]) -> str:
    """The stored answer with its selected choices renamed to the copies.

    A written answer, or a payload this application never wrote, is kept as
    it is.
    """
    try:
        payload = json.loads(answer_data)
    except TypeError, ValueError:
        return answer_data
    if not isinstance(payload, dict) or not isinstance(
        payload.get("selected_choice_ids"), list
    ):
        return answer_data
    payload["selected_choice_ids"] = [
        choice_ids.get(choice_id, choice_id)
        if isinstance(choice_id, int) and not isinstance(choice_id, bool)
        else choice_id
        for choice_id in payload["selected_choice_ids"]
    ]
    return json.dumps(payload, ensure_ascii=False)


def published_sessions_using(question_id: int, session: Session) -> list[int]:
    """Finished sessions using the question whose grades are published.

    Every finished session using it is locked until the edit commits, so
    grades published meanwhile wait for the edit: a session is either frozen
    here, or regraded by the edit and published afterwards.
    """
    rows = session.execute(
        select(QuizSession.id, QuizSession.grades_published_at)
        .where(
            QuizSession.id.in_(sessions_using_questions([question_id])),
            QuizSession.status == SessionStatus.FINISHED,
        )
        .order_by(QuizSession.id)
        .with_for_update()
    ).all()
    return [session_id for session_id, published_at in rows if published_at]


def freeze_for_published_sessions(question: Question, session: Session) -> list[int]:
    """Give published sessions a detached copy of the question as it stands.

    Returns those sessions. Their drawn questions and answers move to the
    copy, choice identifiers included, so the edit that follows changes
    neither what they show nor how they were graded.
    """
    session_ids = published_sessions_using(question.id, session)
    if not session_ids:
        return []
    frozen = copied_row(question, question_bank_id=None)
    session.add(frozen)
    session.flush()
    choice_ids: dict[int, int] = {}
    for choice in session.scalars(
        select(QuestionChoice).where(QuestionChoice.question_id == question.id)
    ):
        copy = copied_row(choice, question_id=frozen.id)
        session.add(copy)
        session.flush()
        choice_ids[choice.id] = copy.id
    code = session.get(QuestionCode, question.id)
    if code is not None:
        session.add(copied_row(code, question_id=frozen.id))
    for table in (QuizSessionQuestion, QuizSessionStudentQuestion):
        session.execute(
            update(table)
            .where(
                table.session_id.in_(session_ids),
                table.question_id == question.id,
            )
            .values(question_id=frozen.id)
            .execution_options(synchronize_session=False)
        )
    answers = [
        {
            "id": answer_id,
            "question_id": frozen.id,
            "answer_data": remapped_answer_data(answer_data, choice_ids),
        }
        for answer_id, answer_data in session.execute(
            select(QuizAnswer.id, QuizAnswer.answer_data).where(
                QuizAnswer.session_id.in_(session_ids),
                QuizAnswer.question_id == question.id,
            )
        )
    ]
    if answers:
        # ORM bulk UPDATE by primary key: a single executemany.
        session.execute(update(QuizAnswer), answers)
    session.flush()
    return session_ids


def unused_detached_questions() -> Select[int]:
    return select(Question.id).where(
        Question.question_bank_id.is_(None),
        *(
            ~exists().where(table.question_id == Question.id)
            for table in SESSION_QUESTION_REFERENCES
        ),
    )


def delete_unused_detached_questions(session: Session) -> int:
    """Delete the detached questions no session refers to any more.

    Sessions go with their retention, or when a teacher deletes them. A
    session launched while the question was being removed may still hold an
    uncommitted reference to it: the foreign key then rejects the deletion,
    which is rolled back to a savepoint, and the next run collects it.
    """
    try:
        with session.begin_nested():
            return affected_rows(
                session.execute(
                    delete(Question).where(Question.id.in_(unused_detached_questions()))
                )
            )
    except IntegrityError:
        return 0
