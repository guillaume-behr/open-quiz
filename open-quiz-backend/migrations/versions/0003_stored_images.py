"""Move question and choice images into a table addressed by content.

Images were bytea columns of questions and question_choices, read along with
every row and stored again for each copy. They move, once per distinct
content, into stored_images, keyed by the SHA-256 of their bytes; questions
and choices keep only that key.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("questions", "question_choices")


def upgrade() -> None:
    op.create_table(
        "stored_images",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("sha256"),
    )
    for table in TABLES:
        op.add_column(
            table, sa.Column("image_sha256", sa.String(length=64), nullable=True)
        )
        # Identical bytes keep the content type first met; normalized images
        # always pair one content with one type.
        op.execute(
            f"INSERT INTO stored_images (sha256, content_type, data) "  # noqa: S608
            f"SELECT DISTINCT ON (digest) digest, image_content_type, image_data "
            f"FROM (SELECT encode(sha256(image_data), 'hex') AS digest, "
            f"image_content_type, image_data FROM {table} "
            f"WHERE image_data IS NOT NULL AND image_content_type IS NOT NULL) "
            f"AS images ORDER BY digest "
            f"ON CONFLICT (sha256) DO NOTHING"
        )
        op.execute(
            f"UPDATE {table} SET image_sha256 = encode(sha256(image_data), 'hex') "  # noqa: S608
            f"WHERE image_data IS NOT NULL AND image_content_type IS NOT NULL"
        )
        op.create_index(f"ix_{table}_image_sha256", table, ["image_sha256"])
        op.create_foreign_key(
            f"fk_{table}_image_sha256",
            table,
            "stored_images",
            ["image_sha256"],
            ["sha256"],
        )
        op.drop_column(table, "image_data")
        op.drop_column(table, "image_content_type")


def downgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("image_data", sa.LargeBinary(), nullable=True))
        op.add_column(
            table,
            sa.Column("image_content_type", sa.String(length=80), nullable=True),
        )
        op.execute(
            f"UPDATE {table} SET image_data = stored_images.data, "  # noqa: S608
            f"image_content_type = stored_images.content_type "
            f"FROM stored_images WHERE stored_images.sha256 = {table}.image_sha256"
        )
        op.drop_constraint(f"fk_{table}_image_sha256", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_image_sha256", table_name=table)
        op.drop_column(table, "image_sha256")
    op.drop_table("stored_images")
