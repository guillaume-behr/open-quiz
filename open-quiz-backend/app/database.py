import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent.parent / "migrations"
# Arbitrary application-wide key for pg_advisory_xact_lock: "openquiz" read as
# a big-endian 64-bit integer.
MIGRATION_LOCK_KEY = 0x6F70656E7175697A
# Taken by the session expiry loop, so that one worker runs it at a time.
EXPIRY_LOCK_KEY = MIGRATION_LOCK_KEY + 1


class Base(DeclarativeBase):
    pass


def postgres_url(database_url: str) -> URL:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use PostgreSQL")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use the Psycopg driver")
    if url.password is None:
        password = os.getenv("POSTGRES_PASSWORD")
        if not password:
            raise ValueError(
                "POSTGRES_PASSWORD must be set when DATABASE_URL has no password"
            )
        url = url.set(password=password)
    if len(url.password or "") < 16 or (url.password or "").startswith("replace-with-"):
        raise ValueError(
            "The PostgreSQL password must be a non-example value of at least 16 characters"
        )
    return url


def migration_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIRECTORY))
    return config


def migrate_database(engine: Engine) -> None:
    """Bring the schema to the latest migration before the application serves.

    Every migration runs in one transaction: PostgreSQL rolls the schema back
    as a whole if any step fails, rather than leaving it half upgraded.
    """
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(
        postgres_url(database_url),
        pool_pre_ping=True,
    )
    migrate_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
