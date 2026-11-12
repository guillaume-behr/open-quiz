"""Schema migrations: fresh databases, pre-migration ones and concurrency."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    CheckConstraint,
    create_engine,
    delete,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.database import Base, migration_config, postgres_url
from app.enums import SessionStatus
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    RefreshSession,
    User,
)
from app.quiz_session_records import delete_quiz_session_records

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


def legacy_question(
    session: DbSession, bank_id: int, prompt: str, answer_mode: str = "single"
) -> int:
    """Insert a bank question into a database migrated to before 0009.

    The model now has columns 0009 adds, so the ORM cannot insert it there.
    """
    return session.execute(
        text(
            "INSERT INTO questions (question_bank_id, prompt, difficulty, "
            "answer_mode, answer_mode_disclosed, allow_code_execution, "
            "correction_mode, created_at) VALUES (:bank_id, :prompt, 'easy', "
            ":answer_mode, true, false, 'automatic', now()) RETURNING id"
        ),
        {"bank_id": bank_id, "prompt": prompt, "answer_mode": answer_mode},
    ).scalar_one()


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
        with DbSession(engine) as session:
            teacher = User(username="teacher", display_name="T", password_hash="x")
            session.add(teacher)
            session.flush()
            quiz = Quiz(owner_id=teacher.id, title="Quiz", question_count=1)
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="C")
            session.add_all([quiz, bank])
            session.flush()
            question_id, other_question_id = (
                legacy_question(session, bank.id, prompt) for prompt in ("Q1", "Q2")
            )
            quiz_session = QuizSession(
                quiz_id=quiz.id, class_name="C", join_code="ORPHAN", status="finished"
            )
            session.add(quiz_session)
            session.flush()
            session.add(
                QuizSessionStudentQuestion(
                    session_id=quiz_session.id,
                    student_id=424242,
                    student_identifier="gone.student",
                    question_id=question_id,
                    position=0,
                )
            )
            session.commit()
            session_id = quiz_session.id
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


def test_upgrade_to_0009_gives_each_session_copies_of_its_questions(
    tmp_path: Path,
) -> None:
    """Existing sessions move to copies of the questions they drew.

    Each session gets one copy per question it drew or answered, with its
    choices and its code. Assignments and answers follow, choice ids recorded
    in answers too, so the bank questions can then change freely. A downgrade
    points everything back at the bank, and a copy goes with its session.
    """
    database_url = database_url_for(tmp_path / "upgrade-0009")
    engine = create_engine(postgres_url(database_url))
    try:
        config = migration_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008")
        with DbSession(engine) as session:
            teacher = User(username="teacher", display_name="T", password_hash="x")
            session.add(teacher)
            session.flush()
            quiz = Quiz(owner_id=teacher.id, title="Quiz", question_count=2)
            bank = QuestionBank(owner_id=teacher.id, grade_level="5e", chapter="C")
            session.add_all([quiz, bank])
            session.flush()
            choice_question = legacy_question(session, bank.id, "Pick")
            written_question = legacy_question(session, bank.id, "Write", "written")
            wrong, right = (
                QuestionChoice(
                    question_id=choice_question,
                    label=label,
                    is_correct=label == "right",
                    points=1.0 if label == "right" else 0.0,
                    position=position,
                )
                for position, label in enumerate(("wrong", "right"))
            )
            session.add_all([right, wrong])
            session.add(
                QuestionCode(
                    question_id=choice_question, language="python", content="x"
                )
            )
            common, personal = (
                QuizSession(
                    quiz_id=quiz.id, class_name="C", join_code=code, status="finished"
                )
                for code in ("COMMON", "PERSON")
            )
            session.add_all([common, personal])
            session.flush()
            session.add_all(
                QuizSessionQuestion(
                    session_id=common.id, question_id=question_id, position=position
                )
                for position, question_id in enumerate(
                    (choice_question, written_question)
                )
            )
            session.add(
                QuizSessionStudentQuestion(
                    session_id=personal.id,
                    student_identifier="ada",
                    question_id=choice_question,
                    position=0,
                )
            )
            participants = [
                QuizParticipant(session_id=quiz_session.id, student_identifier="ada")
                for quiz_session in (common, personal)
            ]
            session.add_all(participants)
            session.flush()
            session.add_all(
                QuizAnswer(
                    session_id=participant.session_id,
                    participant_id=participant.id,
                    question_id=choice_question,
                    answer_data=json.dumps({"selected_choice_ids": [right.id, "x"]}),
                    score=1.0,
                )
                for participant in participants
            )
            session.add(
                QuizAnswer(
                    session_id=common.id,
                    participant_id=participants[0].id,
                    question_id=written_question,
                    answer_data=json.dumps({"text": "écrit"}),
                )
            )
            session.commit()
            common_id, personal_id, right_id = common.id, personal.id, right.id
            bank_id = bank.id

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        def references(session: DbSession) -> list[tuple[str, int, int]]:
            return sorted(
                session.execute(
                    text(
                        "SELECT 'common', session_id, question_id "
                        "FROM quiz_session_questions UNION ALL "
                        "SELECT 'personal', session_id, question_id "
                        "FROM quiz_session_student_questions UNION ALL "
                        "SELECT 'answer', session_id, question_id FROM quiz_answers"
                    )
                ).all()
            )

        with DbSession(engine) as session:
            copies = {
                (copy.quiz_session_id, copy.source_question_id): copy
                for copy in session.scalars(
                    select(Question).where(Question.quiz_session_id.is_not(None))
                )
            }
            assert sorted(copies) == sorted(
                [
                    (common_id, choice_question),
                    (common_id, written_question),
                    (personal_id, choice_question),
                ]
            )
            assert all(copy.question_bank_id is None for copy in copies.values())
            common_choice = copies[(common_id, choice_question)]
            assert common_choice.prompt == "Pick"
            assert references(session) == sorted(
                [
                    ("common", common_id, common_choice.id),
                    ("common", common_id, copies[(common_id, written_question)].id),
                    (
                        "personal",
                        personal_id,
                        copies[(personal_id, choice_question)].id,
                    ),
                    ("answer", common_id, common_choice.id),
                    ("answer", common_id, copies[(common_id, written_question)].id),
                    ("answer", personal_id, copies[(personal_id, choice_question)].id),
                ]
            )
            for (session_id, source_id), copy in copies.items():
                if source_id != choice_question:
                    continue
                copied_right = session.scalar(
                    select(QuestionChoice.id).where(
                        QuestionChoice.question_id == copy.id,
                        QuestionChoice.label == "right",
                    )
                )
                assert copied_right not in (None, right_id)
                assert json.loads(
                    session.scalar(
                        select(QuizAnswer.answer_data).where(
                            QuizAnswer.session_id == session_id,
                            QuizAnswer.question_id == copy.id,
                        )
                    )
                ) == {"selected_choice_ids": [copied_right, "x"]}
                assert (
                    session.scalar(
                        select(QuestionCode.content).where(
                            QuestionCode.question_id == copy.id
                        )
                    )
                    == "x"
                )
            upgraded_references = references(session)

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0008")
        with DbSession(engine) as session:
            assert {question_id for _, _, question_id in references(session)} == {
                choice_question,
                written_question,
            }
            assert set(
                session.scalars(
                    text(
                        "SELECT answer_data FROM quiz_answers "
                        "WHERE question_id = :question_id"
                    ),
                    {"question_id": choice_question},
                )
            ) == {json.dumps({"selected_choice_ids": [right_id, "x"]})}
            assert session.scalar(text("SELECT count(*) FROM questions")) == 2
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert_schema_matches_models(database_url)

        with DbSession(engine) as session:
            assert len(references(session)) == len(upgraded_references)
            # The bank questions go; the sessions keep their copies.
            session.execute(
                delete(Question).where(Question.question_bank_id == bank_id)
            )
            session.commit()
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Question)
                    .where(Question.source_question_id.is_(None))
                )
                == 3
            )
            delete_quiz_session_records([common_id], session)
            session.commit()
            remaining = session.execute(
                select(Question.quiz_session_id, func.count(QuestionChoice.id))
                .outerjoin(QuestionChoice, QuestionChoice.question_id == Question.id)
                .group_by(Question.id)
            ).all()
            assert remaining == [(personal_id, 2)]
            assert session.scalar(select(func.count()).select_from(QuestionCode)) == 1
    finally:
        engine.dispose()
