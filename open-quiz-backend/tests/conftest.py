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
