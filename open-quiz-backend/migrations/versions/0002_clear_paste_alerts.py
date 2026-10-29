"""Clear monitoring alerts recorded for a paste.

A paste is no longer reported as an exam monitoring alert. Participants that
earlier releases flagged for one alone get their alert count and last alert
cleared. Until migrations existed, this ran again at every startup.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29 17:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE quiz_participants SET violation_count = 0, "
        "last_violation_type = NULL, last_violation_at = NULL "
        "WHERE last_violation_type = 'paste_attempt'"
    )


def downgrade() -> None:
    # The cleared alerts are not recorded anywhere, so there is nothing to
    # restore.
    pass
