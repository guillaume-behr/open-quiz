"""Remember the participant token a resumed exam replaced.

A student who lost their participant token joins again and gets a new one
(app/routers/quizzes/student_sessions.py, rejoin_quiz). The replaced token's hash is
kept so the tab still holding it can be told the exam was resumed elsewhere.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-10 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A database created before migrations, from the current models, already
    # has the column (tests/test_migrations.py).
    op.add_column(
        "quiz_participants",
        sa.Column("replaced_token_hash", sa.String(64), nullable=True),
        if_not_exists=True,
    )
    op.create_index(
        "ix_quiz_participants_replaced_token_hash",
        "quiz_participants",
        ["replaced_token_hash"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quiz_participants_replaced_token_hash", table_name="quiz_participants"
    )
    op.drop_column("quiz_participants", "replaced_token_hash")
