import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def secure_private_file(path: Path) -> None:
    """Restrict a local secret file to its owner on POSIX systems."""
    if os.name != "posix" or not path.exists():
        return
    try:
        path.chmod(0o600)
    except OSError as error:
        raise RuntimeError(f"Unable to secure private file {path}") from error


def write_private_file(path: Path, content: str) -> None:
    """Write a secret file that is never readable by anyone else.

    Creating the file first and restricting it afterwards leaves a window in
    which the process umask decides who may read it, which for a default 022
    means every local account.
    """
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as private_file:
        private_file.write(content)
    secure_private_file(path)


def reject_predictable_secret(
    name: str,
    value: str,
    *,
    minimum_unique_characters: int,
) -> None:
    if len(set(value)) < minimum_unique_characters:
        raise ValueError(f"{name} must contain more character variety")
    for pattern_length in range(1, min(64, len(value) // 2) + 1):
        pattern = value[:pattern_length]
        repeats, remainder = divmod(len(value), pattern_length)
        if remainder == 0 and pattern * repeats == value:
            raise ValueError(f"{name} must not be a repeated pattern")


def validate_optional_public_url(name: str, value: str, environment: str) -> None:
    if not value:
        return
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{name} must not contain control characters")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{name} must not contain credentials")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError(f"{name} contains an invalid port") from error
    if environment == "production" and parsed.scheme != "https":
        raise ValueError(f"Production {name} must use HTTPS")


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    totp_encryption_key: str
    student_credential_encryption_key: str
    admin_username: str
    admin_password: str
    frontend_origin: str
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    login_attempts: int = 10
    login_window_seconds: int = 900
    global_login_attempts: int = 2000
    global_login_window_seconds: int = 60
    quiz_join_attempts: int = 60
    quiz_participant_attempts: int = 900
    quiz_violation_attempts: int = 60
    quiz_rate_window_seconds: int = 60
    quiz_result_retention_days: int = 365
    training_result_retention_days: int = 365
    abandoned_session_retention_days: int = 7
    problem_report_attempts: int = 60
    problem_report_window_seconds: int = 900
    problem_report_retention_days: int = 90
    max_request_body_bytes: int = 65536
    environment: str = "development"
    legal_host_name: str = ""
    legal_host_address: str = ""
    legal_host_phone: str = ""
    privacy_controller_name: str = ""
    privacy_controller_contact: str = ""
    privacy_dpo_contact: str = ""
    privacy_legal_basis: str = ""
    privacy_recipients: str = ""
    privacy_teacher_data_retention: str = ""
    privacy_student_data_retention: str = ""
    privacy_security_log_retention: str = ""
    accessibility_contact: str = ""
    accessibility_scheme_url: str = ""
    accessibility_action_plan_url: str = ""

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    def __post_init__(self) -> None:
        if not 1 <= len(self.admin_username) <= 80:
            raise ValueError("ADMIN_USERNAME must contain between 1 and 80 characters")
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        if self.jwt_secret.startswith("replace-with-"):
            raise ValueError("JWT_SECRET is still set to its example value")
        reject_predictable_secret(
            "JWT_SECRET",
            self.jwt_secret,
            minimum_unique_characters=10,
        )
        if len(self.totp_encryption_key) < 32:
            raise ValueError("TOTP_ENCRYPTION_KEY must contain at least 32 characters")
        if self.totp_encryption_key.startswith("replace-with-"):
            raise ValueError("TOTP_ENCRYPTION_KEY is still set to its example value")
        reject_predictable_secret(
            "TOTP_ENCRYPTION_KEY",
            self.totp_encryption_key,
            minimum_unique_characters=10,
        )
        if self.jwt_secret == self.totp_encryption_key:
            raise ValueError("JWT_SECRET and TOTP_ENCRYPTION_KEY must be distinct")
        if len(self.student_credential_encryption_key) < 32:
            raise ValueError(
                "STUDENT_CREDENTIAL_ENCRYPTION_KEY must contain at least 32 characters"
            )
        if self.student_credential_encryption_key.startswith("replace-with-"):
            raise ValueError(
                "STUDENT_CREDENTIAL_ENCRYPTION_KEY is still set to its example value"
            )
        reject_predictable_secret(
            "STUDENT_CREDENTIAL_ENCRYPTION_KEY",
            self.student_credential_encryption_key,
            minimum_unique_characters=10,
        )
        if self.student_credential_encryption_key in {
            self.jwt_secret,
            self.totp_encryption_key,
        }:
            raise ValueError(
                "STUDENT_CREDENTIAL_ENCRYPTION_KEY must be distinct from other secrets"
            )
        if len(self.admin_password) < 16:
            raise ValueError("ADMIN_PASSWORD must contain at least 16 characters")
        if len(self.admin_password) > 256:
            raise ValueError("ADMIN_PASSWORD must contain at most 256 characters")
        if self.admin_password.startswith("replace-with-"):
            raise ValueError("ADMIN_PASSWORD is still set to its example value")
        reject_predictable_secret(
            "ADMIN_PASSWORD",
            self.admin_password,
            minimum_unique_characters=6,
        )
        if not 1 <= self.access_token_minutes <= 30:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 30")
        if not 1 <= self.refresh_token_days <= 30:
            raise ValueError("REFRESH_TOKEN_DAYS must be between 1 and 30")
        if not 3 <= self.login_attempts <= 50:
            raise ValueError("LOGIN_ATTEMPTS must be between 3 and 50")
        if self.login_window_seconds < 60:
            raise ValueError("LOGIN_WINDOW_SECONDS must be at least 60")
        if not 50 <= self.global_login_attempts <= 100000:
            raise ValueError("GLOBAL_LOGIN_ATTEMPTS must be between 50 and 100000")
        if not 10 <= self.global_login_window_seconds <= 3600:
            raise ValueError("GLOBAL_LOGIN_WINDOW_SECONDS must be between 10 and 3600")
        if not 5 <= self.quiz_join_attempts <= 500:
            raise ValueError("QUIZ_JOIN_ATTEMPTS must be between 5 and 500")
        if not 30 <= self.quiz_participant_attempts <= 5000:
            raise ValueError("QUIZ_PARTICIPANT_ATTEMPTS must be between 30 and 5000")
        if not 5 <= self.quiz_violation_attempts <= 500:
            raise ValueError("QUIZ_VIOLATION_ATTEMPTS must be between 5 and 500")
        if not 10 <= self.quiz_rate_window_seconds <= 3600:
            raise ValueError("QUIZ_RATE_WINDOW_SECONDS must be between 10 and 3600")
        if not 1 <= self.quiz_result_retention_days <= 3650:
            raise ValueError("QUIZ_RESULT_RETENTION_DAYS must be between 1 and 3650")
        if not 1 <= self.training_result_retention_days <= 3650:
            raise ValueError(
                "TRAINING_RESULT_RETENTION_DAYS must be between 1 and 3650"
            )
        if not 1 <= self.abandoned_session_retention_days <= 90:
            raise ValueError(
                "ABANDONED_SESSION_RETENTION_DAYS must be between 1 and 90"
            )
        if not 1 <= self.problem_report_attempts <= 5000:
            raise ValueError("PROBLEM_REPORT_ATTEMPTS must be between 1 and 5000")
        if not 60 <= self.problem_report_window_seconds <= 86400:
            raise ValueError(
                "PROBLEM_REPORT_WINDOW_SECONDS must be between 60 and 86400"
            )
        if not 1 <= self.problem_report_retention_days <= 365:
            raise ValueError("PROBLEM_REPORT_RETENTION_DAYS must be between 1 and 365")
        if not 1024 <= self.max_request_body_bytes <= 1048576:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be between 1024 and 1048576")

        origin = urlparse(self.frontend_origin)
        if origin.scheme not in {"http", "https"} or not origin.netloc:
            raise ValueError("FRONTEND_ORIGIN must be an HTTP(S) origin")
        if origin.username or origin.password:
            raise ValueError("FRONTEND_ORIGIN must not contain credentials")
        try:
            _ = origin.port
        except ValueError as error:
            raise ValueError("FRONTEND_ORIGIN contains an invalid port") from error
        if origin.path or origin.params or origin.query or origin.fragment:
            raise ValueError(
                "FRONTEND_ORIGIN must not contain a trailing slash, path, "
                "parameters, query, or fragment"
            )
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        database = urlparse(self.database_url)
        if database.scheme not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("DATABASE_URL must use PostgreSQL")
        if self.environment == "production" and origin.scheme != "https":
            raise ValueError("Production FRONTEND_ORIGIN must use HTTPS")
        validate_optional_public_url(
            "ACCESSIBILITY_SCHEME_URL",
            self.accessibility_scheme_url,
            self.environment,
        )
        validate_optional_public_url(
            "ACCESSIBILITY_ACTION_PLAN_URL",
            self.accessibility_action_plan_url,
            self.environment,
        )


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set in {ENV_FILE}")
    return value


def get_settings() -> Settings:
    secure_private_file(ENV_FILE)
    load_dotenv(ENV_FILE)
    return Settings(
        database_url=required_environment("DATABASE_URL"),
        jwt_secret=required_environment("JWT_SECRET"),
        totp_encryption_key=required_environment("TOTP_ENCRYPTION_KEY"),
        student_credential_encryption_key=required_environment(
            "STUDENT_CREDENTIAL_ENCRYPTION_KEY"
        ),
        admin_username=required_environment("ADMIN_USERNAME"),
        admin_password=required_environment("ADMIN_PASSWORD"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")),
        login_attempts=int(os.getenv("LOGIN_ATTEMPTS", "10")),
        login_window_seconds=int(os.getenv("LOGIN_WINDOW_SECONDS", "900")),
        global_login_attempts=int(os.getenv("GLOBAL_LOGIN_ATTEMPTS", "2000")),
        global_login_window_seconds=int(os.getenv("GLOBAL_LOGIN_WINDOW_SECONDS", "60")),
        quiz_join_attempts=int(os.getenv("QUIZ_JOIN_ATTEMPTS", "60")),
        quiz_participant_attempts=int(os.getenv("QUIZ_PARTICIPANT_ATTEMPTS", "900")),
        quiz_violation_attempts=int(os.getenv("QUIZ_VIOLATION_ATTEMPTS", "60")),
        quiz_rate_window_seconds=int(os.getenv("QUIZ_RATE_WINDOW_SECONDS", "60")),
        quiz_result_retention_days=int(os.getenv("QUIZ_RESULT_RETENTION_DAYS", "365")),
        training_result_retention_days=int(
            os.getenv("TRAINING_RESULT_RETENTION_DAYS", "365")
        ),
        abandoned_session_retention_days=int(
            os.getenv("ABANDONED_SESSION_RETENTION_DAYS", "7")
        ),
        problem_report_attempts=int(os.getenv("PROBLEM_REPORT_ATTEMPTS", "60")),
        problem_report_window_seconds=int(
            os.getenv("PROBLEM_REPORT_WINDOW_SECONDS", "900")
        ),
        problem_report_retention_days=int(
            os.getenv("PROBLEM_REPORT_RETENTION_DAYS", "90")
        ),
        max_request_body_bytes=int(os.getenv("MAX_REQUEST_BODY_BYTES", "65536")),
        environment=required_environment("APP_ENV"),
        legal_host_name=os.getenv("LEGAL_HOST_NAME", ""),
        legal_host_address=os.getenv("LEGAL_HOST_ADDRESS", ""),
        legal_host_phone=os.getenv("LEGAL_HOST_PHONE", ""),
        privacy_controller_name=os.getenv("PRIVACY_CONTROLLER_NAME", ""),
        privacy_controller_contact=os.getenv("PRIVACY_CONTROLLER_CONTACT", ""),
        privacy_dpo_contact=os.getenv("PRIVACY_DPO_CONTACT", ""),
        privacy_legal_basis=os.getenv("PRIVACY_LEGAL_BASIS", ""),
        privacy_recipients=os.getenv("PRIVACY_RECIPIENTS", ""),
        privacy_teacher_data_retention=os.getenv("PRIVACY_TEACHER_DATA_RETENTION", ""),
        privacy_student_data_retention=os.getenv("PRIVACY_STUDENT_DATA_RETENTION", ""),
        privacy_security_log_retention=os.getenv("PRIVACY_SECURITY_LOG_RETENTION", ""),
        accessibility_contact=os.getenv("ACCESSIBILITY_CONTACT", ""),
        accessibility_scheme_url=os.getenv("ACCESSIBILITY_SCHEME_URL", ""),
        accessibility_action_plan_url=os.getenv("ACCESSIBILITY_ACTION_PLAN_URL", ""),
    )
