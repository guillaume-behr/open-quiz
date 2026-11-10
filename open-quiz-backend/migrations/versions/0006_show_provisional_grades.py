"""Let a quiz choose whether students see a provisional correction.

quizzes.show_provisional_grades decides whether a student sees the
correction and their score in their history before the teacher publishes
the grades. Existing quizzes keep doing so (true). Sessions copy the value
at launch; sessions launched before this migration keep NULL and follow
their quiz.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quizzes",
        sa.Column(
            "show_provisional_grades",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        # A database created before migrations, from the current models,
        # already has the column (tests/test_migrations.py).
        if_not_exists=True,
    )
    op.add_column(
        "quiz_sessions",
        sa.Column("show_provisional_grades", sa.Boolean(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("quiz_sessions", "show_provisional_grades")
    op.drop_column("quizzes", "show_provisional_grades")
