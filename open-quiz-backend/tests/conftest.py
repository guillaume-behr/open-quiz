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

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app.database import postgres_url  # noqa: E402

from support import PREPARED_TEST_SCHEMAS, TEST_DATABASE_URL  # noqa: E402


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
