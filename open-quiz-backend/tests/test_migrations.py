"""Schema migrations: fresh databases, pre-migration ones and concurrency."""

import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DbSession

from app.database import Base, migration_config, postgres_url
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    Quiz,
    QuizParticipant,
    QuizSession,
    User,
)

from support import (
    VALID_PNG,
    database_connection,
    database_url_for,
    make_client,
    settings_for,
)


def assert_schema_matches_models(database_url: str) -> None:
    engine = create_engine(postgres_url(database_url))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            head = ScriptDirectory.from_config(migration_config()).get_current_head()
            assert context.get_current_revision() == head
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def test_migrations_build_the_schema_the_models_describe(tmp_path: Path) -> None:
    """A database migrated from empty matches the models exactly.

    A model change committed without its migration fails here. Generate one
    with `uv run alembic revision --autogenerate`.
    """
    settings = settings_for(tmp_path / "migrated")
    with make_client(settings):
        pass

    assert_schema_matches_models(settings.database_url)


def test_migrations_adopt_a_database_created_before_them(tmp_path: Path) -> None:
    """Startup carries a database from 0.4.0 or earlier over to migrations.

    Those releases created tables with create_all() and added late columns at
    startup, so an older instance can lack tables, columns and indexes. The
    baseline fills them in, keeps every row, and the paste alerts those
    releases recorded are cleared once. Their images, stored in each question
    and choice row, move once per distinct content to stored_images.
    """
    database = tmp_path / "pre-migrations"
    database_url = database_url_for(database)
    engine = create_engine(postgres_url(database_url))
    try:
        Base.metadata.create_all(engine)
        with DbSession(engine) as session:
            teacher = User(
                username="legacy-teacher",
                display_name="Legacy teacher",
                password_hash="x",
            )
            session.add(teacher)
            session.flush()
            quiz = Quiz(
                owner_id=teacher.id,
                title="Legacy quiz",
                question_count=1,
                easy_question_count=1,
                medium_question_count=0,
                hard_question_count=0,
            )
            session.add(quiz)
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="Legacy")
            session.add(bank)
            session.flush()
            question = Question(
                question_bank_id=bank.id,
                prompt="Legacy question",
                difficulty="easy",
                answer_mode="single",
                correction_mode="automatic",
            )
            session.add(question)
            session.flush()
            session.add(QuestionChoice(question_id=question.id, label="", position=0))
            quiz_session = QuizSession(
                quiz_id=quiz.id,
                class_name="Legacy class",
                join_code="LEG123",
                status="finished",
            )
            session.add(quiz_session)
            session.flush()
            session.add(
                QuizParticipant(
                    session_id=quiz_session.id,
                    student_identifier="legacy.student",
                    violation_count=1,
                    last_violation_type="paste_attempt",
                    last_violation_at=datetime.now(UTC),
                )
            )
            session.commit()
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE quiz_answers DROP COLUMN feedback")
            connection.exec_driver_sql(
                "ALTER TABLE quiz_participants DROP COLUMN submitted_at"
            )
            connection.exec_driver_sql(
                "ALTER TABLE quizzes DROP COLUMN allow_answer_review"
            )
            connection.exec_driver_sql(
                "DROP INDEX ix_login_rate_limits_window_started_at"
            )
            connection.exec_driver_sql("DROP TABLE makeup_session_selections")
            # 0.4.0 kept images in the rows; one is used twice here.
            for table in ("questions", "question_choices"):
                connection.exec_driver_sql(f"ALTER TABLE {table} DROP image_sha256")
                connection.exec_driver_sql(
                    f"ALTER TABLE {table} ADD image_data bytea, "
                    "ADD image_content_type varchar(80)"
                )
                connection.exec_driver_sql(
                    f"UPDATE {table} SET image_data = %s, "  # noqa: S608
                    "image_content_type = 'image/png'",
                    (VALID_PNG,),
                )
            connection.exec_driver_sql("DROP TABLE stored_images")
    finally:
        engine.dispose()

    with make_client(settings_for(database)):
        pass

    assert_schema_matches_models(database_url)
    with database_connection(database) as connection:
        assert connection.execute(
            "SELECT title, allow_answer_review FROM quizzes"
        ).fetchall() == [("Legacy quiz", True)]
        assert connection.execute(
            "SELECT violation_count, last_violation_type, last_violation_at"
            " FROM quiz_participants"
        ).fetchall() == [(0, None, None)]
        stored = connection.execute(
            "SELECT sha256, content_type, data FROM stored_images"
        ).fetchall()
        assert stored == [(sha256(VALID_PNG).hexdigest(), "image/png", VALID_PNG)]
        assert connection.execute(
            "SELECT image_sha256 FROM questions UNION ALL "
            "SELECT image_sha256 FROM question_choices"
        ).fetchall() == [(stored[0][0],), (stored[0][0],)]


def test_concurrent_startups_migrate_the_database_once(tmp_path: Path) -> None:
    """Workers starting together on an empty database do not race each other.

    Each worker is its own process, so the migrations serialize on a
    PostgreSQL advisory lock rather than on anything held in memory.
    """
    database_url = database_url_for(tmp_path / "concurrent-migrations")
    script = (
        "import sys\n"
        "from sqlalchemy import create_engine\n"
        "from app.database import migrate_database, postgres_url\n"
        "migrate_database(create_engine(postgres_url(sys.argv[1])))\n"
    )
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", script, database_url],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    for worker in workers:
        _, errors = worker.communicate(timeout=60)
        assert worker.returncode == 0, errors.decode()

    assert_schema_matches_models(database_url)
