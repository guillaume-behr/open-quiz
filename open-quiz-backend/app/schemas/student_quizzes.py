"""A quiz session as the student taking it sees it, and their history."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import AnswerMode, Difficulty, SessionStatus
from app.schemas.questions import CodeLanguage, QuestionContentResponse
from app.schemas.quizzes import ReportedViolation


class StudentQuizSessionResponse(BaseModel):
    quiz_title: str
    source_language: str
    class_name: str
    student_name: str
    join_code: str
    status: SessionStatus
    ends_at: datetime | None
    # See QuizSessionResponse.server_now.
    server_now: datetime = Field(default_factory=lambda: datetime.now(UTC))


# A student's choice identifier: an opaque token (app/domain/choice_tokens.py).
StudentChoiceToken = Annotated[
    str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
]


class StudentQuizChoiceResponse(BaseModel):
    id: str
    label: str
    position: int
    has_image: bool
    code_language: CodeLanguage | None
    code_content: str | None


class StudentQuizQuestionResponse(QuestionContentResponse):
    choices: list[StudentQuizChoiceResponse]
    # The most a student can earn on this question, sent in exam mode only.
    total_points: float | None = None


class TrainingFeedback(BaseModel):
    question_id: int
    is_correct: bool | None
    correct_choice_ids: list[str]
    expected_answer: str | None = None
    submitted_answer: str | None = None
    requires_manual_review: bool = False


class StudentAnswerSummary(BaseModel):
    question_number: int
    question_id: int
    prompt: str
    answer_mode: AnswerMode
    submitted_answers: list[str]


class StudentQuizStateResponse(StudentQuizSessionResponse):
    question_number: int | None
    total_questions: int
    has_answered: bool
    answered_count: int
    allow_previous_questions: bool
    allow_answer_review: bool = False
    awaiting_final_submission: bool = False
    answer_summaries: list[StudentAnswerSummary] = Field(default_factory=list)
    accessible_question_numbers: list[int] = Field(default_factory=list)
    # The questions this participant has answered, for the numbered navigation.
    answered_question_numbers: list[int] = Field(default_factory=list)
    selected_choice_ids: list[str] | None = None
    written_answer: str | None = None
    question: StudentQuizQuestionResponse | None
    training_feedback: TrainingFeedback | None = None
    potential_score: float | None = None
    potential_maximum_score: float | None = None
    pending_manual_review_count: int = 0


class StudentQuizJoinResponse(StudentQuizStateResponse):
    participant_token: str


class StudentQuizAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The question shown when the student answered: an answer is never
    # recorded against another one (ANSWER_QUESTION_MISMATCH).
    question_id: int
    selected_choice_ids: list[StudentChoiceToken] | None = Field(
        default=None, min_length=1, max_length=12
    )
    written_answer: str | None = Field(default=None, max_length=20000)


class QuizAnswerGrade(BaseModel):
    score: float = Field(ge=0)
    feedback: str | None = Field(default=None, max_length=2000)


class QuizAnswerReview(BaseModel):
    id: int
    question_id: int
    position: int
    prompt: str
    difficulty: Difficulty
    answer_mode: AnswerMode
    code_content: str | None = None
    code_language: CodeLanguage | None = None
    response_language: CodeLanguage | None = None
    submitted_answers: list[str]
    expected_answers: list[str]
    score: float
    max_score: float
    is_graded: bool
    is_correct: bool | None
    feedback: str | None = None


class StudentQuizHistoryAnswer(BaseModel):
    question_id: int
    position: int
    prompt: str
    difficulty: Difficulty
    answer_mode: AnswerMode
    code_content: str | None = None
    code_language: CodeLanguage | None = None
    response_language: CodeLanguage | None = None
    submitted_answers: list[str]
    # Until the grades are published, nothing that reveals the key: no
    # expected answers, score, correctness or feedback.
    expected_answers: list[str]
    score: float | None
    max_score: float
    is_correct: bool | None
    feedback: str | None = None


class StudentQuizHistoryItem(BaseModel):
    session_id: int
    quiz_title: str
    class_name: str
    started_at: datetime
    grades_published: bool
    # False while the grades are unpublished and the quiz does not show a
    # provisional correction: the answers then carry no correction at all.
    correction_available: bool
    score: float | None = None
    maximum_score: float | None = None
    answers: list[StudentQuizHistoryAnswer]


class TrainingHistoryItem(BaseModel):
    session_id: int
    question_bank_id: int
    started_at: datetime
    score: float
    maximum_score: float
    pending_manual_review_count: int


class StudentQuizNavigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_number: int = Field(ge=1)


class StudentQuizViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: ReportedViolation


class QuizJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    join_code: str = Field(min_length=4, max_length=8)

    @field_validator("join_code")
    @classmethod
    def normalize_join_code(cls, value: str) -> str:
        return value.strip().upper()
