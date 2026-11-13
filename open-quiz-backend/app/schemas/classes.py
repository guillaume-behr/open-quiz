"""Grade levels, classes and student accounts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import reject_predictable_secret


class GradeLevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le niveau ne peut pas être vide")
        return normalized


class GradeLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class StudentResponse(BaseModel):
    id: int
    class_id: int
    account_id: int | None = None
    identifier: str
    display_name: str
    created_at: datetime


class StudentAccountCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_account_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom ne peut pas être vide")
        return normalized


class StudentAccountUpdate(BaseModel):
    identifier: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=10, max_length=256)
    is_active: bool = True

    @field_validator("identifier")
    @classmethod
    def normalize_account_identifier(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_account_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le nom ne peut pas être vide")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_student_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            reject_predictable_secret(
                "PASSWORD",
                value,
                minimum_unique_characters=5,
            )
        except ValueError:
            raise ValueError(
                "Le mot de passe élève doit être difficile à deviner "
                "et ne pas répéter un motif"
            ) from None
        return value


class StudentAccountResponse(BaseModel):
    id: int
    identifier: str
    display_name: str
    is_active: bool
    class_id: int | None
    class_name: str | None
    grade_level: str | None
    created_at: datetime


class StudentAccountCreatedResponse(StudentAccountResponse):
    generated_password: str


class StudentCredentialResponse(BaseModel):
    identifier: str
    display_name: str
    password: str | None


class StudentLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("identifier")
    @classmethod
    def normalize_login_identifier(cls, value: str) -> str:
        return value.strip().lower()


class StudentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret.
    student: StudentAccountResponse


class StudentClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grade_level: str = Field(min_length=1, max_length=80)

    @field_validator("name", "grade_level")
    @classmethod
    def normalize_class_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Ce champ ne peut pas être vide")
        return normalized


class StudentClassResponse(BaseModel):
    id: int
    name: str
    grade_level: str
    student_count: int
    completed_quiz_count: int
    latest_quiz_title: str | None
    latest_quiz_at: datetime | None
    students: list[StudentResponse]
    created_at: datetime


class ClassImportStudent(BaseModel):
    identifier: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        # min_length runs first: "   " passes it and normalizes to "".
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized


class ClassImportItem(StudentClassCreate):
    students: list[ClassImportStudent] = Field(max_length=500)


class ClassBatchImport(BaseModel):
    classes: list[ClassImportItem] = Field(min_length=1, max_length=100)


class ClassBatchImportResponse(BaseModel):
    class_count: int
    student_count: int
