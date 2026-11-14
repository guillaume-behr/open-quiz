"""Question banks, their questions and JSON imports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import AnswerMode, Difficulty
from app.schemas.common import MAX_QUESTIONS_PER_BANK, normalize_optional_code


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


class QuestionBankUpdate(QuestionBankCreate):
    pass


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
    # Questions training can draw: every question but the written ones.
    trainable_question_count: int = 0
    # Quizzes that draw from the bank: deleting it takes it out of them.
    quiz_count: int = 0
    training_question_count: int | None = None


class TrainingQuestionBankItem(BaseModel):
    question_bank_id: int = Field(ge=1)
    question_count: int = Field(ge=1, le=200)


class TrainingQuestionBankSelection(BaseModel):
    # The former question_bank_ids format must fail rather than read as an
    # empty selection, which would clear the class's training banks.
    model_config = ConfigDict(extra="forbid")

    question_banks: list[TrainingQuestionBankItem] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("question_banks")
    @classmethod
    def validate_unique_question_banks(
        cls, value: list[TrainingQuestionBankItem]
    ) -> list[TrainingQuestionBankItem]:
        ids = [item.question_bank_id for item in value]
        if len(ids) != len(set(ids)):
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
    label: str = Field(max_length=4000)
    is_correct: bool = False
    points: float | None = Field(default=None, ge=-10000, le=10000)
    image: QuestionImportImage | None = None
    # The editor's way to send a new image: the position of a file part among
    # the request's choice_images, which no form field size limit applies to.
    # A JSON import carries its images in ``image`` instead.
    image_file: int | None = Field(default=None, ge=0, lt=12)
    remove_image: bool = False
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()

    @field_validator("code_content")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return normalize_optional_code(value)

    @model_validator(mode="after")
    def validate_code(self) -> QuestionChoiceCreate:
        if (self.code_language is None) != (self.code_content is None):
            raise ValueError(
                "Le langage et le contenu du code doivent être renseignés ensemble"
            )
        if self.image is not None and self.image_file is not None:
            raise ValueError("Une proposition reçoit une seule image")
        may_retain_existing_image = self.id is not None and not self.remove_image
        if (
            not self.label
            and self.image is None
            and self.image_file is None
            and self.code_content is None
            and not may_retain_existing_image
        ):
            raise ValueError("Une proposition nécessite du texte, une image ou du code")
        return self


class QuestionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    difficulty: Difficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: bool = True
    response_language: CodeLanguage | None = None
    allow_code_execution: bool = False
    choices: list[QuestionChoiceCreate] = Field(min_length=1, max_length=12)
    code_language: CodeLanguage | None = None
    code_content: str | None = Field(default=None, max_length=20000)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("La question ne peut pas être vide")
        return normalized

    @field_validator("code_content")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return normalize_optional_code(value)

    @model_validator(mode="after")
    def validate_correct_choices(self) -> QuestionCreate:
        existing_choice_ids = [
            choice.id for choice in self.choices if choice.id is not None
        ]
        if len(existing_choice_ids) != len(set(existing_choice_ids)):
            raise ValueError("Une proposition ne peut être utilisée qu’une fois")
        image_files = [
            choice.image_file
            for choice in self.choices
            if choice.image_file is not None
        ]
        if len(image_files) != len(set(image_files)):
            raise ValueError("Une image ne peut servir qu’à une proposition")
        correct_count = sum(choice.is_correct for choice in self.choices)
        if self.answer_mode != AnswerMode.WRITTEN and len(self.choices) < 2:
            raise ValueError("Une question nécessite au moins deux propositions")
        if self.answer_mode == AnswerMode.WRITTEN and len(self.choices) != 1:
            raise ValueError(
                "Une question rédactionnelle nécessite une réponse attendue"
            )
        if self.answer_mode == AnswerMode.WRITTEN and not self.answer_mode_disclosed:
            raise ValueError(
                "Le type d’une réponse rédactionnelle ne peut pas être masqué"
            )
        if (
            self.answer_mode != AnswerMode.WRITTEN
            and self.response_language is not None
        ):
            raise ValueError(
                "Un langage de réponse est réservé aux questions rédactionnelles"
            )
        if self.answer_mode != AnswerMode.WRITTEN and self.allow_code_execution:
            raise ValueError(
                "L’exécution de code est réservée aux questions rédactionnelles"
            )
        if self.allow_code_execution and self.response_language != "python":
            raise ValueError(
                "L’exécution de code nécessite une réponse au format Python"
            )
        if correct_count == 0:
            raise ValueError("Une question nécessite au moins une bonne réponse")
        if (
            self.answer_mode in {AnswerMode.SINGLE, AnswerMode.WRITTEN}
            and correct_count != 1
        ):
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
    points: float
    position: int
    has_image: bool
    code_language: CodeLanguage | None
    code_content: str | None


class QuestionContentResponse(BaseModel):
    id: int
    prompt: str
    difficulty: Difficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: bool
    response_language: CodeLanguage | None
    allow_code_execution: bool
    has_image: bool
    code_language: CodeLanguage | None
    code_content: str | None


class QuestionResponse(QuestionContentResponse):
    question_bank_id: int
    choices: list[QuestionChoiceResponse]
    created_at: datetime


class QuestionUpdate(QuestionCreate):
    remove_image: bool = False


class QuestionUpdateResponse(QuestionResponse):
    # Finished sessions whose grades were already published: an edit never
    # regrades them, so the interface can tell the teacher.
    published_sessions_not_regraded: int


class QuestionImportItem(QuestionCreate):
    image: QuestionImportImage | None = None

    @model_validator(mode="after")
    def validate_embedded_images(self) -> QuestionImportItem:
        # A JSON document has no file parts: its images travel inside it.
        if any(choice.image_file is not None for choice in self.choices):
            raise ValueError("Une image importée doit être encodée dans le fichier")
        return self


class QuestionBatchImport(BaseModel):
    version: Literal[1]
    question_bank: QuestionBankCreate
    questions: list[QuestionImportItem] = Field(max_length=MAX_QUESTIONS_PER_BANK)


class QuestionBatchImportResponse(BaseModel):
    question_bank: QuestionBankResponse
    questions: list[QuestionResponse]
