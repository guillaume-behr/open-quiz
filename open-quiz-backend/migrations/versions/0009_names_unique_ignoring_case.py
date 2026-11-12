"""Make grade level, class and question bank names unique ignoring case.

Names were unique per teacher only with their exact case, while some lookups
ignored it: "Tle" and "tle" could both exist and split classes and banks
between them. Existing names that differ only by case are resolved first:

- grade levels merge into the oldest one, whose name the classes and banks
  of the others take;
- a class, or a bank of the same level, whose name clashes with an older one
  is renamed with a numbered suffix, as in "tg1 (2)". Nothing is deleted.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Index name, table, the columns the name is unique within, the name column.
UNIQUE_NAMES = (
    ("uq_grade_level_owner_name", "grade_levels", ("owner_id",), "name"),
    ("uq_student_class_owner_name", "student_classes", ("owner_id",), "name"),
    (
        "uq_question_bank_owner_classification",
        "question_banks",
        ("owner_id", "grade_level"),
        "chapter",
    ),
)

# The oldest of each teacher's levels sharing a name ignoring case.
CANONICAL_LEVELS = (
    "SELECT DISTINCT ON (owner_id, lower(name)) owner_id, name FROM grade_levels "
    "ORDER BY owner_id, lower(name), id"
)


def merge_grade_levels(connection: sa.Connection) -> None:
    for table in ("student_classes", "question_banks"):
        connection.execute(
            sa.text(
                f"UPDATE {table} AS item SET grade_level = level.name "  # noqa: S608 - constants
                f"FROM ({CANONICAL_LEVELS}) AS level "
                "WHERE item.owner_id = level.owner_id "
                "AND lower(item.grade_level) = lower(level.name) "
                "AND item.grade_level <> level.name"
            )
        )
    connection.execute(
        sa.text(
            "DELETE FROM grade_levels AS duplicate USING grade_levels AS kept "
            "WHERE kept.owner_id = duplicate.owner_id "
            "AND lower(kept.name) = lower(duplicate.name) AND kept.id < duplicate.id"
        )
    )


def rename_duplicates(
    connection: sa.Connection, table: str, scope: Sequence[str], column: str
) -> None:
    """Suffix every name that an older row of the same scope already uses."""
    length = connection.execute(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    ).scalar_one()
    # owner_id, then the other scope columns ignoring case, as the index will.
    scope_sql = ", ".join([scope[0], *(f"lower({name})" for name in scope[1:])])
    rows = connection.execute(
        sa.text(
            f"SELECT id, {scope_sql}, {column}, lower({column}) "  # noqa: S608 - constants
            f"FROM {table} ORDER BY id"
        )
    ).all()
    taken = {(tuple(row[1:-2]), row[-1]) for row in rows}
    seen: set[tuple[tuple[object, ...], str]] = set()
    for row in rows:
        row_scope, name, lowered = tuple(row[1:-2]), row[-2], row[-1]
        if (row_scope, lowered) not in seen:
            seen.add((row_scope, lowered))
            continue
        number = 2
        while True:
            suffix = f" ({number})"
            kept = length - len(suffix)
            candidate, candidate_lowered = name[:kept] + suffix, lowered[:kept] + suffix
            if (row_scope, candidate_lowered) not in taken:
                break
            number += 1
        taken.add((row_scope, candidate_lowered))
        seen.add((row_scope, candidate_lowered))
        connection.execute(
            sa.text(f"UPDATE {table} SET {column} = :name WHERE id = :id"),  # noqa: S608 - constants
            {"name": candidate, "id": row[0]},
        )


def upgrade() -> None:
    connection = op.get_bind()
    merge_grade_levels(connection)
    for _, table, scope, column in UNIQUE_NAMES[1:]:
        rename_duplicates(connection, table, scope, column)
    for name, table, scope, column in UNIQUE_NAMES:
        # A database created before migrations, from the current models,
        # already has the index (tests/test_migrations.py).
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.create_index(
            name,
            table,
            [
                scope[0],
                *(sa.text(f"lower({column})") for column in (*scope[1:], column)),
            ],
            unique=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    for name, table, scope, column in UNIQUE_NAMES:
        op.drop_index(name, table_name=table)
        op.create_unique_constraint(name, table, [*scope, column])
