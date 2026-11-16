"""Tie each quiz participation to the student account that took it.

A participation pointed only at the student's class membership, which goes
when the student leaves the class or the class is deleted: their exam
history then lost every exam taken there. The account outlives those, so
quiz_participants.student_account_id now records it too, and the history
reads it. Existing participations get the account of their membership; one
whose membership is already gone stays without.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_participants",
        sa.Column("student_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "quiz_participants_student_account_id_fkey",
        "quiz_participants",
        "student_accounts",
        ["student_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quiz_participants_student_account_id",
        "quiz_participants",
        ["student_account_id"],
    )
    op.execute(
        "UPDATE quiz_participants SET student_account_id = students.account_id "
        "FROM students WHERE students.id = quiz_participants.student_id"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quiz_participants_student_account_id", table_name="quiz_participants"
    )
    op.drop_column("quiz_participants", "student_account_id")
