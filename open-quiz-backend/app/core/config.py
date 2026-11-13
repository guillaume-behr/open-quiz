import os
import re
import tomllib
from dataclasses import Field, dataclass, fields
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

from dotenv import load_dotenv
from pydantic import Field as PydanticField
from pydantic import create_model
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.audit import audit_event

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

# The image installs dependencies without the project itself, so there is no
# package metadata to read: pyproject.toml, copied next to the app package, is
# the single source of the backend version.
VERSION: str = tomllib.loads((BASE_DIR / "pyproject.toml").read_text())["project"][
    "version"
]


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


# Host names the internal network reaches the API by: the Compose health
# check, and the frontend proxy when something calls it by its service name.
INTERNAL_HOSTS = ("127.0.0.1", "localhost", "open-quiz-backend", "open-quiz-frontend")
# A host name, or one with a leading wildcard label such as *.example.com.
TRUSTED_HOST_PATTERN = re.compile(
    r"^(?:\*\.)?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$"
)

BOUNDS = "bounds"


def bounded(default: int, minimum: int, maximum: int | None = None) -> Any:
    """A numeric setting with its accepted range, declared next to its field."""
    return dataclass_field(default=default, metadata={BOUNDS: (minimum, maximum)})


def require_secret(name: str, value: str) -> None:
    """A long, non-example, unpredictable key."""
    if len(value) < 32:
        raise ValueError(f"{name} must contain at least 32 characters")
    if value.startswith("replace-with-"):
        raise ValueError(f"{name} is still set to its example value")
    reject_predictable_secret(name, value, minimum_unique_characters=10)


def check_bounds(settings: Any) -> None:
    """Refuse any bounded setting outside its range, naming its variable."""
    for setting in fields(settings):
        if BOUNDS not in setting.metadata:
            continue
        minimum, maximum = setting.metadata[BOUNDS]
        value = getattr(settings, setting.name)
        name = environment_variable(setting)
        if maximum is None:
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        elif not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    totp_encryption_key: str
    student_credential_encryption_key: str
    admin_username: str
    admin_password: str
    frontend_origin: str
    access_token_minutes: int = bounded(15, 1, 30)
    refresh_token_days: int = bounded(7, 1, 30)
    # A student session has no refresh step, so it must outlast a lesson:
    # below two hours students would be signed out mid-class.
    student_access_token_hours: int = bounded(2, 2, 12)
    login_attempts: int = bounded(10, 3, 50)
    login_window_seconds: int = bounded(900, 60)
    two_factor_daily_attempts: int = bounded(30, 5, 500)
    two_factor_browser_trust: bool = True
    global_login_attempts: int = bounded(2000, 50, 100000)
    global_login_window_seconds: int = bounded(60, 10, 3600)
    quiz_join_attempts: int = bounded(60, 5, 500)
    quiz_participant_attempts: int = bounded(900, 30, 5000)
    quiz_violation_attempts: int = bounded(60, 5, 500)
    quiz_rate_window_seconds: int = bounded(60, 10, 3600)
    quiz_result_retention_days: int = bounded(365, 1, 3650)
    training_result_retention_days: int = bounded(365, 1, 3650)
    abandoned_session_retention_days: int = bounded(7, 1, 90)
    class_import_attempts: int = bounded(30, 1, 1000)
    class_import_window_seconds: int = bounded(900, 60, 86400)
    problem_report_attempts: int = bounded(60, 1, 5000)
    problem_report_window_seconds: int = bounded(900, 60, 86400)
    problem_report_retention_days: int = bounded(90, 1, 365)
    max_request_body_bytes: int = bounded(65536, 1024, 1048576)
    # Connections each worker's requests may hold at once: the pool keeps
    # DATABASE_POOL_SIZE open and opens up to DATABASE_MAX_OVERFLOW more under
    # load. A request that waits longer than the timeout for one answers 503.
    database_pool_size: int = bounded(5, 1, 100)
    database_max_overflow: int = bounded(10, 0, 100)
    database_pool_timeout_seconds: int = bounded(10, 1, 60)
    # Extra Host names the API answers to in production, separated by commas,
    # for an API published under another name than FRONTEND_ORIGIN.
    trusted_hosts: str = ""
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

    @property
    def allowed_hosts(self) -> list[str]:
        """The Host names a production API answers to."""
        extra = [name.strip() for name in self.trusted_hosts.split(",")]
        frontend_host = urlparse(self.frontend_origin).hostname or ""
        return [frontend_host, *INTERNAL_HOSTS, *(name for name in extra if name)]

    def __post_init__(self) -> None:
        self._validate_admin_username()
        self._validate_secrets()
        self._validate_admin_password()
        check_bounds(self)
        self._validate_trusted_hosts()
        origin = self._validate_frontend_origin()
        self._validate_deployment(origin)

    def _validate_admin_username(self) -> None:
        if not 1 <= len(self.admin_username) <= 80:
            raise ValueError("ADMIN_USERNAME must contain between 1 and 80 characters")
        # The characters a teacher's username may use (UserCreate): sign-in
        # strips spaces, so an administrator stored with one could never sign
        # in.
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", self.admin_username):
            raise ValueError(
                "ADMIN_USERNAME may only contain letters, digits, '.', '_' and '-'"
            )

    def _validate_secrets(self) -> None:
        require_secret("JWT_SECRET", self.jwt_secret)
        require_secret("TOTP_ENCRYPTION_KEY", self.totp_encryption_key)
        if self.jwt_secret == self.totp_encryption_key:
            raise ValueError("JWT_SECRET and TOTP_ENCRYPTION_KEY must be distinct")
        require_secret(
            "STUDENT_CREDENTIAL_ENCRYPTION_KEY", self.student_credential_encryption_key
        )
        if self.student_credential_encryption_key in {
            self.jwt_secret,
            self.totp_encryption_key,
        }:
            raise ValueError(
                "STUDENT_CREDENTIAL_ENCRYPTION_KEY must be distinct from other secrets"
            )

    def _validate_admin_password(self) -> None:
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

    def _validate_trusted_hosts(self) -> None:
        for name in self.trusted_hosts.split(","):
            if name.strip() and not TRUSTED_HOST_PATTERN.match(name.strip()):
                raise ValueError(
                    "TRUSTED_HOSTS must list host names separated by commas"
                )

    def _validate_frontend_origin(self) -> ParseResult:
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
        return origin

    def _validate_deployment(self, origin: ParseResult) -> None:
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


# Every Settings field reads the environment variable of the same name in
# upper case, except these.
ENVIRONMENT_VARIABLES = {"environment": "APP_ENV"}
# Fields the environment must set: get_settings() refuses to start without
# them, even where Settings has a default.
REQUIRED_FIELDS = {
    "database_url",
    "jwt_secret",
    "totp_encryption_key",
    "student_credential_encryption_key",
    "admin_username",
    "admin_password",
    "environment",
}
# Fields Settings requires but the environment may leave out.
ENVIRONMENT_DEFAULTS = {"frontend_origin": "http://localhost:5173"}


class EnvironmentSettings(BaseSettings):
    # Variable names are matched exactly, as os.getenv() did.
    model_config = SettingsConfigDict(case_sensitive=True)


def environment_variable(field: Field[Any]) -> str:
    return ENVIRONMENT_VARIABLES.get(field.name, field.name.upper())


def environment_model() -> type[BaseSettings]:
    """A pydantic-settings model mirroring Settings, read from the environment.

    It parses each variable into the field's type, so a malformed value fails
    with the variable's name and the expected type instead of a bare int()
    error. Required fields default to an empty string here, so that
    get_settings() reports them as missing.
    """
    definitions: dict[str, Any] = {}
    for field in fields(Settings):
        if field.name in REQUIRED_FIELDS:
            default: Any = ""
        elif field.name in ENVIRONMENT_DEFAULTS:
            default = ENVIRONMENT_DEFAULTS[field.name]
        else:
            default = field.default
        definitions[field.name] = (
            field.type,
            PydanticField(default, validation_alias=environment_variable(field)),
        )
    return create_model(
        "EnvironmentSettings", __base__=EnvironmentSettings, **definitions
    )


def get_settings() -> Settings:
    secure_private_file(ENV_FILE)
    load_dotenv(ENV_FILE)
    values = environment_model()().model_dump()
    for field in fields(Settings):
        if field.name in REQUIRED_FIELDS and not values[field.name]:
            raise RuntimeError(
                f"{environment_variable(field)} must be set in {ENV_FILE}"
            )
    return Settings(**values)


PUBLIC_INFORMATION_VARIABLES = (
    ("LEGAL_HOST_NAME", "legal_host_name"),
    ("LEGAL_HOST_ADDRESS", "legal_host_address"),
    # The legal notice flags the host as incomplete without its phone number,
    # so the startup warning has to consider it required too.
    ("LEGAL_HOST_PHONE", "legal_host_phone"),
    ("PRIVACY_CONTROLLER_NAME", "privacy_controller_name"),
    ("PRIVACY_CONTROLLER_CONTACT", "privacy_controller_contact"),
    ("PRIVACY_LEGAL_BASIS", "privacy_legal_basis"),
    ("PRIVACY_RECIPIENTS", "privacy_recipients"),
    ("PRIVACY_TEACHER_DATA_RETENTION", "privacy_teacher_data_retention"),
    ("PRIVACY_STUDENT_DATA_RETENTION", "privacy_student_data_retention"),
    ("PRIVACY_SECURITY_LOG_RETENTION", "privacy_security_log_retention"),
)


def warn_missing_public_information(settings: Settings) -> list[str]:
    """Name the legal mentions a production instance still has to publish.

    An empty value never blocks the start: an instance may legitimately run
    before its operator has settled who the controller is. It must not do so
    silently, because the public pages then carry no identity to address a
    rights request to.
    """
    if settings.environment != "production":
        return []
    missing = [
        name
        for name, attribute in PUBLIC_INFORMATION_VARIABLES
        if not getattr(settings, attribute).strip()
    ]
    if missing:
        audit_event("security.public_information_incomplete", variables=missing)
    return missing
