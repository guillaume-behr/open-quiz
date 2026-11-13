"""Remember which questions a student skipped.

Skipping a question stores an empty answer. quiz_answers.was_skipped keeps the
skip on record once the student comes back and answers it, so the question
navigation can keep it marked. Existing answers were never skipped.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-13 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_answers",
        sa.Column("was_skipped", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("quiz_answers", "was_skipped")
