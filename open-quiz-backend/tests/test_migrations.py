"""Schema migrations: fresh databases, pre-migration ones and concurrency."""

import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.database import Base, migration_config, postgres_url
from app.enums import SessionStatus
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    Quiz,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    RefreshSession,
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
                connection, opts={"compare_type": True, "compare_server_default": True}
            )
            head = ScriptDirectory.from_config(migration_config()).get_current_head()
            assert context.get_current_revision() == head
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def accept_current_models(connection: Any) -> None:
    """Let today's models write rows into a schema older than 0011.

    The columns 0011 drops have no default: the models no longer set them.
    """
    connection.execute(
        text(
            "ALTER TABLE quizzes ALTER easy_points SET DEFAULT 0, "
            "ALTER medium_points SET DEFAULT 0, ALTER hard_points SET DEFAULT 0; "
            "ALTER TABLE questions ALTER correction_mode SET DEFAULT 'automatic'"
        )
    )


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
    baseline fills them in, keeps every row, and the paste and copy alerts
    those releases recorded are cleared once. Their images, stored in each question
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
            session.add(
                QuizParticipant(
                    session_id=quiz_session.id,
                    student_identifier="legacy.copier",
                    violation_count=2,
                    last_violation_type="copy_attempt",
                    last_violation_at=datetime.now(UTC),
                )
            )
            session.commit()
        with engine.begin() as connection:
            # Columns 0.4.0 had and 0011 drops.
            connection.exec_driver_sql(
                "ALTER TABLE questions ADD correction_mode varchar(20) "
                "NOT NULL DEFAULT 'automatic'"
            )
            for column in ("easy_points", "medium_points", "hard_points"):
                connection.exec_driver_sql(
                    f"ALTER TABLE quizzes ADD {column} float NOT NULL DEFAULT 0"
                )
            connection.exec_driver_sql(
                "ALTER TABLE refresh_session_families ADD parent_session_id integer"
            )
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
        ).fetchall() == [(0, None, None), (0, None, None)]
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


def test_vocabulary_constraints_match_the_models_and_refuse_unknown_values(
    tmp_path: Path,
) -> None:
    """The database accepts exactly the values app.enums names."""
    settings = settings_for(tmp_path / "vocabulary")
    with make_client(settings):
        pass

    engine = create_engine(postgres_url(settings.database_url))
    try:
        with engine.connect() as connection:
            stored = dict(
                connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE contype = 'c' AND conname LIKE 'ck\\_%' "
                        "AND connamespace = current_schema()::regnamespace"
                    )
                ).all()
            )
        declared = {
            constraint.name
            for table in Base.metadata.tables.values()
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert set(stored) == declared
        for member in SessionStatus:
            assert f"'{member.value}'" in stored["ck_quiz_sessions_status"]

        with DbSession(engine) as session:
            owner = User(username="vocabulary", display_name="V", password_hash="x")
            session.add(owner)
            session.flush()
            session.add(
                Quiz(owner_id=owner.id, title="Typo", question_count=1, mode="exams")
            )
            with pytest.raises(IntegrityError, match="ck_quizzes_mode"):
                session.flush()
    finally:
        engine.dispose()


def test_every_foreign_key_leads_an_index(tmp_path: Path) -> None:
    """Filtering on a foreign key, or deleting its parent, never scans a table.

    A column that is only the second one of a composite primary key is not
    indexed by it: it needs an index of its own.
    """
    settings = settings_for(tmp_path / "foreign-key-indexes")
    with make_client(settings):
        pass

    engine = create_engine(postgres_url(settings.database_url))
    try:
        inspector = inspect(engine)
        unindexed = []
        for table in inspector.get_table_names():
            leading = {
                (inspector.get_pk_constraint(table)["constrained_columns"] or [None])[0]
            }
            leading |= {
                index["column_names"][0] for index in inspector.get_indexes(table)
            }
            leading |= {
                constraint["column_names"][0]
                for constraint in inspector.get_unique_constraints(table)
            }
            unindexed += [
                f"{table}.{foreign_key['constrained_columns'][0]}"
                for foreign_key in inspector.get_foreign_keys(table)
                if foreign_key["constrained_columns"][0] not in leading
            ]
        assert unindexed == []
    finally:
        engine.dispose()


def test_upgrade_to_0008_clears_dangling_students_and_widens_timestamps(
    tmp_path: Path,
) -> None:
    """Student question rows lose a reference to a deleted student.

    Before 0008, quiz_session_student_questions.student_id had no foreign key:
    deleting a student left it pointing nowhere. The upgrade clears those, then
    the new key keeps them consistent. Unix timestamps fit past 2038.
    """
    database_url = database_url_for(tmp_path / "upgrade-0008")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0007")
            accept_current_models(connection)
        with DbSession(engine) as session:
            teacher = User(username="teacher", display_name="T", password_hash="x")
            session.add(teacher)
            session.flush()
            quiz = Quiz(owner_id=teacher.id, title="Quiz", question_count=1)
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="C")
            session.add_all([quiz, bank])
            session.flush()
            question, other_question = (
                Question(
                    question_bank_id=bank.id,
                    prompt=prompt,
                    difficulty="easy",
                    answer_mode="single",
                )
                for prompt in ("Q1", "Q2")
            )
            quiz_session = QuizSession(
                quiz_id=quiz.id, class_name="C", join_code="ORPHAN", status="finished"
            )
            session.add_all([question, other_question, quiz_session])
            session.flush()
            session.add(
                QuizSessionStudentQuestion(
                    session_id=quiz_session.id,
                    student_id=424242,
                    student_identifier="gone.student",
                    question_id=question.id,
                    position=0,
                )
            )
            session.commit()
            session_id, other_question_id = quiz_session.id, other_question.id
            teacher_id = teacher.id

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with DbSession(engine) as session:
            assert session.scalars(
                text("SELECT student_id FROM quiz_session_student_questions")
            ).all() == [None]
            # Rows without a student account are unique by identifier too.
            session.add(
                QuizSessionStudentQuestion(
                    session_id=session_id,
                    student_identifier="gone.student",
                    question_id=other_question_id,
                    position=0,
                )
            )
            with pytest.raises(
                IntegrityError, match="uq_quiz_session_student_question"
            ):
                session.flush()
            session.rollback()
            session.add(
                RefreshSession(
                    token_hash="0" * 64, user_id=teacher_id, expires_at=2**33
                )
            )
            session.commit()
    finally:
        engine.dispose()


def test_upgrade_to_0009_merges_levels_and_renames_names_differing_by_case(
    tmp_path: Path,
) -> None:
    """Names unique only with their case keep their rows under new names.

    Levels differing by case merge into the oldest one; a class or a bank
    whose name clashes ignoring case gets a numbered suffix.
    """
    database_url = database_url_for(tmp_path / "upgrade-0009")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008")
        with engine.begin() as connection:
            owner = connection.execute(
                text(
                    "INSERT INTO users (username, display_name, password_hash, "
                    "is_admin, is_active, access_token_generation, created_at) "
                    "VALUES ('t', 'T', 'x', false, true, 0, now()) RETURNING id"
                )
            ).scalar_one()
            for name in ("Tle", "tle", "1ere"):
                connection.execute(
                    text(
                        "INSERT INTO grade_levels (owner_id, name, created_at) "
                        "VALUES (:owner, :name, now())"
                    ),
                    {"owner": owner, "name": name},
                )
            for name, level in (
                ("TG1", "tle"),
                ("tg1", "Tle"),
                ("tg1 (2)", "1ere"),
                ("x" * 120, "Tle"),
                ("X" * 120, "Tle"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO student_classes (owner_id, name, grade_level, "
                        "created_at) VALUES (:owner, :name, :level, now())"
                    ),
                    {"owner": owner, "name": name, "level": level},
                )
            for level, chapter in (("Tle", "Suites"), ("tle", "suites")):
                connection.execute(
                    text(
                        "INSERT INTO question_banks (owner_id, grade_level, chapter, "
                        "created_at) VALUES (:owner, :level, :chapter, now())"
                    ),
                    {"owner": owner, "level": level, "chapter": chapter},
                )

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT name FROM grade_levels ORDER BY id")
            ).scalars().all() == ["Tle", "1ere"]
            assert connection.execute(
                text("SELECT name, grade_level FROM student_classes ORDER BY id")
            ).all() == [
                ("TG1", "Tle"),
                ("tg1 (3)", "Tle"),
                ("tg1 (2)", "1ere"),
                ("x" * 120, "Tle"),
                ("X" * 116 + " (2)", "Tle"),
            ]
            assert connection.execute(
                text("SELECT grade_level, chapter FROM question_banks ORDER BY id")
            ).all() == [("Tle", "Suites"), ("Tle", "suites (2)")]
    finally:
        engine.dispose()


def test_upgrade_to_0010_lets_the_database_cascade_deletes(tmp_path: Path) -> None:
    """Rows written before 0010 lose their children with them afterwards."""
    database_url = database_url_for(tmp_path / "upgrade-0010")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0009")
            accept_current_models(connection)
        with DbSession(engine) as session:
            teacher = User(username="teacher", display_name="T", password_hash="x")
            session.add(teacher)
            session.flush()
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="C")
            session.add(bank)
            session.flush()
            question = Question(
                question_bank_id=bank.id,
                prompt="Q",
                difficulty="easy",
                answer_mode="single",
            )
            session.add(question)
            session.flush()
            session.add(QuestionChoice(question_id=question.id, label="A", position=0))
            session.commit()

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM users"))
            for table in ("question_banks", "questions", "question_choices"):
                assert (
                    connection.execute(
                        text(f"SELECT count(*) FROM {table}")  # noqa: S608 - constant
                    ).scalar_one()
                    == 0
                )
    finally:
        engine.dispose()


def test_upgrade_to_0011_clears_legacy_rows_and_dead_columns(tmp_path: Path) -> None:
    """Cancelled sessions, retired alerts and account-less pupils are cleared.

    Nothing writes them any more: the application stops handling them, so the
    upgrade removes what an older release left, then drops unused columns.
    """
    database_url = database_url_for(tmp_path / "upgrade-0011")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0010")

        def insert(connection: Any, statement: str, **values: object) -> int:
            return connection.execute(text(statement), values).scalar_one()

        with engine.begin() as connection:
            owner = insert(
                connection,
                "INSERT INTO users (username, display_name, password_hash, "
                "access_token_generation, is_admin, is_active, created_at) "
                "VALUES ('t', 'T', 'x', 0, false, true, now()) RETURNING id",
            )
            quiz = insert(
                connection,
                "INSERT INTO quizzes (owner_id, mode, title, source_language, "
                "question_count, duration_seconds, allow_previous_questions, "
                "allow_answer_review, allow_negative_points, same_questions_for_all, "
                "easy_question_count, medium_question_count, hard_question_count, "
                "easy_points, medium_points, hard_points, created_at) VALUES "
                "(:owner, 'exam', 'Q', 'fr', 1, 600, true, true, false, false, "
                "1, 0, 0, 0, 0, 0, now()) RETURNING id",
                owner=owner,
            )
            class_id = insert(
                connection,
                "INSERT INTO student_classes (owner_id, name, grade_level, "
                "created_at) VALUES (:owner, 'C', 'Tle', now()) RETURNING id",
                owner=owner,
            )
            legacy_pupil = insert(
                connection,
                "INSERT INTO students (class_id, identifier, display_name, "
                "created_at) VALUES (:class_id, 'legacy', 'Legacy', now()) "
                "RETURNING id",
                class_id=class_id,
            )
            makeup = insert(
                connection,
                "INSERT INTO makeup_sessions (owner_id, class_name, join_code, "
                "status, created_at) VALUES (:owner, 'C', 'MAKEUP1', 'cancelled', "
                "now()) RETURNING id",
                owner=owner,
            )
            sessions = {}
            for code, status_value, makeup_id in (
                ("CANCEL1", "cancelled", None),
                ("CHILD01", "waiting", makeup),
                ("KEPT001", "finished", None),
            ):
                sessions[code] = insert(
                    connection,
                    "INSERT INTO quiz_sessions (quiz_id, class_name, join_code, "
                    "status, created_at, paused_duration_seconds, "
                    "makeup_session_id) VALUES (:quiz, 'C', :code, :status, now(), "
                    "0, :makeup) RETURNING id",
                    quiz=quiz,
                    code=code,
                    status=status_value,
                    makeup=makeup_id,
                )
            for code in ("CANCEL1", "CHILD01", "KEPT001", "MAKEUP1"):
                connection.execute(
                    text("INSERT INTO quiz_join_codes (code) VALUES (:code)"),
                    {"code": code},
                )
            connection.execute(
                text(
                    "INSERT INTO quiz_participants (session_id, student_id, "
                    "student_identifier, violation_count, last_violation_type, "
                    "last_violation_at, joined_at) VALUES (:session, :pupil, "
                    "'legacy', 3, 'paste_attempt', now(), now())"
                ),
                {"session": sessions["KEPT001"], "pupil": legacy_pupil},
            )

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT join_code FROM quiz_sessions")
            ).scalars().all() == ["KEPT001"]
            assert (
                connection.execute(
                    text("SELECT count(*) FROM makeup_sessions")
                ).scalar_one()
                == 0
            )
            assert connection.execute(
                text("SELECT code FROM quiz_join_codes")
            ).scalars().all() == ["KEPT001"]
            assert (
                connection.execute(text("SELECT count(*) FROM students")).scalar_one()
                == 0
            )
            assert connection.execute(
                text(
                    "SELECT student_id, violation_count, last_violation_type, "
                    "last_violation_at FROM quiz_participants"
                )
            ).all() == [(None, 0, None, None)]
    finally:
        engine.dispose()


def test_upgrade_to_0012_lets_a_question_leave_its_bank(tmp_path: Path) -> None:
    """Existing questions keep their bank; a removed one may then have none."""
    database_url = database_url_for(tmp_path / "upgrade-0012")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0011")
        with DbSession(engine) as session:
            teacher = User(username="teacher", display_name="T", password_hash="x")
            session.add(teacher)
            session.flush()
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="C")
            session.add(bank)
            session.flush()
            session.add_all(
                Question(
                    question_bank_id=bank.id,
                    prompt=prompt,
                    difficulty="easy",
                    answer_mode="single",
                )
                for prompt in ("Kept", "Detached")
            )
            session.commit()
            bank_id = bank.id

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with engine.begin() as connection:
            assert connection.execute(
                text("SELECT question_bank_id FROM questions ORDER BY prompt")
            ).scalars().all() == [bank_id, bank_id]
            connection.execute(
                text(
                    "UPDATE questions SET question_bank_id = NULL "
                    "WHERE prompt = 'Detached'"
                )
            )
            connection.execute(text("DELETE FROM question_banks"))
            assert connection.execute(
                text("SELECT prompt FROM questions")
            ).scalars().all() == ["Detached"]
    finally:
        engine.dispose()
