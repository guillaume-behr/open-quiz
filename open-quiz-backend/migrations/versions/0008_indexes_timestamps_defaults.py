"""Index foreign keys and running sessions, widen Unix timestamps, align defaults.

- Running sessions get a partial index: the expiry loop looks for them every
  few seconds among finished sessions kept for a year. Retention selects
  sessions by creation date every hour: indexed too.
- A foreign key that is only the second column of a composite primary key
  gets an index of its own, used when it is filtered on and when its parent
  row is deleted.
- Unix timestamps move to 64 bits, past 2038.
- quiz_session_student_questions.student_id becomes a foreign key: rows left
  pointing at a deleted student are cleared first. Its positions are unique
  per student identifier, since rows without an account have no student_id.
- Databases adopted from 0.4.0 or earlier got server defaults that fresh
  ones lack: dropped, as in the models.

Every step is idempotent: a database created before migrations, from the
current models, already has some of them (tests/test_migrations.py).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_SESSIONS = "status IN ('waiting', 'in_progress', 'paused')"

FOREIGN_KEY_INDEXES = (
    ("quiz_session_questions", "question_id"),
    ("quiz_session_student_questions", "question_id"),
    ("class_training_question_banks", "question_bank_id"),
    ("quiz_question_banks", "question_bank_id"),
    ("makeup_session_quizzes", "quiz_id"),
    ("makeup_session_selections", "student_id"),
)

UNIX_TIMESTAMPS = (
    ("refresh_sessions", "expires_at", False),
    ("refresh_sessions", "revoked_at", True),
    ("authentication_challenges", "expires_at", False),
    ("authentication_challenges", "used_at", True),
    ("login_rate_limits", "window_started_at", False),
)

LEGACY_DEFAULTS = (
    ("users", "access_token_generation"),
    ("student_accounts", "access_token_generation"),
    ("quizzes", "allow_answer_review"),
)

STUDENT_QUESTIONS = "quiz_session_student_questions"
STUDENT_FOREIGN_KEY = "quiz_session_student_questions_student_id_fkey"
POSITION_CONSTRAINT = "uq_quiz_session_student_question_position"


def upgrade() -> None:
    op.create_index(
        "ix_quiz_sessions_active",
        "quiz_sessions",
        ["id"],
        postgresql_where=sa.text(ACTIVE_SESSIONS),
        if_not_exists=True,
    )
    op.create_index(
        "ix_quiz_sessions_created_at",
        "quiz_sessions",
        ["created_at"],
        if_not_exists=True,
    )
    for table, column in FOREIGN_KEY_INDEXES:
        op.create_index(f"ix_{table}_{column}", table, [column], if_not_exists=True)

    for table, column, nullable in UNIX_TIMESTAMPS:
        op.alter_column(
            table,
            column,
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=nullable,
        )

    op.execute(
        f"UPDATE {STUDENT_QUESTIONS} SET student_id = NULL "  # noqa: S608 - constants
        "WHERE student_id IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM students WHERE students.id = {STUDENT_QUESTIONS}.student_id)"
    )
    op.execute(
        f"ALTER TABLE {STUDENT_QUESTIONS} DROP CONSTRAINT IF EXISTS {STUDENT_FOREIGN_KEY}"
    )
    op.create_foreign_key(
        STUDENT_FOREIGN_KEY,
        STUDENT_QUESTIONS,
        "students",
        ["student_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        f"ALTER TABLE {STUDENT_QUESTIONS} DROP CONSTRAINT IF EXISTS {POSITION_CONSTRAINT}"
    )
    op.create_unique_constraint(
        POSITION_CONSTRAINT,
        STUDENT_QUESTIONS,
        ["session_id", "student_identifier", "position"],
    )

    for table, column in LEGACY_DEFAULTS:
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    op.drop_constraint(POSITION_CONSTRAINT, STUDENT_QUESTIONS, type_="unique")
    op.create_unique_constraint(
        POSITION_CONSTRAINT,
        STUDENT_QUESTIONS,
        ["session_id", "student_id", "position"],
    )
    op.drop_constraint(STUDENT_FOREIGN_KEY, STUDENT_QUESTIONS, type_="foreignkey")
    for table, column, nullable in UNIX_TIMESTAMPS:
        op.alter_column(
            table,
            column,
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=nullable,
        )
    for table, column in FOREIGN_KEY_INDEXES:
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_index("ix_quiz_sessions_created_at", table_name="quiz_sessions")
    op.drop_index("ix_quiz_sessions_active", table_name="quiz_sessions")
