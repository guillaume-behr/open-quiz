from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import reject_predictable_secret

MAX_QUESTIONS_PER_BANK = 500


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


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    audience: Literal["professor", "admin"] | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_proof: str
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
    password: str = Field(min_length=16, max_length=256)

    _validate_password = field_validator("password")(validate_teacher_password)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserCredentialReset(BaseModel):
    password: str = Field(min_length=16, max_length=256)
    reset_two_factor: bool = True

    _validate_password = field_validator("password")(validate_teacher_password)


class ProblemReportCreate(BaseModel):
    message: str = Field(min_length=5, max_length=2000)
    page_path: str = Field(min_length=1, max_length=500, pattern=r"^/")

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(normalized) < 5:
            raise ValueError("Le message doit contenir au moins 5 caractères")
        return normalized


class ProblemReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    page_path: str
    created_at: datetime


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
    identifier: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)

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


class StudentAccountUpdate(BaseModel):
    identifier: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=256)
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


class StudentAccountResponse(BaseModel):
    id: int
    identifier: str
    display_name: str
    is_active: bool
    class_id: int | None
    class_name: str | None
    created_at: datetime


class StudentLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("identifier")
    @classmethod
    def normalize_login_identifier(cls, value: str) -> str:
        return value.strip().lower()


class StudentLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
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


class QuestionBankCreate(BaseModel):
    grade_level: str = Field(min_length=1, max_length=80)
    chapter: str = Field(min_length=1, max_length=160)

    @field_validator("grade_level", "chapter")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Ce champ ne peut pas être vide")
        return normalized


class QuestionBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade_level: str
    chapter: str
    created_at: datetime
    question_count: int = 0
    easy_question_count: int = 0
    medium_question_count: int = 0
    hard_question_count: int = 0


class TrainingQuestionBankSelection(BaseModel):
    question_bank_ids: list[int] = Field(max_length=100)

    @field_validator("question_bank_ids")
    @classmethod
    def validate_unique_question_banks(cls, value: list[int]) -> list[int]:
        if any(question_bank_id < 1 for question_bank_id in value):
            raise ValueError("Les banques de questions sélectionnées sont invalides")
        if len(value) != len(set(value)):
            raise ValueError(
                "Chaque banque de questions ne peut être sélectionnée qu’une fois"
            )
        return value


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
    image: QuestionImportImage | None = None
    remove_image: bool = False
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("Une proposition ne peut pas être vide")
        return normalized

    @field_validator("code_content")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return normalized if normalized.strip() else None

    @model_validator(mode="after")
    def validate_code(self) -> QuestionChoiceCreate:
        if (self.code_language is None) != (self.code_content is None):
            raise ValueError(
                "Le langage et le contenu du code doivent être renseignés ensemble"
            )
        return self


class QuestionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    difficulty: Literal["easy", "medium", "hard"]
    answer_mode: Literal["single", "multiple", "written"]
    answer_mode_disclosed: bool = True
    response_language: CodeLanguage | None = None
    choices: list[QuestionChoiceCreate] = Field(min_length=1, max_length=12)
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("La question ne peut pas être vide")
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
    def validate_correct_choices(self) -> QuestionCreate:
        correct_count = sum(choice.is_correct for choice in self.choices)
        if self.answer_mode in {"single", "written"} and correct_count > 1:
            raise ValueError(
                "Une question à choix unique ne peut avoir qu’une bonne réponse"
            )
        if self.answer_mode != "written" and len(self.choices) < 2:
            raise ValueError("Une question nécessite au moins deux propositions")
        if self.answer_mode == "written" and len(self.choices) != 1:
            raise ValueError(
                "Une question rédactionnelle nécessite une réponse attendue"
            )
        if self.answer_mode != "written" and self.response_language is not None:
            raise ValueError(
                "Un langage de réponse est réservé aux questions rédactionnelles"
            )
        if correct_count == 0:
            raise ValueError("Une question nécessite au moins une bonne réponse")
        if self.answer_mode in {"single", "written"} and correct_count != 1:
            raise ValueError(
                "Une question à choix unique nécessite une seule bonne réponse"
            )
        if (self.code_language is None) != (self.code_content is None):
            raise ValueError(
                "Le langage et le contenu du code doivent être renseignés ensemble"
            )
        return self


class QuestionChoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    is_correct: bool
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
    response_language: str | None
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
    questions: list[QuestionImportItem] = Field(max_length=MAX_QUESTIONS_PER_BANK)


class QuestionBatchImportResponse(BaseModel):
    question_bank: QuestionBankResponse
    questions: list[QuestionResponse]


class QuizCreate(BaseModel):
    mode: Literal["exam"] = "exam"
    title: str = Field(min_length=1, max_length=160)
    source_language: str = Field(
        default="fr",
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$",
    )
    question_bank_ids: list[int] = Field(min_length=1, max_length=100)
    duration_seconds: int = Field(default=1800, ge=60, le=28800)
    allow_previous_questions: bool = False
    same_questions_for_all: bool = True
    easy_question_count: int = Field(ge=0, le=200)
    medium_question_count: int = Field(ge=0, le=200)
    hard_question_count: int = Field(ge=0, le=200)
    easy_points: float = Field(default=0, ge=0, le=10000)
    medium_points: float = Field(default=0, ge=0, le=10000)
    hard_points: float = Field(default=0, ge=0, le=10000)

    @property
    def question_count(self) -> int:
        return (
            self.easy_question_count
            + self.medium_question_count
            + self.hard_question_count
        )

    @field_validator("title")
    @classmethod
    def normalize_quiz_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Le titre du quiz ne peut pas être vide")
        return normalized

    @model_validator(mode="after")
    def validate_question_counts(self) -> QuizCreate:
        if self.question_count < 1:
            raise ValueError("Le quiz doit contenir au moins une question")
        if self.question_count > 200:
            raise ValueError("Le quiz ne peut pas contenir plus de 200 questions")
        for difficulty in ("easy", "medium", "hard"):
            if (
                getattr(self, f"{difficulty}_question_count") == 0
                and getattr(self, f"{difficulty}_points") != 0
            ):
                raise ValueError(
                    "Des points ne peuvent être attribués à une difficulté sans question"
                )
        if len(set(self.question_bank_ids)) != len(self.question_bank_ids):
            raise ValueError(
                "Chaque banque de questions ne peut être sélectionnée qu’une fois"
            )
        return self


class QuizBankSummary(BaseModel):
    id: int
    grade_level: str
    chapter: str
    question_count: int
    easy_question_count: int
    medium_question_count: int
    hard_question_count: int


class QuizResponse(BaseModel):
    id: int
    mode: Literal["exam", "training"]
    title: str
    source_language: str
    question_count: int
    duration_seconds: int
    allow_previous_questions: bool
    same_questions_for_all: bool
    easy_question_count: int
    medium_question_count: int
    hard_question_count: int
    easy_points: float
    medium_points: float
    hard_points: float
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
    pending_manual_grading_count: int = 0
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
    status: Literal["waiting", "in_progress", "paused", "finished", "cancelled"]
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
    source_language: str
    class_name: str
    student_name: str
    join_code: str
    status: Literal["waiting", "in_progress", "paused", "finished", "cancelled"]
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
    response_language: str | None
    has_image: bool
    code_language: str | None
    code_content: str | None
    choices: list[StudentQuizChoiceResponse]


class TrainingFeedback(BaseModel):
    question_id: int
    is_correct: bool
    correct_choice_ids: list[int]
    expected_answer: str | None = None


class StudentQuizStateResponse(StudentQuizSessionResponse):
    question_number: int | None
    total_questions: int
    has_answered: bool
    answered_count: int
    allow_previous_questions: bool
    selected_choice_ids: list[int] | None = None
    written_answer: str | None = None
    question: StudentQuizQuestionResponse | None
    training_feedback: TrainingFeedback | None = None


class StudentQuizJoinResponse(StudentQuizStateResponse):
    participant_token: str


class StudentQuizAnswer(BaseModel):
    selected_choice_ids: list[int] | None = Field(
        default=None, min_length=1, max_length=12
    )
    written_answer: str | None = Field(default=None, max_length=20000)


class QuizAnswerGrade(BaseModel):
    score: float = Field(ge=0)


class QuizAnswerReview(BaseModel):
    id: int
    question_id: int
    position: int
    prompt: str
    difficulty: Literal["easy", "medium", "hard"]
    answer_mode: Literal["single", "multiple", "written"]
    submitted_answers: list[str]
    expected_answers: list[str]
    score: float
    max_score: float
    is_graded: bool


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
    model_config = ConfigDict(extra="forbid")

    join_code: str = Field(min_length=4, max_length=8)

    @field_validator("join_code")
    @classmethod
    def normalize_join_code(cls, value: str) -> str:
        return value.strip().upper()
