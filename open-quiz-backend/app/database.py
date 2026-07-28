from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        choice_columns = {
            column["name"]
            for column in inspect(connection).get_columns("question_choices")
        }
        quiz_columns = {
            column["name"]
            for column in inspect(connection).get_columns("quizzes")
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
        if "points" not in choice_columns:
            connection.execute(
                text(
                    "ALTER TABLE question_choices "
                    "ADD COLUMN points FLOAT NOT NULL DEFAULT 0"
                )
            )
        for column_name, column_type in (
            ("image_data", LargeBinary()),
            ("image_content_type", String(80)),
            ("code_language", String(30)),
            ("code_content", Text()),
        ):
            if column_name not in choice_columns:
                compiled_type = column_type.compile(
                    dialect=connection.dialect
                )
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
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }
            if column_name not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} INTEGER"
                    )
                )
        participant_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "quiz_participants"
            )
        }
        if "student_display_name" not in participant_columns:
            connection.execute(
                text(
                    "ALTER TABLE quiz_participants "
                    "ADD COLUMN student_display_name VARCHAR(120)"
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
                    "ALTER TABLE quiz_participants "
                    "ADD COLUMN current_position INTEGER"
                )
            )
        for column_name, column_type, suffix in (
            ("violation_count", Integer(), " NOT NULL DEFAULT 0"),
            ("last_violation_type", String(40), ""),
            ("last_violation_at", DateTime(timezone=True), ""),
        ):
            if column_name not in participant_columns:
                compiled_type = column_type.compile(
                    dialect=connection.dialect
                )
                connection.execute(
                    text(
                        f"ALTER TABLE quiz_participants "
                        f"ADD COLUMN {column_name} {compiled_type}{suffix}"
                    )
                )
    return sessionmaker(bind=engine, expire_on_commit=False)
