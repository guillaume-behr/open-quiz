"""Clear monitoring alerts recorded for a copy.

A copy is no longer reported as an exam monitoring alert. Participants that
earlier releases flagged for one last get their alert count and last alert
cleared, as 0002 did for a paste.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE quiz_participants SET violation_count = 0, "
        "last_violation_type = NULL, last_violation_at = NULL "
        "WHERE last_violation_type = 'copy_attempt'"
    )


def downgrade() -> None:
    # The cleared alerts are not recorded anywhere, so there is nothing to
    # restore.
    pass
