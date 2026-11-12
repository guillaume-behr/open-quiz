"""Test environment defaults required while the application module is imported."""

import os

TEST_ENVIRONMENT = {
    "APP_ENV": "test",
    "JWT_SECRET": "test-secret-that-is-at-least-32-bytes-long",
    "TOTP_ENCRYPTION_KEY": "test-totp-key-that-is-at-least-32-bytes",
    "STUDENT_CREDENTIAL_ENCRYPTION_KEY": (
        "test-student-credential-key-with-enough-variety-4567"
    ),
    "ADMIN_USERNAME": "root-admin",
    "ADMIN_PASSWORD": "a-strong-test-password",
}

for name, value in TEST_ENVIRONMENT.items():
    os.environ.setdefault(name, value)
# The local test database of CONTRIBUTING.md, unless TEST_DATABASE_URL names
# another. The application reads DATABASE_URL at import: it gets the same.
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://open_quiz_test:open-quiz-test-password@127.0.0.1:5432/open_quiz_test",
)
os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])

import pytest  # noqa: E402
from pwdlib import PasswordHash  # noqa: E402
from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app import maintenance, security  # noqa: E402
from app.database import postgres_url  # noqa: E402

from support import PREPARED_TEST_SCHEMAS, TEST_DATABASE_URL, TEST_ENGINES  # noqa: E402

# Password hashing at the production cost dominates many tests' runtime. The
# hashes keep the Argon2id format; only the work factors are the minimum.
security.password_hash = PasswordHash(
    (Argon2Hasher(time_cost=1, memory_cost=8 * 1024, parallelism=1),)
)

# Tests finish expired sessions explicitly with expire_due_sessions(): a
# background tick firing in the middle of a test would make it racy.
maintenance.SESSION_EXPIRY_INTERVAL_SECONDS = 3600


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_schemas():
    yield
    if not PREPARED_TEST_SCHEMAS:
        return
    engine = create_engine(postgres_url(TEST_DATABASE_URL))
    try:
        for schema in PREPARED_TEST_SCHEMAS:
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def dispose_test_engines():
    yield
    while TEST_ENGINES:
        TEST_ENGINES.pop().dispose()
