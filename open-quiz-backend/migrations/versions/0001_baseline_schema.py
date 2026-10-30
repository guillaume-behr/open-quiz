"""Baseline schema of Open Quiz 0.4.0.

Releases up to 0.4.0 had no migrations: every startup ran create_all() and
then added a few late columns by hand. This revision builds the schema of an
up-to-date 0.4.0 instance and skips whatever already exists, so the same
upgrade serves an empty database and one left by any of those releases. On
the latter it only adds the tables, columns and indexes an older release
never created, and keeps every row.

Revision ID: 0001
Revises:
Create Date: 2026-10-29 17:15:25.002002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("limiter_key", sa.String(length=96), nullable=False),
        sa.Column("window_started_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("limiter_key"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_login_rate_limits_window_started_at"),
        "login_rate_limits",
        ["window_started_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "problem_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_problem_reports_created_at"),
        "problem_reports",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quiz_join_codes",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("code"),
        if_not_exists=True,
    )
    op.create_table(
        "security_state",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        if_not_exists=True,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("access_token_generation", sa.Integer(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_users_username"),
        "users",
        ["username"],
        unique=True,
        if_not_exists=True,
    )
    op.create_table(
        "authentication_challenges",
        sa.Column("token_id_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("token_id_hash"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_authentication_challenges_expires_at"),
        "authentication_challenges",
        ["expires_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_authentication_challenges_user_id"),
        "authentication_challenges",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "grade_levels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_grade_level_owner_name"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_grade_levels_owner_id"),
        "grade_levels",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "question_banks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("grade_level", sa.String(length=80), nullable=False),
        sa.Column("chapter", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "grade_level",
            "chapter",
            name="uq_question_bank_owner_classification",
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_question_banks_owner_id"),
        "question_banks",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("source_language", sa.String(length=35), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("allow_previous_questions", sa.Boolean(), nullable=False),
        sa.Column("allow_answer_review", sa.Boolean(), nullable=False),
        sa.Column("allow_negative_points", sa.Boolean(), nullable=False),
        sa.Column("same_questions_for_all", sa.Boolean(), nullable=False),
        sa.Column("easy_question_count", sa.Integer(), nullable=False),
        sa.Column("medium_question_count", sa.Integer(), nullable=False),
        sa.Column("hard_question_count", sa.Integer(), nullable=False),
        sa.Column("easy_points", sa.Float(), nullable=False),
        sa.Column("medium_points", sa.Float(), nullable=False),
        sa.Column("hard_points", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quizzes_mode"), "quizzes", ["mode"], unique=False, if_not_exists=True
    )
    op.create_index(
        op.f("ix_quizzes_owner_id"),
        "quizzes",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_refresh_sessions_token_hash"),
        "refresh_sessions",
        ["token_hash"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"),
        "refresh_sessions",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "student_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("access_token_generation", sa.Integer(), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_student_accounts_identifier"),
        "student_accounts",
        ["identifier"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_student_accounts_owner_id"),
        "student_accounts",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "student_classes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("grade_level", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_student_class_owner_name"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_student_classes_owner_id"),
        "student_classes",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "two_factor_credentials",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("encrypted_secret", sa.String(length=255), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("last_counter", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id"),
        if_not_exists=True,
    )
    op.create_table(
        "class_training_question_banks",
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("question_bank_id", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["student_classes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["question_bank_id"],
            ["question_banks.id"],
        ),
        sa.PrimaryKeyConstraint("class_id", "question_bank_id"),
        if_not_exists=True,
    )
    op.create_table(
        "makeup_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.String(length=120), nullable=False),
        sa.Column("join_code", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["student_classes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_makeup_sessions_class_id"),
        "makeup_sessions",
        ["class_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_makeup_sessions_join_code"),
        "makeup_sessions",
        ["join_code"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_makeup_sessions_owner_id"),
        "makeup_sessions",
        ["owner_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_bank_id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("answer_mode", sa.String(length=20), nullable=False),
        sa.Column("answer_mode_disclosed", sa.Boolean(), nullable=False),
        sa.Column("response_language", sa.String(length=30), nullable=True),
        sa.Column(
            "allow_code_execution", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column("correction_mode", sa.String(length=20), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=True),
        sa.Column("image_content_type", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_bank_id"],
            ["question_banks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_questions_question_bank_id"),
        "questions",
        ["question_bank_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quiz_question_banks",
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("question_bank_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_bank_id"],
            ["question_banks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
        ),
        sa.PrimaryKeyConstraint("quiz_id", "question_bank_id"),
        if_not_exists=True,
    )
    op.create_table(
        "refresh_session_families",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["refresh_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("session_id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_refresh_session_families_family_id"),
        "refresh_session_families",
        ["family_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("identifier", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["student_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["student_classes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "class_id", "identifier", name="uq_student_class_identifier"
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_students_account_id"),
        "students",
        ["account_id"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_students_class_id"),
        "students",
        ["class_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "training_quiz_profiles",
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
        ),
        sa.PrimaryKeyConstraint("owner_id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_training_quiz_profiles_quiz_id"),
        "training_quiz_profiles",
        ["quiz_id"],
        unique=True,
        if_not_exists=True,
    )
    op.create_table(
        "makeup_session_quizzes",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["makeup_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("session_id", "quiz_id"),
        if_not_exists=True,
    )
    op.create_table(
        "makeup_session_selections",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["makeup_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
        ),
        sa.PrimaryKeyConstraint("session_id", "student_id"),
        if_not_exists=True,
    )
    op.create_table(
        "question_choices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=True),
        sa.Column("image_content_type", sa.String(length=80), nullable=True),
        sa.Column("code_language", sa.String(length=30), nullable=True),
        sa.Column("code_content", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id", "position", name="uq_question_choice_position"
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_question_choices_question_id"),
        "question_choices",
        ["question_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "question_codes",
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
        ),
        sa.PrimaryKeyConstraint("question_id"),
        if_not_exists=True,
    )
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("quiz_title", sa.String(length=160), nullable=True),
        sa.Column("source_language", sa.String(length=35), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("allow_previous_questions", sa.Boolean(), nullable=True),
        sa.Column("allow_answer_review", sa.Boolean(), nullable=True),
        sa.Column("allow_negative_points", sa.Boolean(), nullable=True),
        sa.Column("same_questions_for_all", sa.Boolean(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.String(length=120), nullable=False),
        sa.Column("join_code", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("grades_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("makeup_session_id", sa.Integer(), nullable=True),
        sa.Column("training_question_bank_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["student_classes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["makeup_session_id"],
            ["makeup_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["training_question_bank_id"],
            ["question_banks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_sessions_class_id"),
        "quiz_sessions",
        ["class_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_sessions_join_code"),
        "quiz_sessions",
        ["join_code"],
        unique=True,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_sessions_makeup_session_id"),
        "quiz_sessions",
        ["makeup_session_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_sessions_quiz_id"),
        "quiz_sessions",
        ["quiz_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_sessions_training_question_bank_id"),
        "quiz_sessions",
        ["training_question_bank_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quiz_participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("student_identifier", sa.String(length=80), nullable=False),
        sa.Column("student_display_name", sa.String(length=120), nullable=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=True),
        sa.Column("current_position", sa.Integer(), nullable=True),
        sa.Column("violation_count", sa.Integer(), nullable=False),
        sa.Column("last_violation_type", sa.String(length=40), nullable=True),
        sa.Column("last_violation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["quiz_sessions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "student_identifier", name="uq_quiz_participant_identifier"
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_participants_access_token_hash"),
        "quiz_participants",
        ["access_token_hash"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_participants_session_id"),
        "quiz_participants",
        ["session_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_participants_student_id"),
        "quiz_participants",
        ["student_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quiz_session_questions",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["quiz_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("session_id", "question_id"),
        sa.UniqueConstraint(
            "session_id", "position", name="uq_quiz_session_question_position"
        ),
        if_not_exists=True,
    )
    op.create_table(
        "quiz_session_student_questions",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("student_identifier", sa.String(length=80), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["quiz_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("session_id", "student_identifier", "question_id"),
        sa.UniqueConstraint(
            "session_id",
            "student_id",
            "position",
            name="uq_quiz_session_student_question_position",
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_session_student_questions_student_id"),
        "quiz_session_student_questions",
        ["student_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer_data", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("is_graded", sa.Boolean(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["quiz_participants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["quiz_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "participant_id",
            "question_id",
            name="uq_quiz_answer_participant_question",
        ),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_answers_participant_id"),
        "quiz_answers",
        ["participant_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_answers_question_id"),
        "quiz_answers",
        ["question_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_quiz_answers_session_id"),
        "quiz_answers",
        ["session_id"],
        unique=False,
        if_not_exists=True,
    )

    # Columns that 0.4.0 and earlier added at startup to tables created before
    # them. They are already present on a fresh database.
    for table in ("users", "student_accounts"):
        op.add_column(
            table,
            sa.Column(
                "access_token_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            if_not_exists=True,
        )
    op.add_column(
        "quizzes",
        sa.Column(
            "allow_answer_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        if_not_exists=True,
    )
    op.add_column(
        "quiz_sessions",
        sa.Column("allow_answer_review", sa.Boolean(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "quiz_participants",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "quiz_answers",
        sa.Column("feedback", sa.Text(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_quiz_answers_session_id"), table_name="quiz_answers")
    op.drop_index(op.f("ix_quiz_answers_question_id"), table_name="quiz_answers")
    op.drop_index(op.f("ix_quiz_answers_participant_id"), table_name="quiz_answers")
    op.drop_table("quiz_answers")
    op.drop_index(
        op.f("ix_quiz_session_student_questions_student_id"),
        table_name="quiz_session_student_questions",
    )
    op.drop_table("quiz_session_student_questions")
    op.drop_table("quiz_session_questions")
    op.drop_index(
        op.f("ix_quiz_participants_student_id"), table_name="quiz_participants"
    )
    op.drop_index(
        op.f("ix_quiz_participants_session_id"), table_name="quiz_participants"
    )
    op.drop_index(
        op.f("ix_quiz_participants_access_token_hash"), table_name="quiz_participants"
    )
    op.drop_table("quiz_participants")
    op.drop_index(
        op.f("ix_quiz_sessions_training_question_bank_id"), table_name="quiz_sessions"
    )
    op.drop_index(op.f("ix_quiz_sessions_quiz_id"), table_name="quiz_sessions")
    op.drop_index(
        op.f("ix_quiz_sessions_makeup_session_id"), table_name="quiz_sessions"
    )
    op.drop_index(op.f("ix_quiz_sessions_join_code"), table_name="quiz_sessions")
    op.drop_index(op.f("ix_quiz_sessions_class_id"), table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
    op.drop_table("question_codes")
    op.drop_index(
        op.f("ix_question_choices_question_id"), table_name="question_choices"
    )
    op.drop_table("question_choices")
    op.drop_table("makeup_session_selections")
    op.drop_table("makeup_session_quizzes")
    op.drop_index(
        op.f("ix_training_quiz_profiles_quiz_id"), table_name="training_quiz_profiles"
    )
    op.drop_table("training_quiz_profiles")
    op.drop_index(op.f("ix_students_class_id"), table_name="students")
    op.drop_index(op.f("ix_students_account_id"), table_name="students")
    op.drop_table("students")
    op.drop_index(
        op.f("ix_refresh_session_families_family_id"),
        table_name="refresh_session_families",
    )
    op.drop_table("refresh_session_families")
    op.drop_table("quiz_question_banks")
    op.drop_index(op.f("ix_questions_question_bank_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_makeup_sessions_owner_id"), table_name="makeup_sessions")
    op.drop_index(op.f("ix_makeup_sessions_join_code"), table_name="makeup_sessions")
    op.drop_index(op.f("ix_makeup_sessions_class_id"), table_name="makeup_sessions")
    op.drop_table("makeup_sessions")
    op.drop_table("class_training_question_banks")
    op.drop_table("two_factor_credentials")
    op.drop_index(op.f("ix_student_classes_owner_id"), table_name="student_classes")
    op.drop_table("student_classes")
    op.drop_index(op.f("ix_student_accounts_owner_id"), table_name="student_accounts")
    op.drop_index(op.f("ix_student_accounts_identifier"), table_name="student_accounts")
    op.drop_table("student_accounts")
    op.drop_index(op.f("ix_refresh_sessions_user_id"), table_name="refresh_sessions")
    op.drop_index(op.f("ix_refresh_sessions_token_hash"), table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_index(op.f("ix_quizzes_owner_id"), table_name="quizzes")
    op.drop_index(op.f("ix_quizzes_mode"), table_name="quizzes")
    op.drop_table("quizzes")
    op.drop_index(op.f("ix_question_banks_owner_id"), table_name="question_banks")
    op.drop_table("question_banks")
    op.drop_index(op.f("ix_grade_levels_owner_id"), table_name="grade_levels")
    op.drop_table("grade_levels")
    op.drop_index(
        op.f("ix_authentication_challenges_user_id"),
        table_name="authentication_challenges",
    )
    op.drop_index(
        op.f("ix_authentication_challenges_expires_at"),
        table_name="authentication_challenges",
    )
    op.drop_table("authentication_challenges")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    op.drop_table("security_state")
    op.drop_table("quiz_join_codes")
    op.drop_index(op.f("ix_problem_reports_created_at"), table_name="problem_reports")
    op.drop_table("problem_reports")
    op.drop_index(
        op.f("ix_login_rate_limits_window_started_at"), table_name="login_rate_limits"
    )
    op.drop_table("login_rate_limits")
