import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


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


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(
        postgres_url(database_url),
        pool_pre_ping=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
