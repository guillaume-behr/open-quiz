"""Remember which questions a student skipped.

A skipped question has no answer while the session runs: the participant
keeps its id in quiz_participants.skipped_question_ids, and the end of the
session stores an empty answer for each one still unanswered. Existing
participants skipped nothing.

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
        "quiz_participants",
        sa.Column(
            "skipped_question_ids",
            sa.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("quiz_participants", "skipped_question_ids")
