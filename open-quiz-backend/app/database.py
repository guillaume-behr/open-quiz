import os
from pathlib import Path

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def legacy_difficulty_counts(
    question_count: int,
    percentages: dict[str, int],
    available: dict[str, int],
) -> dict[str, int]:
    """Reproduce the pre-0.2 percentage draw before persisting explicit counts."""
    ease_priority = {"easy": 2, "medium": 1, "hard": 0}
    exact = {
        difficulty: question_count * percentage / 100
        for difficulty, percentage in percentages.items()
    }
    counts = {difficulty: int(value) for difficulty, value in exact.items()}
    remaining = question_count - sum(counts.values())
    priorities = sorted(
        percentages,
        key=lambda difficulty: (
            exact[difficulty] - counts[difficulty],
            percentages[difficulty],
            ease_priority[difficulty],
        ),
        reverse=True,
    )
    for difficulty in priorities[:remaining]:
        counts[difficulty] += 1
    counts = {
        difficulty: min(count, available.get(difficulty, 0))
        for difficulty, count in counts.items()
    }
    remaining = question_count - sum(counts.values())
    while remaining:
        candidates = [
            difficulty
            for difficulty in percentages
            if counts[difficulty] < available.get(difficulty, 0)
        ]
        if not candidates:
            break
        difficulty = max(
            candidates,
            key=lambda item: (percentages[item], ease_priority[item]),
        )
        counts[difficulty] += 1
        remaining -= 1
    return counts


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or url.database in {None, "", ":memory:"}:
        return None
    if url.database.startswith("file:"):
        return None
    return Path(url.database).resolve()


def secure_sqlite_files(database_path: Path) -> None:
    if os.name != "posix":
        return
    for path in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        if path.exists():
            path.chmod(0o600)


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    sqlite = database_url.startswith("sqlite")
    database_path = sqlite_database_path(database_url)
    if database_path is not None:
        if os.name == "posix":
            os.umask(0o077)
        database_path.touch(mode=0o600, exist_ok=True)
        secure_sqlite_files(database_path)
    connect_args = {"check_same_thread": False, "timeout": 30} if sqlite else {}
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
            if database_path is not None:
                secure_sqlite_files(database_path)

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO grade_levels (owner_id, name, created_at) "
                "SELECT DISTINCT owner_id, grade_level, CURRENT_TIMESTAMP "
                "FROM student_classes "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM grade_levels "
                "WHERE grade_levels.owner_id = student_classes.owner_id "
                "AND grade_levels.name = student_classes.grade_level"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO grade_levels (owner_id, name, created_at) "
                "SELECT DISTINCT owner_id, grade_level, CURRENT_TIMESTAMP "
                "FROM question_banks "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM grade_levels "
                "WHERE grade_levels.owner_id = question_banks.owner_id "
                "AND grade_levels.name = question_banks.grade_level"
                ")"
            )
        )
        choice_columns = {
            column["name"]
            for column in inspect(connection).get_columns("question_choices")
        }
        question_columns = {
            column["name"] for column in inspect(connection).get_columns("questions")
        }
        if "response_language" not in question_columns:
            connection.execute(
                text("ALTER TABLE questions ADD COLUMN response_language VARCHAR(30)")
            )
        if "points" not in question_columns:
            connection.execute(
                text("ALTER TABLE questions ADD COLUMN points FLOAT NOT NULL DEFAULT 1")
            )
        quiz_columns = {
            column["name"] for column in inspect(connection).get_columns("quizzes")
        }
        if "mode" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "mode VARCHAR(20) NOT NULL DEFAULT 'exam'"
                )
            )
        quiz_session_columns = {
            column["name"]
            for column in inspect(connection).get_columns("quiz_sessions")
        }
        if "makeup_session_id" not in quiz_session_columns:
            connection.execute(
                text("ALTER TABLE quiz_sessions ADD COLUMN makeup_session_id INTEGER")
            )
        if "duration_seconds" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "duration_seconds INTEGER NOT NULL DEFAULT 1800"
                )
            )
        if "allow_previous_questions" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "allow_previous_questions BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        if "same_questions_for_all" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "same_questions_for_all BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
            connection.execute(
                text("UPDATE quizzes SET same_questions_for_all = FALSE")
            )
        if "source_language" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "source_language VARCHAR(35) NOT NULL DEFAULT 'fr'"
                )
            )
        difficulty_count_columns = (
            "easy_question_count",
            "medium_question_count",
            "hard_question_count",
        )
        added_difficulty_counts = any(
            column_name not in quiz_columns for column_name in difficulty_count_columns
        )
        for column_name in difficulty_count_columns:
            if column_name not in quiz_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE quizzes ADD COLUMN {column_name} "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
        for column_name in ("easy_points", "medium_points", "hard_points"):
            if column_name not in quiz_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE quizzes ADD COLUMN {column_name} "
                        "FLOAT NOT NULL DEFAULT 0"
                    )
                )
        if added_difficulty_counts and {
            "easy_percentage",
            "medium_percentage",
            "hard_percentage",
        }.issubset(quiz_columns):
            legacy_quizzes = list(
                connection.execute(
                    text(
                        "SELECT id, question_count, easy_percentage, "
                        "medium_percentage, hard_percentage FROM quizzes"
                    )
                ).mappings()
            )
            for legacy_quiz in legacy_quizzes:
                available_rows = connection.execute(
                    text(
                        "SELECT questions.difficulty, COUNT(questions.id) "
                        "FROM questions "
                        "JOIN quiz_question_banks ON "
                        "quiz_question_banks.question_bank_id = "
                        "questions.question_bank_id "
                        "WHERE quiz_question_banks.quiz_id = :quiz_id "
                        "GROUP BY questions.difficulty"
                    ),
                    {"quiz_id": legacy_quiz["id"]},
                )
                available: dict[str, int] = {}
                for difficulty, count in available_rows:
                    available[difficulty] = count
                counts = legacy_difficulty_counts(
                    legacy_quiz["question_count"],
                    {
                        "easy": legacy_quiz["easy_percentage"],
                        "medium": legacy_quiz["medium_percentage"],
                        "hard": legacy_quiz["hard_percentage"],
                    },
                    available,
                )
                connection.execute(
                    text(
                        "UPDATE quizzes SET question_count = :question_count, "
                        "easy_question_count = :easy, "
                        "medium_question_count = :medium, "
                        "hard_question_count = :hard WHERE id = :quiz_id"
                    ),
                    {
                        "quiz_id": legacy_quiz["id"],
                        "question_count": sum(counts.values()),
                        **counts,
                    },
                )
        if "paused_at" not in quiz_session_columns:
            connection.execute(
                text("ALTER TABLE quiz_sessions ADD COLUMN paused_at DATETIME")
            )
        if "paused_duration_seconds" not in quiz_session_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_sessions ADD COLUMN "
                    "paused_duration_seconds INTEGER NOT NULL DEFAULT 0"
                )
            )
        for column_name, definition, quiz_column in (
            ("quiz_title", "VARCHAR(160)", "title"),
            ("source_language", "VARCHAR(35)", "source_language"),
            ("duration_seconds", "INTEGER", "duration_seconds"),
            (
                "allow_previous_questions",
                "BOOLEAN",
                "allow_previous_questions",
            ),
            (
                "same_questions_for_all",
                "BOOLEAN",
                "same_questions_for_all",
            ),
        ):
            if column_name not in quiz_session_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE quiz_sessions "
                        f"ADD COLUMN {column_name} {definition}"
                    )
                )
                connection.execute(
                    text(
                        f"UPDATE quiz_sessions SET {column_name} = "
                        f"(SELECT {quiz_column} FROM quizzes "
                        "WHERE quizzes.id = quiz_sessions.quiz_id)"
                    )
                )
        if "points" not in choice_columns:
            connection.execute(
                text(
                    "ALTER TABLE question_choices "
                    "ADD COLUMN points FLOAT NOT NULL DEFAULT 0"
                )
            )
            connection.execute(text("UPDATE question_choices SET points = 0"))
        for column_name, column_type in (
            ("image_data", LargeBinary()),
            ("image_content_type", String(80)),
            ("code_language", String(30)),
            ("code_content", Text()),
        ):
            if column_name not in choice_columns:
                compiled_type = column_type.compile(dialect=connection.dialect)
                connection.execute(
                    text(
                        f"ALTER TABLE question_choices "
                        f"ADD COLUMN {column_name} {compiled_type}"
                    )
                )
        for table_name, column_name in (
            ("quiz_sessions", "class_id"),
            ("quiz_participants", "student_id"),
            ("students", "account_id"),
        ):
            columns = {
                column["name"] for column in inspect(connection).get_columns(table_name)
            }
            if column_name not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} INTEGER")
                )
        student_question_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "quiz_session_student_questions"
            )
        }
        if "student_id" not in student_question_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_session_student_questions "
                    "ADD COLUMN student_id INTEGER"
                )
            )
        if "points" not in student_question_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_session_student_questions "
                    "ADD COLUMN points FLOAT NOT NULL DEFAULT 0"
                )
            )
        session_question_columns = {
            column["name"]
            for column in inspect(connection).get_columns("quiz_session_questions")
        }
        if "points" not in session_question_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_session_questions "
                    "ADD COLUMN points FLOAT NOT NULL DEFAULT 0"
                )
            )
        connection.execute(
            text(
                "UPDATE quiz_participants SET student_id = NULL "
                "WHERE student_id IN "
                "(SELECT id FROM students WHERE account_id IS NULL)"
            )
        )
        connection.execute(
            text(
                "DELETE FROM quiz_session_student_questions "
                "WHERE student_id IN "
                "(SELECT id FROM students WHERE account_id IS NULL)"
            )
        )
        connection.execute(text("DELETE FROM students WHERE account_id IS NULL"))
        participant_columns = {
            column["name"]
            for column in inspect(connection).get_columns("quiz_participants")
        }
        if "student_display_name" not in participant_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_participants "
                    "ADD COLUMN student_display_name VARCHAR(120)"
                )
            )
        answer_columns = {
            column["name"] for column in inspect(connection).get_columns("quiz_answers")
        }
        if "is_graded" not in answer_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_answers "
                    "ADD COLUMN is_graded BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            connection.execute(
                text(
                    "UPDATE quiz_answers SET is_graded = CASE "
                    "WHEN question_id IN "
                    "(SELECT id FROM questions WHERE answer_mode = 'written') "
                    "THEN FALSE ELSE TRUE END"
                )
            )
        if "access_token_hash" not in participant_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_participants "
                    "ADD COLUMN access_token_hash VARCHAR(64)"
                )
            )
        if "current_position" not in participant_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_participants ADD COLUMN current_position INTEGER"
                )
            )
        for column_name, column_type, suffix in (
            ("violation_count", Integer(), " NOT NULL DEFAULT 0"),
            ("last_violation_type", String(40), ""),
            ("last_violation_at", DateTime(timezone=True), ""),
        ):
            if column_name not in participant_columns:
                compiled_type = column_type.compile(dialect=connection.dialect)
                connection.execute(
                    text(
                        f"ALTER TABLE quiz_participants "
                        f"ADD COLUMN {column_name} {compiled_type}{suffix}"
                    )
                )
    if database_path is not None:
        secure_sqlite_files(database_path)
    return sessionmaker(bind=engine, expire_on_commit=False)
