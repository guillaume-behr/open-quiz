"""Let PostgreSQL cascade deletes along foreign keys.

Every delete path removed children by hand, table by table, in an order each
new table had to be added to. The foreign keys now say what happens:

- CASCADE for rows meaningless without their parent: a user's data, a
  class's memberships, a bank's questions and their choices and code, a
  session's participants, answers and drawn questions, link tables;
- SET NULL where history outlives the parent: a participant whose student
  was removed, a session or make-up session whose class was deleted.

The references from history to questions and from training sessions to their
bank keep refusing a delete: the application checks those first.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table, column and what deleting the referenced row does to it.
ON_DELETE = (
    ("grade_levels", "owner_id", "CASCADE"),
    ("student_classes", "owner_id", "CASCADE"),
    ("student_accounts", "owner_id", "CASCADE"),
    ("students", "class_id", "CASCADE"),
    ("students", "account_id", "CASCADE"),
    ("question_banks", "owner_id", "CASCADE"),
    ("class_training_question_banks", "class_id", "CASCADE"),
    ("class_training_question_banks", "question_bank_id", "CASCADE"),
    ("questions", "question_bank_id", "CASCADE"),
    ("question_codes", "question_id", "CASCADE"),
    ("question_choices", "question_id", "CASCADE"),
    ("quizzes", "owner_id", "CASCADE"),
    ("quiz_question_banks", "quiz_id", "CASCADE"),
    ("quiz_question_banks", "question_bank_id", "CASCADE"),
    ("training_quiz_profiles", "owner_id", "CASCADE"),
    ("training_quiz_profiles", "quiz_id", "CASCADE"),
    ("quiz_sessions", "quiz_id", "CASCADE"),
    ("quiz_sessions", "class_id", "SET NULL"),
    ("quiz_sessions", "makeup_session_id", "CASCADE"),
    ("makeup_sessions", "owner_id", "CASCADE"),
    ("makeup_sessions", "class_id", "SET NULL"),
    ("makeup_session_quizzes", "session_id", "CASCADE"),
    ("makeup_session_quizzes", "quiz_id", "CASCADE"),
    ("makeup_session_selections", "session_id", "CASCADE"),
    ("makeup_session_selections", "student_id", "CASCADE"),
    ("quiz_session_questions", "session_id", "CASCADE"),
    ("quiz_session_student_questions", "session_id", "CASCADE"),
    ("quiz_participants", "session_id", "CASCADE"),
    ("quiz_participants", "student_id", "SET NULL"),
    ("quiz_answers", "session_id", "CASCADE"),
    ("quiz_answers", "participant_id", "CASCADE"),
    ("refresh_sessions", "user_id", "CASCADE"),
    ("refresh_session_families", "session_id", "CASCADE"),
    ("two_factor_credentials", "user_id", "CASCADE"),
    ("authentication_challenges", "user_id", "CASCADE"),
)


def recreate_foreign_keys(cascade: bool) -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column, action in ON_DELETE:
        (key,) = (
            key
            for key in inspector.get_foreign_keys(table)
            if key["constrained_columns"] == [column]
        )
        # PostgreSQL names every constraint; the fallback is its default name.
        name = key["name"] or f"{table}_{column}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            key["referred_table"],
            [column],
            key["referred_columns"],
            ondelete=action if cascade else None,
        )


def upgrade() -> None:
    recreate_foreign_keys(cascade=True)


def downgrade() -> None:
    recreate_foreign_keys(cascade=False)
