"""Constants and validators shared by the request schemas."""

from app.core.config import reject_predictable_secret

MAX_QUESTIONS_PER_BANK = 500


def normalize_optional_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized if normalized.strip() else None


def validate_teacher_password(value: str) -> str:
    try:
        reject_predictable_secret(
            "PASSWORD",
            value,
            minimum_unique_characters=6,
        )
    except ValueError:
        raise ValueError(
            "Le mot de passe doit être difficile à deviner et ne pas répéter un motif"
        ) from None
    return value
