"""Alembic environment for Open Quiz.

At startup the application applies pending migrations itself through
app.database.migrate_database(), which passes its own connection in
config.attributes. The alembic command line connects with DATABASE_URL
instead, read from the environment or from open-quiz-backend/.env.
"""

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import Connection, create_engine, text

import app.models  # noqa: F401 - registers every table on Base.metadata
from app.config import ENV_FILE
from app.database import MIGRATION_LOCK_KEY, Base, postgres_url

config = context.config


def run_migrations(connection: Connection) -> None:
    # Serialize concurrent upgrades, such as several workers starting at once.
    # The lock is held until the surrounding transaction ends.
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
    )
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Open Quiz migrations must run against a live database")

shared_connection = config.attributes.get("connection")
if shared_connection is not None:
    run_migrations(shared_connection)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    load_dotenv(ENV_FILE)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(f"DATABASE_URL must be set in {ENV_FILE}")
    engine = create_engine(postgres_url(database_url))
    try:
        with engine.begin() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
