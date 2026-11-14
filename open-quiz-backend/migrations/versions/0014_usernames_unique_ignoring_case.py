"""Make teacher and administrator usernames unique ignoring case.

Usernames were unique with their exact case only: "Alice" and "alice" could
be two accounts, and a sign-in had to match the case it was created with.
Sign-in now ignores case, so two such accounts would be one name. Of each
group of usernames differing only by case, the managed administrator, or
else the oldest account, keeps its name; the others are renamed with a
numbered suffix, as in "alice-2", which the administrator page shows.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_users_username"
USERNAME_LENGTH = 80


def rename_duplicates(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            "SELECT users.id, users.username, lower(users.username) FROM users "
            "LEFT JOIN security_state AS managed "
            "ON managed.key = 'managed_admin_user_id' "
            "AND managed.value = users.id::text "
            "ORDER BY managed.key IS NULL, users.id"
        )
    ).all()
    taken = {lowered for _, _, lowered in rows}
    seen: set[str] = set()
    for user_id, username, lowered in rows:
        if lowered not in seen:
            seen.add(lowered)
            continue
        number = 2
        while True:
            suffix = f"-{number}"
            kept = USERNAME_LENGTH - len(suffix)
            candidate = username[:kept] + suffix
            if lowered[:kept] + suffix not in taken:
                break
            number += 1
        taken.add(lowered[:kept] + suffix)
        seen.add(lowered[:kept] + suffix)
        connection.execute(
            sa.text("UPDATE users SET username = :username WHERE id = :id"),
            {"username": candidate, "id": user_id},
        )


def upgrade() -> None:
    rename_duplicates(op.get_bind())
    # The case-insensitive index serves every lookup the plain one did.
    op.drop_index("ix_users_username", table_name="users", if_exists=True)
    op.create_index(
        INDEX,
        "users",
        [sa.text("lower(username)")],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="users")
    op.create_index("ix_users_username", "users", ["username"], unique=True)
