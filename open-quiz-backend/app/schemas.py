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


class StudentCreate(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("display_name")
    @classmethod
    def normalize_student_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("This field cannot be empty")
        return normalized

    @field_validator("identifier")
    @classmethod
    def normalize_student_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = "".join(value.split()).lower()
        if not normalized:
            raise ValueError("The identifier cannot be empty")
        return normalized


class StudentResponse(BaseModel):
    id: int
    class_id: int
    identifier: str
    display_name: str
    created_at: datetime


class StudentClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grade_level: str = Field(min_length=1, max_length=80)

    @field_validator("name", "grade_level")
    @classmethod
    def normalize_class_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("This field cannot be empty")
        return normalized


class StudentClassResponse(BaseModel):
    id: int
    name: str
    grade_level: str
    student_count: int
    completed_quiz_count: int
    students: list[StudentResponse]
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
    label: str = Field(min_length=1, max_length=4000)
    is_correct: bool = False
    points: float = Field(default=0, ge=-1000, le=1000)
    image: QuestionImportImage | None = None
    remove_image: bool = False
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
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
    answer_mode: Literal["single", "multiple", "written"]
    answer_mode_disclosed: bool = True
    choices: list[QuestionChoiceCreate] = Field(min_length=1, max_length=12)
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
        if self.answer_mode in {"single", "written"} and correct_count > 1:
            raise ValueError("A single-choice question can have one correct answer")
        if self.answer_mode != "written" and len(self.choices) < 2:
            raise ValueError("A question requires at least two choices")
        if self.answer_mode == "written" and len(self.choices) != 1:
            raise ValueError("A written answer requires one response")
        if correct_count == 0:
            raise ValueError("A question requires a correct answer")
        if self.answer_mode in {"single", "written"} and correct_count != 1:
            raise ValueError("A single answer requires one correct answer")
        if any(
            choice.points < 0 for choice in self.choices if choice.is_correct
        ):
            raise ValueError("A correct answer cannot deduct points")
        if any(
            choice.points > 0
            for choice in self.choices
            if not choice.is_correct
        ):
            raise ValueError("An incorrect answer cannot award positive points")
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
    answer_mode: Literal["single", "multiple", "written"]
    answer_mode_disclosed: bool
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


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question_bank_ids: list[int] = Field(min_length=1, max_length=100)
    question_count: int = Field(ge=1, le=200)
    duration_seconds: int = Field(default=1800, ge=60, le=28800)
    allow_previous_questions: bool = False
    easy_percentage: int = Field(ge=0, le=100)
    medium_percentage: int = Field(ge=0, le=100)
    hard_percentage: int = Field(ge=0, le=100)

    @field_validator("title")
    @classmethod
    def normalize_quiz_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("The quiz title cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_distribution(self) -> "QuizCreate":
        if (
            self.easy_percentage
            + self.medium_percentage
            + self.hard_percentage
            != 100
        ):
            raise ValueError("Difficulty percentages must total 100")
        if len(set(self.question_bank_ids)) != len(self.question_bank_ids):
            raise ValueError("Question banks must be unique")
        return self


class QuizBankSummary(BaseModel):
    id: int
    grade_level: str
    chapter: str
    question_count: int


class QuizResponse(BaseModel):
    id: int
    title: str
    question_count: int
    duration_seconds: int
    allow_previous_questions: bool
    easy_percentage: int
    medium_percentage: int
    hard_percentage: int
    question_banks: list[QuizBankSummary]
    created_at: datetime


class QuizLaunch(BaseModel):
    class_id: int = Field(gt=0)


class QuizParticipantResponse(BaseModel):
    id: int
    student_identifier: str
    student_display_name: str | None
    answered_count: int = 0
    score: float = 0
    violation_count: int = 0
    last_violation_type: str | None = None
    last_violation_at: datetime | None = None
    joined_at: datetime


class QuizSessionResponse(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    class_id: int | None
    class_name: str
    join_code: str
    status: Literal["waiting", "in_progress", "finished"]
    participant_count: int
    participants: list[QuizParticipantResponse]
    current_question_number: int | None
    total_questions: int
    current_submission_count: int
    created_at: datetime
    started_at: datetime | None
    ends_at: datetime | None


class StudentQuizSessionResponse(BaseModel):
    quiz_title: str
    class_name: str
    join_code: str
    status: Literal["waiting", "in_progress", "finished"]
    ends_at: datetime | None


class StudentQuizChoiceResponse(BaseModel):
    id: int
    label: str
    position: int
    has_image: bool
    code_language: str | None
    code_content: str | None


class StudentQuizQuestionResponse(BaseModel):
    id: int
    prompt: str
    difficulty: Literal["easy", "medium", "hard"]
    answer_mode: Literal["single", "multiple", "written"]
    answer_mode_disclosed: bool
    has_image: bool
    code_language: str | None
    code_content: str | None
    choices: list[StudentQuizChoiceResponse]


class StudentQuizStateResponse(StudentQuizSessionResponse):
    question_number: int | None
    total_questions: int
    has_answered: bool
    answered_count: int
    allow_previous_questions: bool
    selected_choice_ids: list[int] | None = None
    written_answer: str | None = None
    question: StudentQuizQuestionResponse | None


class StudentQuizJoinResponse(StudentQuizStateResponse):
    participant_token: str


class StudentQuizAnswer(BaseModel):
    selected_choice_ids: list[int] | None = Field(
        default=None, max_length=12
    )
    written_answer: str | None = Field(default=None, max_length=4000)


class StudentQuizNavigation(BaseModel):
    question_number: int = Field(ge=1)


class StudentQuizViolation(BaseModel):
    event_type: Literal[
        "fullscreen_exit",
        "pointer_exit",
        "window_blur",
        "page_hidden",
    ]


class QuizJoin(BaseModel):
    join_code: str = Field(min_length=4, max_length=8)
    student_identifier: str = Field(min_length=1, max_length=80)

    @field_validator("join_code")
    @classmethod
    def normalize_join_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("student_identifier")
    @classmethod
    def normalize_student_identifier(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("The student identifier cannot be empty")
        return normalized
