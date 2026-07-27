from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    audience: Literal["professor", "admin"] | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    status: Literal["setup_required", "verification_required"]
    challenge_token: str
    secret: str | None = None
    provisioning_uri: str | None = None


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=1, max_length=2048)
    code: str = Field(pattern=r"^\d{6}$")


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class QuestionBankCreate(BaseModel):
    grade_level: str = Field(min_length=1, max_length=80)
    chapter: str = Field(min_length=1, max_length=160)

    @field_validator("grade_level", "chapter")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("This field cannot be empty")
        return normalized


class QuestionBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade_level: str
    chapter: str
    created_at: datetime
    question_count: int = 0


CodeLanguage = Literal[
    "javascript",
    "typescript",
    "python",
    "java",
    "csharp",
    "cpp",
    "markup",
    "css",
    "sql",
    "bash",
    "json",
]


class QuestionImportImage(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
    data_base64: str = Field(min_length=1, max_length=28_000_000)


class QuestionChoiceCreate(BaseModel):
    id: int | None = None
    label: str = Field(min_length=1, max_length=500)
    is_correct: bool = False
    points: float = Field(default=0, ge=-1000, le=1000)
    image: QuestionImportImage | None = None
    remove_image: bool = False
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("A choice cannot be empty")
        return normalized

    @field_validator("code_content")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return normalized if normalized.strip() else None

    @model_validator(mode="after")
    def validate_code(self) -> "QuestionChoiceCreate":
        if (self.code_language is None) != (self.code_content is None):
            raise ValueError("Code language and content must be provided together")
        return self


class QuestionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    difficulty: Literal["easy", "medium", "hard"]
    answer_mode: Literal["single", "multiple"]
    answer_mode_disclosed: bool = True
    correction_mode: Literal["automatic", "manual"]
    choices: list[QuestionChoiceCreate] = Field(min_length=2, max_length=12)
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("The question cannot be empty")
        return normalized

    @field_validator("code_content")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return None
        return normalized

    @model_validator(mode="after")
    def validate_correct_choices(self) -> "QuestionCreate":
        for choice in self.choices:
            if "points" not in choice.model_fields_set:
                choice.points = 1 if choice.is_correct else 0
        correct_count = sum(choice.is_correct for choice in self.choices)
        if self.answer_mode == "single" and correct_count > 1:
            raise ValueError("A single-choice question can have one correct answer")
        if self.correction_mode == "automatic":
            if correct_count == 0:
                raise ValueError("Automatic correction requires a correct answer")
            if self.answer_mode == "single" and correct_count != 1:
                raise ValueError(
                    "Automatic single-choice correction requires one correct answer"
                )
            if any(
                choice.points < 0
                for choice in self.choices
                if choice.is_correct
            ):
                raise ValueError("A correct answer cannot deduct points")
            if any(
                choice.points > 0
                for choice in self.choices
                if not choice.is_correct
            ):
                raise ValueError("An incorrect answer cannot award positive points")
        elif correct_count:
            raise ValueError("Manual correction cannot define correct answers")
        if (self.code_language is None) != (self.code_content is None):
            raise ValueError("Code language and content must be provided together")
        return self


class QuestionChoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    is_correct: bool
    points: float
    position: int
    has_image: bool
    code_language: str | None
    code_content: str | None


class QuestionResponse(BaseModel):
    id: int
    question_bank_id: int
    prompt: str
    difficulty: Literal["easy", "medium", "hard"]
    answer_mode: Literal["single", "multiple"]
    answer_mode_disclosed: bool
    correction_mode: Literal["automatic", "manual"]
    has_image: bool
    code_language: str | None
    code_content: str | None
    choices: list[QuestionChoiceResponse]
    created_at: datetime


class QuestionUpdate(QuestionCreate):
    remove_image: bool = False


class QuestionImportItem(QuestionCreate):
    image: QuestionImportImage | None = None


class QuestionBatchImport(BaseModel):
    version: Literal[1]
    question_bank: QuestionBankCreate
    questions: list[QuestionImportItem]


class QuestionBatchImportResponse(BaseModel):
    question_bank: QuestionBankResponse
    questions: list[QuestionResponse]
