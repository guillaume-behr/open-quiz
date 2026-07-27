from sqlalchemy import LargeBinary, String, Text, create_engine, inspect, text
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
    return sessionmaker(bind=engine, expire_on_commit=False)
