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
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    sqlite = database_url.startswith("sqlite")
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
        quiz_columns = {
            column["name"] for column in inspect(connection).get_columns("quizzes")
        }
        quiz_session_columns = {
            column["name"]
            for column in inspect(connection).get_columns("quiz_sessions")
        }
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
        if "source_language" not in quiz_columns:
            connection.execute(
                text(
                    "ALTER TABLE quizzes ADD COLUMN "
                    "source_language VARCHAR(35) NOT NULL DEFAULT 'fr'"
                )
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
        if "points" not in choice_columns:
            connection.execute(
                text(
                    "ALTER TABLE question_choices "
                    "ADD COLUMN points FLOAT NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                text("UPDATE question_choices SET points = 1 WHERE is_correct = TRUE")
            )
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
        ):
            columns = {
                column["name"] for column in inspect(connection).get_columns(table_name)
            }
            if column_name not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} INTEGER")
                )
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
    return sessionmaker(bind=engine, expire_on_commit=False)
