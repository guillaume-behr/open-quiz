"""Restrict statuses, modes and question settings to their known values.

The columns were free strings: a typo in the code wrote a value nothing ever
matched. The application now names them through app.enums, and these CHECK
constraints make PostgreSQL refuse anything else. The values are written out
here rather than imported, so this revision keeps meaning what it meant when
it was written.

A database holding an unknown value makes the upgrade fail as a whole; the
schema then stays at 0003 and the error names the constraint concerned.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 13:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SESSION_STATUSES = ("waiting", "in_progress", "paused", "finished", "cancelled")
CONSTRAINTS = (
    ("ck_questions_difficulty", "questions", "difficulty", ("easy", "medium", "hard")),
    (
        "ck_questions_answer_mode",
        "questions",
        "answer_mode",
        ("single", "multiple", "written"),
    ),
    (
        "ck_questions_correction_mode",
        "questions",
        "correction_mode",
        ("automatic",),
    ),
    ("ck_quizzes_mode", "quizzes", "mode", ("exam", "training")),
    ("ck_quiz_sessions_status", "quiz_sessions", "status", SESSION_STATUSES),
    ("ck_makeup_sessions_status", "makeup_sessions", "status", SESSION_STATUSES),
)


def upgrade() -> None:
    for name, table, column, values in CONSTRAINTS:
        allowed = ", ".join(f"'{value}'" for value in values)
        op.create_check_constraint(name, table, f"{column} IN ({allowed})")


def downgrade() -> None:
    for name, table, _column, _values in reversed(CONSTRAINTS):
        op.drop_constraint(name, table, type_="check")
