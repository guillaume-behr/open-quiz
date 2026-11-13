"""Let a question outlive its bank while past sessions still need it.

Deleting a question, or its bank, now detaches the questions that exam
sessions drew or answered: their bank becomes NULL (app/records/question_history.py).
Nothing is detached by the upgrade itself.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "questions", "question_bank_id", existing_type=sa.Integer(), nullable=True
    )


def downgrade() -> None:
    # Fails while detached questions remain: they have no bank to return to.
    op.alter_column(
        "questions", "question_bank_id", existing_type=sa.Integer(), nullable=False
    )
