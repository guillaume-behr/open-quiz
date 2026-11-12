"""The fixed vocabularies stored in the database and exchanged with clients.

Each is a StrEnum, so a member compares and serializes as its plain string:
stored rows and API payloads keep the same values, while a typo in the code
becomes an error instead of a comparison that silently matches nothing. The
database enforces the same values with CHECK constraints (migration 0004).
"""

from enum import StrEnum


class SessionStatus(StrEnum):
    """Where a quiz session or a makeup session stands."""

    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    FINISHED = "finished"


class QuizMode(StrEnum):
    EXAM = "exam"
    TRAINING = "training"


class AnswerMode(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    WRITTEN = "written"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


def allowed_values(column: str, vocabulary: type[StrEnum]) -> str:
    """A CHECK constraint condition admitting only the vocabulary's values."""
    values = ", ".join(f"'{member.value}'" for member in vocabulary)
    return f"{column} IN ({values})"
