"""Problem reports sent from the public form."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProblemReportCreate(BaseModel):
    message: str = Field(min_length=5, max_length=2000)
    page_path: str = Field(min_length=1, max_length=500)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(normalized) < 5:
            raise ValueError("Le message doit contenir au moins 5 caractères")
        return normalized

    @field_validator("page_path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        """Accept only local application paths, never network-path references."""
        if (
            not value.startswith("/")
            or value.startswith("//")
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("Le chemin de la page doit être un chemin local valide")
        return value


class ProblemReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    page_path: str
    created_at: datetime
