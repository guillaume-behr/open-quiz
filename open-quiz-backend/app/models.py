from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class GradeLevel(Base):
    __tablename__ = "grade_levels"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_grade_level_owner_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class StudentClass(Base):
    __tablename__ = "student_classes"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "name",
            name="uq_student_class_owner_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    grade_level: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class StudentAccount(Base):
    __tablename__ = "student_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    identifier: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "identifier",
            name="uq_student_class_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("student_classes.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_accounts.id"), nullable=True, unique=True, index=True
    )
    identifier: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class QuestionBank(Base):
    __tablename__ = "question_banks"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "grade_level",
            "chapter",
            name="uq_question_bank_owner_classification",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    grade_level: Mapped[str] = mapped_column(String(80))
    chapter: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class ClassTrainingQuestionBank(Base):
    __tablename__ = "class_training_question_banks"

    class_id: Mapped[int] = mapped_column(
        ForeignKey("student_classes.id"), primary_key=True
    )
    question_bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id"), index=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(20))
    answer_mode: Mapped[str] = mapped_column(String(20))
    answer_mode_disclosed: Mapped[bool] = mapped_column(Boolean, default=True)
    response_language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    correction_mode: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class QuestionCode(Base):
    __tablename__ = "question_codes"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)


class QuestionChoice(Base):
    __tablename__ = "question_choices"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_choice_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    label: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    code_language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    code_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="exam", index=True)
    title: Mapped[str] = mapped_column(String(160))
    source_language: Mapped[str] = mapped_column(String(35), default="fr")
    question_count: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    allow_previous_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_negative_points: Mapped[bool] = mapped_column(Boolean, default=False)
    same_questions_for_all: Mapped[bool] = mapped_column(Boolean, default=True)
    easy_question_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_question_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_question_count: Mapped[int] = mapped_column(Integer, default=0)
    easy_points: Mapped[float] = mapped_column(Float, default=0.0)
    medium_points: Mapped[float] = mapped_column(Float, default=0.0)
    hard_points: Mapped[float] = mapped_column(Float, default=0.0)
    # Kept only so databases created before explicit difficulty counts can still
    # satisfy their legacy NOT NULL columns. These values are no longer exposed.
    easy_percentage: Mapped[int] = mapped_column(Integer, default=0)
    medium_percentage: Mapped[int] = mapped_column(Integer, default=0)
    hard_percentage: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class QuizQuestionBank(Base):
    __tablename__ = "quiz_question_banks"

    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), primary_key=True)
    question_bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id"), primary_key=True
    )


class TrainingQuizProfile(Base):
    __tablename__ = "training_quiz_profiles"

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id"), unique=True, index=True
    )


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    quiz_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_language: Mapped[str | None] = mapped_column(String(35), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_previous_questions: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    allow_negative_points: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    same_questions_for_all: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_classes.id"), nullable=True, index=True
    )
    class_name: Mapped[str] = mapped_column(String(120))
    join_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    makeup_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("makeup_sessions.id"), nullable=True, index=True
    )


class MakeupSession(Base):
    __tablename__ = "makeup_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_classes.id"), nullable=True, index=True
    )
    class_name: Mapped[str] = mapped_column(String(120))
    join_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class MakeupSessionQuiz(Base):
    __tablename__ = "makeup_session_quizzes"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("makeup_sessions.id"), primary_key=True
    )
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), primary_key=True)


class MakeupSessionSelection(Base):
    __tablename__ = "makeup_session_selections"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("makeup_sessions.id"), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)


class QuizJoinCode(Base):
    __tablename__ = "quiz_join_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)


class QuizSessionQuestion(Base):
    __tablename__ = "quiz_session_questions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "position",
            name="uq_quiz_session_question_position",
        ),
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id"), primary_key=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=0.0)


class QuizSessionStudentQuestion(Base):
    __tablename__ = "quiz_session_student_questions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "student_id",
            "position",
            name="uq_quiz_session_student_question_position",
        ),
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id"), primary_key=True
    )
    student_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    student_identifier: Mapped[str] = mapped_column(String(80), primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, default=0.0)


class QuizParticipant(Base):
    __tablename__ = "quiz_participants"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "student_identifier",
            name="uq_quiz_participant_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id"), index=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"), nullable=True, index=True
    )
    student_identifier: Mapped[str] = mapped_column(String(80))
    student_display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    access_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    current_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_violation_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_violation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "participant_id",
            "question_id",
            name="uq_quiz_answer_participant_question",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id"), index=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_participants.id"), index=True
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    answer_data: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    is_graded: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class RefreshSessionFamily(Base):
    __tablename__ = "refresh_session_families"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("refresh_sessions.id"), primary_key=True
    )
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TwoFactorCredential(Base):
    __tablename__ = "two_factor_credentials"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_secret: Mapped[str] = mapped_column(String(255))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuthenticationChallenge(Base):
    __tablename__ = "authentication_challenges"

    token_id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    limiter_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    window_started_at: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer)


class ProblemReport(Base):
    __tablename__ = "problem_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    page_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class SecurityState(Base):
    __tablename__ = "security_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
