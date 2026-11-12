"""Sessions own copies of the questions they drew.

A drawn question becomes a copy that belongs to its session
(questions.quiz_session_id), with its choices and its code, so bank questions
can be edited or deleted freely. Copies are deleted with their session, and
choices and code with their question, by ON DELETE CASCADE.

Existing sessions get their copies here: one per question each session drew
or holds an answer to, from the bank question as it is now. Assignments,
answers and the choice ids recorded inside answers move to the copies.

Every step is idempotent: a database created before migrations, from the
current models, already has the columns (tests/test_migrations.py).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 18:00:00.000000
"""

import json
from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BANK_OR_SESSION = "ck_questions_bank_or_session"
CASCADING_CHILDREN = ("question_choices", "question_codes")
QUESTION_REFERENCES = (
    "quiz_session_questions",
    "quiz_session_student_questions",
    "quiz_answers",
)
COPIED_COLUMNS = (
    "prompt, difficulty, answer_mode, answer_mode_disclosed, response_language, "
    "allow_code_execution, correction_mode, image_sha256, created_at"
)
CHOICE_COLUMNS = (
    "label, is_correct, points, image_sha256, code_language, code_content, position"
)


def upgrade() -> None:
    op.alter_column(
        "questions", "question_bank_id", existing_type=sa.Integer(), nullable=True
    )
    op.execute(
        "ALTER TABLE questions "
        "ADD COLUMN IF NOT EXISTS quiz_session_id integer, "
        "ADD COLUMN IF NOT EXISTS source_question_id integer"
    )
    for column, parent, on_delete in (
        ("quiz_session_id", "quiz_sessions", "CASCADE"),
        ("source_question_id", "questions", "SET NULL"),
    ):
        name = f"questions_{column}_fkey"
        op.execute(f"ALTER TABLE questions DROP CONSTRAINT IF EXISTS {name}")
        op.create_foreign_key(
            name, "questions", parent, [column], ["id"], ondelete=on_delete
        )
        op.create_index(
            f"ix_questions_{column}", "questions", [column], if_not_exists=True
        )
    for table in CASCADING_CHILDREN:
        name = f"{table}_question_id_fkey"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.create_foreign_key(
            name, table, "questions", ["question_id"], ["id"], ondelete="CASCADE"
        )

    copy_drawn_questions()

    op.execute(f"ALTER TABLE questions DROP CONSTRAINT IF EXISTS {BANK_OR_SESSION}")
    op.create_check_constraint(
        BANK_OR_SESSION,
        "questions",
        "(question_bank_id IS NULL) <> (quiz_session_id IS NULL)",
    )


def copy_drawn_questions() -> None:
    connection = op.get_bind()
    copied_before = connection.execute(
        sa.text("SELECT coalesce(max(id), 0) FROM questions")
    ).scalar_one()
    drawn = " UNION ".join(
        f"SELECT session_id, question_id FROM {table}"  # noqa: S608 - constants
        for table in QUESTION_REFERENCES
    )
    op.execute(
        f"INSERT INTO questions (quiz_session_id, source_question_id, {COPIED_COLUMNS}) "  # noqa: S608
        f"SELECT drawn.session_id, source.id, {prefixed('source', COPIED_COLUMNS)} "
        f"FROM ({drawn}) AS drawn "
        "JOIN questions AS source ON source.id = drawn.question_id "
        "WHERE source.question_bank_id IS NOT NULL "
        "ORDER BY drawn.session_id, source.id"
    )
    new_copies = f"copy.quiz_session_id IS NOT NULL AND copy.id > {copied_before:d}"
    op.execute(
        f"INSERT INTO question_choices (question_id, {CHOICE_COLUMNS}) "  # noqa: S608
        f"SELECT copy.id, {prefixed('choice', CHOICE_COLUMNS)} "
        "FROM questions AS copy "
        "JOIN question_choices AS choice "
        "ON choice.question_id = copy.source_question_id "
        f"WHERE {new_copies} "
        "ORDER BY copy.id, choice.position"
    )
    op.execute(
        "INSERT INTO question_codes (question_id, language, content) "  # noqa: S608
        "SELECT copy.id, code.language, code.content "
        "FROM questions AS copy "
        "JOIN question_codes AS code ON code.question_id = copy.source_question_id "
        f"WHERE {new_copies}"
    )
    # Answers still reference bank questions here: a choice of a copy sits at
    # the position of the bank choice it was made from.
    choice_copies = {
        (session_id, bank_choice_id): copy_choice_id
        for session_id, bank_choice_id, copy_choice_id in connection.execute(
            sa.text(
                "SELECT copy.quiz_session_id, bank_choice.id, copy_choice.id "  # noqa: S608
                f"{CHOICE_PAIRS} WHERE {new_copies}"
            )
        )
    }
    remap_selected_choices(
        connection,
        "JOIN questions AS question ON question.id = answer.question_id "
        "WHERE question.question_bank_id IS NOT NULL",
        lambda session_id, choice_id: choice_copies.get(
            (session_id, choice_id), choice_id
        ),
    )
    for table in QUESTION_REFERENCES:
        op.execute(
            f"UPDATE {table} SET question_id = copy.id "  # noqa: S608 - constants
            "FROM questions AS copy "
            f"WHERE copy.quiz_session_id = {table}.session_id "
            f"AND copy.source_question_id = {table}.question_id"
        )


# Each choice of a copy with the bank choice it was made from.
CHOICE_PAIRS = (
    "FROM questions AS copy "
    "JOIN question_choices AS copy_choice ON copy_choice.question_id = copy.id "
    "JOIN question_choices AS bank_choice "
    "ON bank_choice.question_id = copy.source_question_id "
    "AND bank_choice.position = copy_choice.position"
)


def remap_selected_choices(
    connection: sa.Connection,
    answer_filter: str,
    new_choice_id: Callable[[int, int], int],
) -> None:
    """Rewrite the choice ids recorded in answers, leaving anything else as is."""
    changes = []
    for answer_id, session_id, answer_data in connection.execute(
        sa.text(
            "SELECT answer.id, answer.session_id, answer.answer_data "  # noqa: S608
            f"FROM quiz_answers AS answer {answer_filter} "
            "AND answer.answer_data LIKE '%selected_choice_ids%'"
        )
    ):
        try:
            payload = json.loads(answer_data)
        except TypeError, ValueError:
            continue
        if not isinstance(payload, dict) or not isinstance(
            payload.get("selected_choice_ids"), list
        ):
            continue
        payload["selected_choice_ids"] = [
            new_choice_id(session_id, choice_id)
            if isinstance(choice_id, int) and not isinstance(choice_id, bool)
            else choice_id
            for choice_id in payload["selected_choice_ids"]
        ]
        changes.append(
            {"id": answer_id, "data": json.dumps(payload, ensure_ascii=False)}
        )
    if changes:
        connection.execute(
            sa.text("UPDATE quiz_answers SET answer_data = :data WHERE id = :id"),
            changes,
        )


def prefixed(alias: str, columns: str) -> str:
    return ", ".join(f"{alias}.{column.strip()}" for column in columns.split(","))


def downgrade() -> None:
    """Point sessions back at the bank questions their copies came from.

    A copy whose bank question was deleted since has nothing to point back
    to, so the downgrade refuses rather than lose its session's record.
    """
    connection = op.get_bind()
    orphaned = connection.execute(
        sa.text(
            "SELECT count(*) FROM questions "
            "WHERE quiz_session_id IS NOT NULL AND source_question_id IS NULL"
        )
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} session questions no longer have a bank question: "
            "delete their sessions before downgrading"
        )
    bank_choices: dict[int, int] = dict(
        connection.execute(
            sa.text(
                f"SELECT copy_choice.id, bank_choice.id {CHOICE_PAIRS} "  # noqa: S608
                "WHERE copy.quiz_session_id IS NOT NULL"
            )
        ).all()
    )
    remap_selected_choices(
        connection,
        "WHERE true",
        lambda _session_id, choice_id: bank_choices.get(choice_id, choice_id),
    )
    for table in QUESTION_REFERENCES:
        op.execute(
            f"UPDATE {table} SET question_id = copy.source_question_id "  # noqa: S608
            "FROM questions AS copy "
            f"WHERE copy.id = {table}.question_id "
            "AND copy.quiz_session_id IS NOT NULL"
        )
    op.execute("DELETE FROM questions WHERE quiz_session_id IS NOT NULL")
    op.drop_constraint(BANK_OR_SESSION, "questions", type_="check")
    for table in CASCADING_CHILDREN:
        name = f"{table}_question_id_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "questions", ["question_id"], ["id"])
    for column in ("source_question_id", "quiz_session_id"):
        op.drop_index(f"ix_questions_{column}", table_name="questions")
        op.drop_constraint(f"questions_{column}_fkey", "questions", type_="foreignkey")
        op.drop_column("questions", column)
    op.alter_column(
        "questions", "question_bank_id", existing_type=sa.Integer(), nullable=False
    )
