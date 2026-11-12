"""Remove what nothing writes any more: legacy rows, a status and dead columns.

- Cancelled sessions and make-up sessions: cancelling now deletes them, and
  the application no longer handles the status. Remaining ones go, with their
  join codes, and the status leaves the check constraints.
- Paste and copy alerts are no longer reported; one still stored was hidden
  on display. It is now cleared as it was displayed.
- Memberships without a student account predate accounts and were hidden
  from every listing: they are deleted, and every membership now has one.
  Their participations keep their results without the student.
- Unused columns: quizzes.easy_points, medium_points and hard_points,
  questions.correction_mode and refresh_session_families.parent_session_id.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-12 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_CONSTRAINTS = (
    ("ck_quiz_sessions_status", "quiz_sessions"),
    ("ck_makeup_sessions_status", "makeup_sessions"),
)
STATUSES = ("waiting", "in_progress", "paused", "finished")
DIFFICULTY_POINTS = ("easy_points", "medium_points", "hard_points")

CANCELLED_MAKEUPS = "SELECT id FROM makeup_sessions WHERE status = 'cancelled'"
CANCELLED_SESSIONS = (
    "SELECT join_code FROM quiz_sessions WHERE status = 'cancelled' "
    "OR makeup_session_id IN "
    "(SELECT id FROM makeup_sessions WHERE status = 'cancelled')"
)


def status_check(statuses: Sequence[str]) -> str:
    return "status IN ({})".format(", ".join(f"'{value}'" for value in statuses))


def upgrade() -> None:
    op.execute(
        f"DELETE FROM quiz_join_codes WHERE code IN ({CANCELLED_SESSIONS}) "  # noqa: S608 - constants
        "OR code IN (SELECT join_code FROM makeup_sessions "
        "WHERE status = 'cancelled')"
    )
    # Participants, answers and drawn questions cascade (0010).
    op.execute(
        "DELETE FROM quiz_sessions WHERE status = 'cancelled' "  # noqa: S608 - constants
        f"OR makeup_session_id IN ({CANCELLED_MAKEUPS})"
    )
    op.execute("DELETE FROM makeup_sessions WHERE status = 'cancelled'")
    for name, table in STATUS_CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, status_check(STATUSES))

    op.execute(
        "UPDATE quiz_participants SET violation_count = 0, "
        "last_violation_type = NULL, last_violation_at = NULL "
        "WHERE last_violation_type IN ('paste_attempt', 'copy_attempt')"
    )

    # Participations and make-up selections follow their foreign keys (0010).
    op.execute("DELETE FROM students WHERE account_id IS NULL")
    op.alter_column(
        "students", "account_id", existing_type=sa.Integer(), nullable=False
    )

    for column in DIFFICULTY_POINTS:
        op.drop_column("quizzes", column)
    op.drop_column("questions", "correction_mode")
    op.drop_column("refresh_session_families", "parent_session_id")


def downgrade() -> None:
    op.add_column(
        "refresh_session_families",
        sa.Column("parent_session_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column(
            "correction_mode",
            sa.String(20),
            nullable=False,
            server_default="automatic",
        ),
    )
    op.create_check_constraint(
        "ck_questions_correction_mode", "questions", "correction_mode IN ('automatic')"
    )
    for column in DIFFICULTY_POINTS:
        op.add_column(
            "quizzes",
            sa.Column(column, sa.Float(), nullable=False, server_default="0"),
        )
    op.alter_column("students", "account_id", existing_type=sa.Integer(), nullable=True)
    for name, table in STATUS_CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, status_check((*STATUSES, "cancelled")))
