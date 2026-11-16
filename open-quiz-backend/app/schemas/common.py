"""Constants and validators shared by the request schemas."""

import re

from app.core.config import reject_predictable_secret

MAX_QUESTIONS_PER_BANK = 500


LEADING_BLANK_LINES = re.compile(r"\A(?:[^\S\n]*\n)+")


def trim_text_block(value: str) -> str:
    """Trim text the way it is stored, keeping pasted code in shape.

    Text on one line is stripped as usual. Text on several lines loses the
    blank lines before it and the spaces after it, but keeps the indentation
    of its first line.
    """
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    text = LEADING_BLANK_LINES.sub("", normalized)
    return text if "\n" in text else text.strip()


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
