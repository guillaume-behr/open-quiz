import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    admin_username: str
    admin_password: str
    frontend_origin: str
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    login_attempts: int = 5
    login_window_seconds: int = 900
    environment: str = "development"

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    def __post_init__(self) -> None:
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        if self.jwt_secret.startswith("replace-with-"):
            raise ValueError("JWT_SECRET is still set to its example value")
        if len(self.admin_password) < 16:
            raise ValueError("ADMIN_PASSWORD must contain at least 16 characters")
        if self.admin_password.startswith("replace-with-"):
            raise ValueError("ADMIN_PASSWORD is still set to its example value")
        if not 1 <= self.access_token_minutes <= 30:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 30")
        if not 1 <= self.refresh_token_days <= 30:
            raise ValueError("REFRESH_TOKEN_DAYS must be between 1 and 30")
        if not 3 <= self.login_attempts <= 20:
            raise ValueError("LOGIN_ATTEMPTS must be between 3 and 20")
        if self.login_window_seconds < 60:
            raise ValueError("LOGIN_WINDOW_SECONDS must be at least 60")

        origin = urlparse(self.frontend_origin)
        if origin.scheme not in {"http", "https"} or not origin.netloc:
            raise ValueError("FRONTEND_ORIGIN must be an HTTP(S) origin")
        if origin.path not in {"", "/"} or origin.query or origin.fragment:
            raise ValueError(
                "FRONTEND_ORIGIN must not contain a path, query, or fragment"
            )
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if self.environment == "production" and origin.scheme != "https":
            raise ValueError("Production FRONTEND_ORIGIN must use HTTPS")


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set in {BASE_DIR / '.env'}")
    return value


def get_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'open-quiz.db').as_posix()}"
        ),
        jwt_secret=required_environment("JWT_SECRET"),
        admin_username=required_environment("ADMIN_USERNAME"),
        admin_password=required_environment("ADMIN_PASSWORD"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")),
        login_attempts=int(os.getenv("LOGIN_ATTEMPTS", "5")),
        login_window_seconds=int(os.getenv("LOGIN_WINDOW_SECONDS", "900")),
        environment=os.getenv("APP_ENV", "development"),
    )
