"""Quizzes, their sessions, make-up sessions and participants, for teachers."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.enums import QuizMode, SessionStatus


class QuizCreate(BaseModel):
    mode: Literal[QuizMode.EXAM] = QuizMode.EXAM
    title: str = Field(min_length=1, max_length=160)
    source_language: str = Field(
        default="fr",
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$",
    )
    question_bank_ids: list[int] = Field(min_length=1, max_length=100)
    duration_seconds: int = Field(default=900, ge=60, le=28800)
    allow_previous_questions: bool = False
    allow_answer_review: bool = True
    show_provisional_grades: bool = True
    allow_negative_points: bool = False
    same_questions_for_all: bool = False
    easy_question_count: int = Field(ge=0, le=200)
    medium_question_count: int = Field(ge=0, le=200)
    hard_question_count: int = Field(ge=0, le=200)

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
    mode: QuizMode
    title: str
    source_language: str
    question_count: int
    duration_seconds: int
    allow_previous_questions: bool
    allow_answer_review: bool
    show_provisional_grades: bool
    allow_negative_points: bool
    same_questions_for_all: bool
    easy_question_count: int
    medium_question_count: int
    hard_question_count: int
    question_banks: list[QuizBankSummary]
    created_at: datetime


class QuizLaunch(BaseModel):
    class_id: int = Field(gt=0)


class MakeupSessionCreate(BaseModel):
    class_id: int = Field(gt=0)
    quiz_ids: list[int] = Field(min_length=1, max_length=100)


class MakeupQuizOption(BaseModel):
    id: int
    title: str
    duration_seconds: int


class MakeupSessionJoinResponse(BaseModel):
    join_code: str
    class_name: str
    status: Literal[SessionStatus.WAITING]
    quizzes: list[MakeupQuizOption]


class MakeupQuizSelection(BaseModel):
    quiz_id: int = Field(gt=0)


# A browser event a student's quiz reports (StudentQuizViolation).
ReportedViolation = Literal[
    "fullscreen_exit",
    "pointer_exit",
    "window_blur",
    "page_hidden",
    "context_menu",
    "print_attempt",
]
# A participant's last alert: a reported event, or the resumption the server
# records itself (participants.SESSION_RESUMED_VIOLATION).
RecordedViolation = Literal[ReportedViolation, "session_resumed"]


class QuizParticipantResponse(BaseModel):
    id: int
    student_identifier: str
    student_display_name: str | None
    answered_count: int = 0
    # Questions skipped and still unanswered: none once the session is over,
    # when an empty answer stands for each.
    skipped_count: int = 0
    has_finished: bool = False
    score: float = 0
    maximum_score: float = 0
    pending_manual_grading_count: int = 0
    violation_count: int = 0
    last_violation_type: RecordedViolation | None = None
    last_violation_at: datetime | None = None
    joined_at: datetime


class MakeupParticipantResponse(QuizParticipantResponse):
    quiz_title: str
    total_questions: int


class MakeupSessionResponse(BaseModel):
    id: int
    class_id: int | None
    class_name: str
    join_code: str
    status: SessionStatus
    quizzes: list[MakeupQuizOption]
    participant_count: int
    participants: list[MakeupParticipantResponse]
    created_at: datetime


class QuizSessionResponse(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    class_id: int | None
    class_name: str
    join_code: str
    status: SessionStatus
    participant_count: int
    participants: list[QuizParticipantResponse]
    median_maximum_score: float = 0
    total_questions: int
    created_at: datetime
    started_at: datetime | None
    ends_at: datetime | None
    grades_published_at: datetime | None
    # The server's clock when this state was built, so a client whose own
    # clock is off can still count down to ends_at correctly.
    server_now: datetime = Field(default_factory=lambda: datetime.now(UTC))
