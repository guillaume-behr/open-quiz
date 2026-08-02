import csv
import io
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil, comb
from random import SystemRandom
from secrets import token_urlsafe
from string import ascii_uppercase, digits
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.audit import audit_event
from app.dependencies import DbSession, ProfessorUser
from app.grading import compute_final_scores
from app.models import (
    ClassTrainingQuestionBank,
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    QuizSessionStudentQuestion,
    Student,
    StudentAccount,
    StudentClass,
    TrainingQuizProfile,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.routers.question_banks import question_response
from app.routers.student_auth import current_student
from app.schemas import (
    MakeupQuizOption,
    MakeupQuizSelection,
    MakeupSessionCreate,
    MakeupSessionJoinResponse,
    MakeupSessionResponse,
    QuestionBankResponse,
    QuestionResponse,
    QuizAnswerGrade,
    QuizAnswerReview,
    QuizBankSummary,
    QuizCreate,
    QuizJoin,
    QuizLaunch,
    QuizParticipantResponse,
    QuizResponse,
    QuizSessionResponse,
    StudentQuizAnswer,
    StudentQuizChoiceResponse,
    StudentQuizHistoryAnswer,
    StudentQuizHistoryItem,
    StudentQuizJoinResponse,
    StudentQuizNavigation,
    StudentQuizQuestionResponse,
    StudentQuizSessionResponse,
    StudentQuizStateResponse,
    StudentQuizViolation,
    TrainingFeedback,
    TrainingQuestionBankSelection,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])
randomizer = SystemRandom()
JOIN_CODE_ALPHABET = ascii_uppercase + digits
VIOLATION_DEDUPLICATION_SECONDS = 2
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")
MAX_TRAINING_QUESTIONS = 200


def safe_spreadsheet_cell(value: str) -> str:
    trimmed = value.lstrip()
    if value.startswith(("\t", "\r", "\n")) or trimmed.startswith(
        SPREADSHEET_FORMULA_PREFIXES
    ):
        return f"'{value}"
    return value


def enforce_public_rate_limit(
    request: Request,
    session: DbSession,
    limiter_name: str,
    subject: str,
) -> None:
    limiter = getattr(request.app.state, limiter_name)
    retry_after = limiter.reserve(session, subject)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives pour rejoindre le quiz",
            headers={"Retry-After": str(retry_after)},
        )


def quiz_join_rejected() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Impossible de rejoindre ce quiz",
    )


def reject_quiz_join(
    request: Request,
    session: DbSession,
    subject: str,
) -> None:
    enforce_public_rate_limit(
        request,
        session,
        "quiz_join_rate_limiter",
        subject,
    )
    raise quiz_join_rejected()


def difficulty_counts(payload: Quiz | QuizCreate) -> dict[str, int]:
    return {
        "easy": payload.easy_question_count,
        "medium": payload.medium_question_count,
        "hard": payload.hard_question_count,
    }


def difficulty_points(quiz: Quiz) -> dict[str, float]:
    return {
        "easy": quiz.easy_points,
        "medium": quiz.medium_points,
        "hard": quiz.hard_points,
    }


def points_for_drawn_questions(
    quiz: Quiz,
    question_ids: list[int],
    session: DbSession,
) -> dict[int, float]:
    return dict(
        session.execute(
            select(Question.id, Question.points).where(Question.id.in_(question_ids))
        ).all()
    )


POINT_TARGET_SHORTFALL_TOLERANCE = 0.75
MAX_QUIZ_BONUS_POINTS = 2.0


def adjust_last_question_for_points(
    selected: list[Question],
    candidates: list[Question],
    target: float,
) -> list[Question]:
    if not selected or target <= 0:
        return selected
    total = sum(question.points for question in selected)
    minimum = target - POINT_TARGET_SHORTFALL_TOLERANCE
    maximum = target + MAX_QUIZ_BONUS_POINTS
    if minimum <= total <= maximum:
        return selected
    fixed_total = total - selected[-1].points
    fixed_ids = {question.id for question in selected[:-1]}
    replacements = [question for question in candidates if question.id not in fixed_ids]
    if not replacements:
        return selected
    valid_replacements = [
        question
        for question in replacements
        if minimum <= fixed_total + question.points <= maximum
    ]
    if not valid_replacements:
        raise ValueError("Aucun remplacement ne respecte la limite de points")
    replacement = min(
        valid_replacements,
        key=lambda question: (
            abs(target - (fixed_total + question.points)),
            randomizer.random(),
        ),
    )
    return [*selected[:-1], replacement]


def owned_quiz(quiz_id: int, professor: ProfessorUser, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
    )
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz introuvable",
        )
    return quiz


def quiz_bank_ids(quiz_id: int, session: DbSession) -> list[int]:
    return list(
        session.scalars(
            select(QuizQuestionBank.question_bank_id).where(
                QuizQuestionBank.quiz_id == quiz_id
            )
        )
    )


def validate_bank_selection(
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBank]:
    banks = list(
        session.scalars(
            select(QuestionBank).where(
                QuestionBank.id.in_(payload.question_bank_ids),
                QuestionBank.owner_id == professor.id,
            )
        )
    )
    if len(banks) != len(payload.question_bank_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une ou plusieurs banques de questions sont invalides",
        )
    difficulty_counts_for_banks(payload, payload.question_bank_ids, session)
    return banks


def available_difficulty_counts(
    bank_ids: list[int],
    session: DbSession,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for difficulty, count in session.execute(
        select(Question.difficulty, func.count(Question.id))
        .where(Question.question_bank_id.in_(bank_ids))
        .group_by(Question.difficulty)
    ):
        counts[difficulty] = count
    return counts


def difficulty_counts_for_banks(
    payload: Quiz | QuizCreate,
    bank_ids: list[int],
    session: DbSession,
) -> dict[str, int]:
    available = available_difficulty_counts(bank_ids, session)
    requested = difficulty_counts(payload)
    unavailable = [
        difficulty
        for difficulty, count in requested.items()
        if count > available.get(difficulty, 0)
    ]
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Nombre de questions insuffisant pour une ou plusieurs difficultés "
                "dans les banques sélectionnées"
            ),
        )
    return requested


def draw_question_ids(quiz: Quiz, session: DbSession) -> list[int]:
    bank_ids = quiz_bank_ids(quiz.id, session)
    requested = difficulty_counts_for_banks(quiz, bank_ids, session)
    candidates_by_difficulty = {
        difficulty: list(
            session.scalars(
                select(Question).where(
                    Question.question_bank_id.in_(bank_ids),
                    Question.difficulty == difficulty,
                )
            )
        )
        for difficulty, count in requested.items()
        if count > 0
    }
    target = sum(difficulty_points(quiz).values())
    selected: list[Question] = []
    for _ in range(100):
        selected = []
        for difficulty, count in requested.items():
            if count > 0:
                selected.extend(
                    randomizer.sample(candidates_by_difficulty[difficulty], count)
                )
        if target <= 0:
            break
        last_difficulty = selected[-1].difficulty
        try:
            selected = adjust_last_question_for_points(
                selected,
                candidates_by_difficulty[last_difficulty],
                target,
            )
            break
        except ValueError:
            continue
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Les questions disponibles ne permettent pas de respecter "
                "la limite totale de points"
            ),
        )
    selected_ids = [question.id for question in selected]
    randomizer.shuffle(selected_ids)
    return selected_ids


def draw_unique_question_ids(
    quiz: Quiz,
    session: DbSession,
    used_draws: set[tuple[int, ...]],
) -> list[int]:
    if used_draws:
        bank_ids = quiz_bank_ids(quiz.id, session)
        requested = difficulty_counts_for_banks(quiz, bank_ids, session)
        available = available_difficulty_counts(bank_ids, session)
        possible_combination_count = 1
        for difficulty, count in requested.items():
            possible_combination_count *= comb(available.get(difficulty, 0), count)
        if len(used_draws) >= possible_combination_count:
            return draw_question_ids(quiz, session)

    for _ in range(200):
        question_ids = draw_question_ids(quiz, session)
        signature = tuple(sorted(question_ids))
        if signature not in used_draws:
            used_draws.add(signature)
            return question_ids
    # If the banks contain only one possible combination, every student still
    # receives an independent draw even though the resulting sets must match.
    return draw_question_ids(quiz, session)


def load_question_responses(
    question_ids: list[int],
    session: DbSession,
) -> list[QuestionResponse]:
    if not question_ids:
        return []
    questions_by_id = {
        question.id: question
        for question in session.scalars(
            select(Question)
            .options(defer(Question.image_data))
            .where(Question.id.in_(question_ids))
        )
    }
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    for choice in session.scalars(
        select(QuestionChoice)
        .options(defer(QuestionChoice.image_data))
        .where(QuestionChoice.question_id.in_(question_ids))
        .order_by(QuestionChoice.question_id, QuestionChoice.position)
    ):
        choices_by_question[choice.question_id].append(choice)
    codes_by_question = {
        code.question_id: code
        for code in session.scalars(
            select(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
        )
    }
    return [
        question_response(
            questions_by_id[question_id],
            choices_by_question[question_id],
            codes_by_question.get(question_id),
        )
        for question_id in question_ids
    ]


def quiz_response(quiz: Quiz, session: DbSession) -> QuizResponse:
    rows = session.execute(
        select(
            QuestionBank,
            func.count(Question.id),
            func.sum(case((Question.difficulty == "easy", 1), else_=0)),
            func.sum(case((Question.difficulty == "medium", 1), else_=0)),
            func.sum(case((Question.difficulty == "hard", 1), else_=0)),
        )
        .join(
            QuizQuestionBank,
            QuizQuestionBank.question_bank_id == QuestionBank.id,
        )
        .outerjoin(Question, Question.question_bank_id == QuestionBank.id)
        .where(QuizQuestionBank.quiz_id == quiz.id)
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
    )
    return QuizResponse(
        id=quiz.id,
        mode=quiz.mode,
        title=quiz.title,
        source_language=quiz.source_language,
        question_count=quiz.question_count,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        same_questions_for_all=quiz.same_questions_for_all,
        easy_question_count=quiz.easy_question_count,
        medium_question_count=quiz.medium_question_count,
        hard_question_count=quiz.hard_question_count,
        easy_points=quiz.easy_points,
        medium_points=quiz.medium_points,
        hard_points=quiz.hard_points,
        question_banks=[
            QuizBankSummary(
                id=bank.id,
                grade_level=bank.grade_level,
                chapter=bank.chapter,
                question_count=count,
                easy_question_count=easy_count or 0,
                medium_question_count=medium_count or 0,
                hard_question_count=hard_count or 0,
            )
            for bank, count, easy_count, medium_count, hard_count in rows
        ],
        created_at=quiz.created_at,
    )


def question_bank_responses(
    question_bank_ids: list[int],
    session: DbSession,
) -> list[QuestionBankResponse]:
    if not question_bank_ids:
        return []
    rows = session.execute(
        select(
            QuestionBank,
            func.count(Question.id),
            func.sum(case((Question.difficulty == "easy", 1), else_=0)),
            func.sum(case((Question.difficulty == "medium", 1), else_=0)),
            func.sum(case((Question.difficulty == "hard", 1), else_=0)),
        )
        .outerjoin(Question, Question.question_bank_id == QuestionBank.id)
        .where(QuestionBank.id.in_(question_bank_ids))
        .group_by(QuestionBank.id)
        .order_by(QuestionBank.grade_level, QuestionBank.chapter)
    )
    return [
        QuestionBankResponse.model_validate(bank).model_copy(
            update={
                "question_count": question_count,
                "easy_question_count": easy_count or 0,
                "medium_question_count": medium_count or 0,
                "hard_question_count": hard_count or 0,
            }
        )
        for bank, question_count, easy_count, medium_count, hard_count in rows
    ]


def training_profile_quiz(owner_id: int, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz)
        .join(TrainingQuizProfile, TrainingQuizProfile.quiz_id == Quiz.id)
        .where(TrainingQuizProfile.owner_id == owner_id)
    )
    if quiz is not None:
        return quiz
    quiz = Quiz(
        owner_id=owner_id,
        mode="training",
        title="Entraînement",
        source_language="fr",
        question_count=0,
        duration_seconds=28800,
        allow_previous_questions=False,
        same_questions_for_all=False,
        easy_question_count=0,
        medium_question_count=0,
        hard_question_count=0,
        easy_points=0,
        medium_points=0,
        hard_points=0,
    )
    session.add(quiz)
    session.flush()
    session.add(TrainingQuizProfile(owner_id=owner_id, quiz_id=quiz.id))
    return quiz


def draw_training_question_ids(bank_id: int, session: DbSession) -> list[int]:
    question_ids = list(
        session.scalars(select(Question.id).where(Question.question_bank_id == bank_id))
    )
    randomizer.shuffle(question_ids)
    return question_ids[:MAX_TRAINING_QUESTIONS]


def owned_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> tuple[QuizSession, Quiz]:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.id == session_id,
            Quiz.owner_id == professor.id,
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session de quiz introuvable",
        )
    return row


def session_question_ids(
    quiz_session: QuizSession,
    session: DbSession,
    participant: QuizParticipant | None = None,
) -> list[int]:
    if participant is not None and participant.student_id is not None:
        personalized_ids = list(
            session.scalars(
                select(QuizSessionStudentQuestion.question_id)
                .where(
                    QuizSessionStudentQuestion.session_id == quiz_session.id,
                    QuizSessionStudentQuestion.student_id == participant.student_id,
                )
                .order_by(QuizSessionStudentQuestion.position)
            )
        )
        if personalized_ids:
            return personalized_ids
    if participant is not None:
        personalized_ids = list(
            session.scalars(
                select(QuizSessionStudentQuestion.question_id)
                .where(
                    QuizSessionStudentQuestion.session_id == quiz_session.id,
                    QuizSessionStudentQuestion.student_identifier
                    == participant.student_identifier,
                )
                .order_by(QuizSessionStudentQuestion.position)
            )
        )
        if personalized_ids:
            return personalized_ids
    return list(
        session.scalars(
            select(QuizSessionQuestion.question_id)
            .where(QuizSessionQuestion.session_id == quiz_session.id)
            .order_by(QuizSessionQuestion.position)
        )
    )


def session_question_points(
    quiz_session: QuizSession,
    session: DbSession,
    participant: QuizParticipant | None = None,
) -> dict[int, float]:
    if participant is not None and participant.student_id is not None:
        personalized = dict(
            session.execute(
                select(
                    QuizSessionStudentQuestion.question_id,
                    QuizSessionStudentQuestion.points,
                ).where(
                    QuizSessionStudentQuestion.session_id == quiz_session.id,
                    QuizSessionStudentQuestion.student_id == participant.student_id,
                )
            ).all()
        )
        if personalized:
            return personalized
    if participant is not None:
        personalized = dict(
            session.execute(
                select(
                    QuizSessionStudentQuestion.question_id,
                    QuizSessionStudentQuestion.points,
                ).where(
                    QuizSessionStudentQuestion.session_id == quiz_session.id,
                    QuizSessionStudentQuestion.student_identifier
                    == participant.student_identifier,
                )
            ).all()
        )
        if personalized:
            return personalized
    return dict(
        session.execute(
            select(QuizSessionQuestion.question_id, QuizSessionQuestion.points).where(
                QuizSessionQuestion.session_id == quiz_session.id
            )
        ).all()
    )


def current_question_id(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
) -> int | None:
    if (
        quiz_session.status not in ("in_progress", "paused")
        or participant.current_position is None
    ):
        return None
    question_ids = session_question_ids(quiz_session, session, participant)
    if participant.current_position >= len(question_ids):
        return None
    return question_ids[participant.current_position]


def session_question_count(quiz_session: QuizSession, session: DbSession) -> int:
    common_count = session.scalar(
        select(func.count(QuizSessionQuestion.question_id)).where(
            QuizSessionQuestion.session_id == quiz_session.id
        )
    )
    if common_count:
        return common_count
    personalized_count = session.scalar(
        select(func.count(QuizSessionStudentQuestion.question_id))
        .where(QuizSessionStudentQuestion.session_id == quiz_session.id)
        .group_by(QuizSessionStudentQuestion.student_identifier)
        .limit(1)
    )
    return personalized_count or 0


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    expire_quiz_session(quiz_session, quiz, session)
    participants = list(
        session.scalars(
            select(QuizParticipant)
            .where(QuizParticipant.session_id == quiz_session.id)
            .order_by(QuizParticipant.joined_at, QuizParticipant.id)
        )
    )
    answer_rows = list(
        session.execute(
            select(
                QuizAnswer.participant_id,
                func.count(QuizAnswer.id),
                func.coalesce(func.sum(QuizAnswer.score), 0),
                func.sum(case((QuizAnswer.is_graded.is_(False), 1), else_=0)),
            )
            .where(QuizAnswer.session_id == quiz_session.id)
            .group_by(QuizAnswer.participant_id)
        )
    )
    answers_by_student = {
        participant_id: (answered_count, float(score), pending_count or 0)
        for participant_id, answered_count, score, pending_count in answer_rows
    }
    student_ids = [
        participant.student_id
        for participant in participants
        if participant.student_id is not None
    ]
    students_by_id = (
        {
            student.id: student
            for student in session.scalars(
                select(Student).where(Student.id.in_(student_ids))
            )
        }
        if student_ids
        else {}
    )
    return QuizSessionResponse(
        id=quiz_session.id,
        quiz_id=quiz.id,
        quiz_title=quiz_session.quiz_title or quiz.title,
        class_id=quiz_session.class_id,
        class_name=quiz_session.class_name,
        join_code=quiz_session.join_code,
        status=quiz_session.status,
        participant_count=len(participants),
        participants=[
            QuizParticipantResponse(
                id=participant.id,
                student_identifier=participant.student_identifier,
                student_display_name=(
                    students_by_id[participant.student_id].display_name
                    if participant.student_id in students_by_id
                    else participant.student_display_name
                ),
                answered_count=answers_by_student.get(participant.id, (0, 0, 0))[0],
                score=(
                    answers_by_student.get(participant.id, (0, 0, 0))[1]
                    if quiz_session.status == "finished"
                    else 0
                ),
                pending_manual_grading_count=(
                    answers_by_student.get(participant.id, (0, 0, 0))[2]
                    if quiz_session.status == "finished"
                    else 0
                ),
                violation_count=participant.violation_count,
                last_violation_type=participant.last_violation_type,
                last_violation_at=participant.last_violation_at,
                joined_at=participant.joined_at,
            )
            for participant in participants
        ],
        current_question_number=None,
        total_questions=session_question_count(quiz_session, session),
        current_submission_count=0,
        created_at=quiz_session.created_at,
        started_at=quiz_session.started_at,
        ends_at=quiz_ends_at(quiz_session, quiz),
    )


def student_session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
) -> StudentQuizSessionResponse:
    return StudentQuizSessionResponse(
        quiz_title=quiz_session.quiz_title or quiz.title,
        source_language=quiz_session.source_language or quiz.source_language,
        class_name=quiz_session.class_name,
        student_name=(
            participant.student_display_name or participant.student_identifier
        ),
        join_code=quiz_session.join_code,
        status=quiz_session.status,
        ends_at=quiz_ends_at(quiz_session, quiz),
    )


def quiz_ends_at(quiz_session: QuizSession, quiz: Quiz) -> datetime | None:
    started_at = quiz_session.started_at
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    paused_duration = quiz_session.paused_duration_seconds or 0
    if quiz_session.status == "paused" and quiz_session.paused_at is not None:
        paused_at = quiz_session.paused_at
        if paused_at.tzinfo is None:
            paused_at = paused_at.replace(tzinfo=UTC)
        paused_duration += ceil(max(0, (datetime.now(UTC) - paused_at).total_seconds()))
    duration_seconds = quiz_session.duration_seconds
    if duration_seconds is None:
        duration_seconds = quiz.duration_seconds
    return started_at + timedelta(seconds=duration_seconds + paused_duration)


def expire_quiz_session(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> None:
    ends_at = quiz_ends_at(quiz_session, quiz)
    if (
        quiz_session.status == "in_progress"
        and ends_at is not None
        and datetime.now(UTC) >= ends_at
    ):
        quiz_session.status = "finished"
        for participant in session.scalars(
            select(QuizParticipant).where(QuizParticipant.session_id == quiz_session.id)
        ):
            participant.current_position = None
        if quiz.mode == "exam":
            compute_final_scores(quiz_session, session)
        session.commit()


def expire_owned_quiz_sessions(
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    rows = list(
        session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.status == "in_progress",
            )
        )
    )
    finished_training_ids: list[int] = []
    for quiz_session, quiz in rows:
        expire_quiz_session(quiz_session, quiz, session)
        if quiz.mode == "training" and quiz_session.status == "finished":
            finished_training_ids.append(quiz_session.id)
    if finished_training_ids:
        delete_quiz_session_records(finished_training_ids, session)
        session.commit()


def delete_quiz_session_records(
    session_ids: list[int],
    session: DbSession,
) -> None:
    if not session_ids:
        return
    session.execute(delete(QuizAnswer).where(QuizAnswer.session_id.in_(session_ids)))
    session.execute(
        delete(QuizParticipant).where(QuizParticipant.session_id.in_(session_ids))
    )
    session.execute(
        delete(QuizSessionQuestion).where(
            QuizSessionQuestion.session_id.in_(session_ids)
        )
    )
    session.execute(
        delete(QuizSessionStudentQuestion).where(
            QuizSessionStudentQuestion.session_id.in_(session_ids)
        )
    )
    session.execute(delete(QuizSession).where(QuizSession.id.in_(session_ids)))


def discard_finished_training_session(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> None:
    if quiz.mode != "training" or quiz_session.status != "finished":
        return
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()


def discard_previous_training_sessions(
    student: StudentAccount,
    membership: Student,
    session: DbSession,
) -> None:
    session_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                Quiz.owner_id == student.owner_id,
                Quiz.mode == "training",
                or_(
                    QuizParticipant.student_id == membership.id,
                    QuizParticipant.student_identifier == student.identifier,
                ),
            )
        )
    )
    delete_quiz_session_records(session_ids, session)


def purge_expired_quiz_results(
    professor: ProfessorUser,
    request: Request,
    session: DbSession,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(
        days=request.app.state.settings.quiz_result_retention_days
    )
    expired_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.status == "finished",
                QuizSession.started_at.is_not(None),
                QuizSession.started_at <= cutoff,
            )
        )
    )
    if expired_ids:
        delete_quiz_session_records(expired_ids, session)
        session.commit()
        audit_event(
            "quiz.results_retention_purged",
            professor_id=professor.id,
            deleted_count=len(expired_ids),
        )
    return len(expired_ids)


def participant_token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def public_session_subject(
    join_code: str,
    purpose: str,
    session: DbSession,
) -> str:
    normalized_join_code = join_code.strip().upper()
    session_id = session.scalar(
        select(QuizSession.id).where(QuizSession.join_code == normalized_join_code)
    )
    return (
        f"{purpose}:session:{session_id}"
        if session_id is not None
        else f"{purpose}:unknown"
    )


def authenticated_participant(
    join_code: str,
    token: str | None,
    request: Request,
    session: DbSession,
) -> tuple[QuizSession, Quiz, QuizParticipant]:
    if not token:
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            public_session_subject(join_code, "participant-auth", session),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de participation au quiz manquant",
        )
    row = session.execute(
        select(QuizSession, Quiz, QuizParticipant)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .join(
            QuizParticipant,
            QuizParticipant.session_id == QuizSession.id,
        )
        .where(
            QuizSession.join_code == join_code.strip().upper(),
            QuizParticipant.access_token_hash == participant_token_hash(token),
        )
    ).first()
    if row is None:
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            public_session_subject(join_code, "participant-auth", session),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de participation au quiz invalide",
        )
    return row


def student_question_response(
    question_id: int,
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizQuestionResponse:
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La question actuelle n’est pas disponible",
        )
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .options(defer(QuestionChoice.image_data))
            .where(QuestionChoice.question_id == question.id)
            .order_by(QuestionChoice.position)
        )
    )
    choices.sort(
        key=lambda choice: sha256(
            (f"{quiz_session.id}:{participant.id}:{question.id}:{choice.id}").encode()
        ).digest()
    )
    code = session.get(QuestionCode, question.id)
    return StudentQuizQuestionResponse(
        id=question.id,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        answer_mode_disclosed=question.answer_mode_disclosed,
        response_language=question.response_language,
        has_image=question.image_content_type is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=[
            StudentQuizChoiceResponse(
                id=choice.id,
                label=choice.label,
                position=position,
                has_image=choice.image_content_type is not None,
                code_language=choice.code_language,
                code_content=choice.code_content,
            )
            for position, choice in enumerate(choices)
        ],
    )


def student_state_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizStateResponse:
    expire_quiz_session(quiz_session, quiz, session)
    question_ids = session_question_ids(quiz_session, session, participant)
    question_id = current_question_id(quiz_session, participant, session)
    has_answered = (
        question_id is not None
        and session.scalar(
            select(QuizAnswer.id).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
                QuizAnswer.question_id == question_id,
            )
        )
        is not None
    )
    existing_answer = (
        session.scalar(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
                QuizAnswer.question_id == question_id,
            )
        )
        if question_id is not None
        else None
    )
    saved_answer = (
        json.loads(existing_answer.answer_data) if existing_answer is not None else {}
    )
    answered_count = session.scalar(
        select(func.count(QuizAnswer.id)).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.participant_id == participant.id,
        )
    )
    return StudentQuizStateResponse(
        **student_session_response(quiz_session, quiz, participant).model_dump(),
        question_number=(
            participant.current_position + 1
            if participant.current_position is not None
            and quiz_session.status == "in_progress"
            else None
        ),
        total_questions=len(question_ids),
        has_answered=has_answered,
        answered_count=answered_count or 0,
        allow_previous_questions=(
            quiz_session.allow_previous_questions
            if quiz_session.allow_previous_questions is not None
            else quiz.allow_previous_questions
        ),
        selected_choice_ids=saved_answer.get("selected_choice_ids"),
        written_answer=saved_answer.get("written_answer"),
        question=(
            student_question_response(
                question_id,
                quiz_session,
                participant,
                session,
            )
            if question_id is not None and quiz_session.status == "in_progress"
            else None
        ),
    )


def generate_join_code(session: DbSession) -> str:
    for _ in range(20):
        code = "".join(randomizer.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        if (
            session.scalar(select(QuizSession.id).where(QuizSession.join_code == code))
            is None
            and session.scalar(
                select(MakeupSession.id).where(MakeupSession.join_code == code)
            )
            is None
        ):
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Impossible de générer un code de quiz",
    )


@router.get("", response_model=list[QuizResponse])
def list_quizzes(
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    search: Annotated[str, Query(max_length=160)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
    mode: Annotated[str, Query(pattern="^exam$")] = "exam",
) -> list[QuizResponse]:
    filters = [Quiz.owner_id == professor.id, Quiz.mode == mode]
    if search:
        filters.append(Quiz.title.ilike(f"%{search}%"))
    if grade_level:
        filters.append(
            Quiz.id.in_(
                select(QuizQuestionBank.quiz_id)
                .join(
                    QuestionBank,
                    QuestionBank.id == QuizQuestionBank.question_bank_id,
                )
                .where(QuestionBank.grade_level == grade_level)
            )
        )
    total = session.scalar(select(func.count()).select_from(Quiz).where(*filters)) or 0
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(*filters)
            .order_by(Quiz.created_at.desc(), Quiz.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return [quiz_response(quiz, session) for quiz in quizzes]


@router.post(
    "",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_quiz(
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizResponse:
    validate_bank_selection(payload, professor, session)
    quiz = Quiz(
        owner_id=professor.id,
        mode=payload.mode,
        title=payload.title,
        source_language=payload.source_language,
        question_count=payload.question_count,
        duration_seconds=payload.duration_seconds,
        allow_previous_questions=payload.allow_previous_questions,
        same_questions_for_all=False,
        easy_question_count=payload.easy_question_count,
        medium_question_count=payload.medium_question_count,
        hard_question_count=payload.hard_question_count,
        easy_points=payload.easy_points,
        medium_points=payload.medium_points,
        hard_points=payload.hard_points,
    )
    session.add(quiz)
    session.flush()
    session.add_all(
        QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank_id)
        for bank_id in payload.question_bank_ids
    )
    session.commit()
    session.refresh(quiz)
    return quiz_response(quiz, session)


@router.get("/sessions/active", response_model=list[QuizSessionResponse])
def list_active_sessions(
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizSessionResponse]:
    expire_owned_quiz_sessions(professor, session)
    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            Quiz.owner_id == professor.id,
            Quiz.mode == "exam",
            QuizSession.status.in_(["waiting", "in_progress", "paused", "cancelled"]),
        )
        .order_by(QuizSession.created_at.desc(), QuizSession.id.desc())
        .limit(20)
    )
    return [
        session_response(quiz_session, quiz, session) for quiz_session, quiz in rows
    ]


@router.get("/sessions/results", response_model=list[QuizSessionResponse])
def list_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    quiz_search: Annotated[str, Query(max_length=160)] = "",
    class_search: Annotated[str, Query(max_length=120)] = "",
) -> list[QuizSessionResponse]:
    expire_owned_quiz_sessions(professor, session)
    purge_expired_quiz_results(professor, request, session)
    filters = [
        Quiz.owner_id == professor.id,
        Quiz.mode == "exam",
        QuizSession.status == "finished",
    ]
    if quiz_search:
        filters.append(
            func.coalesce(QuizSession.quiz_title, Quiz.title).ilike(f"%{quiz_search}%")
        )
    if class_search:
        filters.append(QuizSession.class_name.ilike(f"%{class_search}%"))
    total = (
        session.scalar(
            select(func.count())
            .select_from(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*filters)
        )
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(*filters)
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.created_at.desc(),
            QuizSession.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [
        session_response(quiz_session, quiz, session) for quiz_session, quiz in rows
    ]


@router.get("/sessions/results/export")
def export_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    class_id: Annotated[int, Query(ge=1)],
    quiz_id: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    purge_expired_quiz_results(professor, request, session)
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    filters = [
        Quiz.owner_id == professor.id,
        Quiz.mode == "exam",
        QuizSession.class_id == class_id,
        QuizSession.status == "finished",
    ]
    if quiz_id is not None:
        quiz = session.scalar(
            select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
        )
        if quiz is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        filters.append(QuizSession.quiz_id == quiz_id)

    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(*filters)
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.created_at.desc(),
            QuizSession.id.desc(),
        )
    )
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "class",
            "quiz",
            "date",
            "student_identifier",
            "student_name",
            "questions_answered",
            "total_questions",
            "score",
            "pending_manual_grading",
            "violations",
        ]
    )
    for quiz_session, quiz in rows:
        result = session_response(quiz_session, quiz, session)
        result_date = result.started_at or result.created_at
        for participant in result.participants:
            writer.writerow(
                [
                    safe_spreadsheet_cell(result.class_name),
                    safe_spreadsheet_cell(result.quiz_title),
                    result_date.isoformat(),
                    safe_spreadsheet_cell(participant.student_identifier),
                    safe_spreadsheet_cell(participant.student_display_name or ""),
                    participant.answered_count,
                    result.total_questions,
                    participant.score,
                    participant.pending_manual_grading_count,
                    participant.violation_count,
                ]
            )

    safe_class_id = student_class.id
    safe_quiz = f"-quiz-{quiz_id}" if quiz_id is not None else "-tous-les-quiz"
    filename = f"resultats-classe-{safe_class_id}{safe_quiz}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def answer_review(
    answer: QuizAnswer,
    question: Question,
    position: int,
    choices: list[QuestionChoice],
    max_score: float,
) -> QuizAnswerReview:
    submitted = json.loads(answer.answer_data)
    choices_by_id = {choice.id: choice for choice in choices}
    if question.answer_mode == "written":
        submitted_answers = [str(submitted.get("written_answer", ""))]
    else:
        submitted_answers = [
            choices_by_id[choice_id].label
            for choice_id in submitted.get("selected_choice_ids", [])
            if choice_id in choices_by_id
        ]
    expected_answers = [choice.label for choice in choices if choice.is_correct]
    return QuizAnswerReview(
        id=answer.id,
        question_id=question.id,
        position=position + 1,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        submitted_answers=submitted_answers,
        expected_answers=expected_answers,
        score=answer.score,
        max_score=max_score,
        is_graded=answer.is_graded,
    )


@router.get(
    "/sessions/{session_id}/participants/{participant_id}/answers",
    response_model=list[QuizAnswerReview],
)
def list_participant_answers(
    session_id: int,
    participant_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizAnswerReview]:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les réponses sont disponibles une fois le quiz terminé",
        )
    participant = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.id == participant_id,
            QuizParticipant.session_id == quiz_session.id,
        )
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant introuvable",
        )
    rows = list(
        session.execute(
            select(QuizAnswer, Question)
            .join(Question, Question.id == QuizAnswer.question_id)
            .where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    question_order = {
        question_id: position
        for position, question_id in enumerate(
            session_question_ids(quiz_session, session, participant)
        )
    }
    question_points = session_question_points(quiz_session, session, participant)
    rows.sort(key=lambda row: question_order[row[1].id])
    question_ids = [question.id for _, question in rows]
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    if question_ids:
        for choice in session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id.in_(question_ids))
            .order_by(QuestionChoice.position, QuestionChoice.id)
        ):
            choices_by_question[choice.question_id].append(choice)
    return [
        answer_review(
            answer,
            question,
            question_order[question.id],
            choices_by_question[question.id],
            question_points.get(question.id, 0),
        )
        for answer, question in rows
    ]


@router.get(
    "/student/history",
    response_model=list[StudentQuizHistoryItem],
)
def list_student_quiz_history(
    student: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> list[StudentQuizHistoryItem]:
    membership_id = session.scalar(
        select(Student.id).where(Student.account_id == student.id)
    )
    if membership_id is None:
        return []
    rows = list(
        session.execute(
            select(QuizSession, QuizParticipant)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizParticipant.student_id == membership_id,
                QuizSession.status == "finished",
                QuizSession.started_at.is_not(None),
                Quiz.mode == "exam",
            )
            .order_by(QuizSession.started_at.desc(), QuizSession.id.desc())
        )
    )
    history: list[StudentQuizHistoryItem] = []
    for quiz_session, participant in rows:
        question_ids = session_question_ids(quiz_session, session, participant)
        questions_by_id = {
            question.id: question
            for question in session.scalars(
                select(Question).where(Question.id.in_(question_ids))
            )
        }
        answers_by_question = {
            answer.question_id: answer
            for answer in session.scalars(
                select(QuizAnswer).where(
                    QuizAnswer.session_id == quiz_session.id,
                    QuizAnswer.participant_id == participant.id,
                )
            )
        }
        choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
        if question_ids:
            for choice in session.scalars(
                select(QuestionChoice)
                .where(QuestionChoice.question_id.in_(question_ids))
                .order_by(QuestionChoice.position, QuestionChoice.id)
            ):
                choices_by_question[choice.question_id].append(choice)
        answers = []
        for position, question_id in enumerate(question_ids):
            question = questions_by_id.get(question_id)
            if question is None:
                continue
            question_choices = choices_by_question[question.id]
            answer = answers_by_question.get(question.id)
            if answer is not None:
                review = answer_review(
                    answer,
                    question,
                    position,
                    question_choices,
                    0,
                )
                submitted_answers = review.submitted_answers
            else:
                submitted_answers = []
            answers.append(
                StudentQuizHistoryAnswer(
                    question_id=question.id,
                    position=position + 1,
                    prompt=question.prompt,
                    difficulty=question.difficulty,
                    answer_mode=question.answer_mode,
                    submitted_answers=submitted_answers,
                    expected_answers=[
                        choice.label for choice in question_choices if choice.is_correct
                    ],
                )
            )
        history.append(
            StudentQuizHistoryItem(
                session_id=quiz_session.id,
                quiz_title=quiz_session.quiz_title or "Quiz",
                class_name=quiz_session.class_name,
                started_at=quiz_session.started_at,
                answers=answers,
            )
        )
    return history


@router.post(
    "/sessions/{session_id}/answers/{answer_id}/grade",
    response_model=QuizAnswerReview,
)
def grade_written_answer(
    session_id: int,
    answer_id: int,
    payload: QuizAnswerGrade,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizAnswerReview:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La correction est disponible une fois le quiz terminé",
        )
    row = session.execute(
        select(QuizAnswer, Question)
        .join(Question, Question.id == QuizAnswer.question_id)
        .where(
            QuizAnswer.id == answer_id,
            QuizAnswer.session_id == quiz_session.id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Réponse introuvable",
        )
    answer, question = row
    participant = session.get(QuizParticipant, answer.participant_id)
    question_ids = (
        session_question_ids(quiz_session, session, participant)
        if participant is not None
        else []
    )
    if question.id not in question_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La question ne fait pas partie de cette session",
        )
    position = question_ids.index(question.id)
    if question.answer_mode != "written":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Seules les réponses rédactionnelles sont corrigées manuellement",
        )
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id == question.id)
            .order_by(QuestionChoice.position, QuestionChoice.id)
        )
    )
    max_score = session_question_points(quiz_session, session, participant).get(
        question.id, 0
    )
    if payload.score > max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La note ne peut pas dépasser {max_score:g}",
        )
    answer.score = payload.score
    answer.is_graded = True
    session.commit()
    return answer_review(answer, question, position, choices, max_score)


@router.get(
    "/sessions/{session_id}",
    response_model=QuizSessionResponse,
)
def get_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    return session_response(quiz_session, quiz, session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status not in {"finished", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Seules les sessions terminées ou annulées peuvent être supprimées"
            ),
        )
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()
    audit_event(
        "quiz.session_deleted",
        professor_id=professor.id,
        session_id=session_id,
    )


@router.post(
    "/sessions/{session_id}/start",
    response_model=QuizSessionResponse,
)
def start_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status == "waiting":
        participants = list(
            session.scalars(
                select(QuizParticipant).where(
                    QuizParticipant.session_id == quiz_session.id
                )
            )
        )
        if not participants:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Au moins un élève doit rejoindre le quiz avant son démarrage",
            )
        quiz_session.status = "in_progress"
        quiz_session.started_at = datetime.now(UTC)
        for participant in participants:
            participant.current_position = 0
        session.commit()
        session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/pause",
    response_model=QuizSessionResponse,
)
def pause_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seul un quiz en cours peut être mis en pause",
        )
    quiz_session.status = "paused"
    quiz_session.paused_at = datetime.now(UTC)
    session.commit()
    session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/resume",
    response_model=QuizSessionResponse,
)
def resume_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "paused" or quiz_session.paused_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seul un quiz en pause peut être repris",
        )
    paused_at = quiz_session.paused_at
    if paused_at.tzinfo is None:
        paused_at = paused_at.replace(tzinfo=UTC)
    quiz_session.paused_duration_seconds = (
        quiz_session.paused_duration_seconds or 0
    ) + ceil(max(0, (datetime.now(UTC) - paused_at).total_seconds()))
    quiz_session.paused_at = None
    quiz_session.status = "in_progress"
    session.commit()
    session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/cancel",
    response_model=QuizSessionResponse,
)
def cancel_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status not in {"waiting", "in_progress", "paused"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette session ne peut plus être annulée",
        )
    quiz_session.status = "cancelled"
    quiz_session.paused_at = None
    for participant in session.scalars(
        select(QuizParticipant).where(QuizParticipant.session_id == quiz_session.id)
    ):
        participant.current_position = None
    session.commit()
    session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.get(
    "/training/classes/{class_id}/question-banks",
    response_model=list[QuestionBankResponse],
)
def list_class_training_question_banks(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBankResponse]:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    bank_ids = list(
        session.scalars(
            select(ClassTrainingQuestionBank.question_bank_id)
            .join(
                QuestionBank,
                QuestionBank.id == ClassTrainingQuestionBank.question_bank_id,
            )
            .where(
                ClassTrainingQuestionBank.class_id == class_id,
                QuestionBank.grade_level == student_class.grade_level,
            )
        )
    )
    return question_bank_responses(bank_ids, session)


@router.put(
    "/training/classes/{class_id}/question-banks",
    response_model=list[QuestionBankResponse],
)
def update_class_training_question_banks(
    class_id: int,
    payload: TrainingQuestionBankSelection,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBankResponse]:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    banks = list(
        session.scalars(
            select(QuestionBank).where(
                QuestionBank.id.in_(payload.question_bank_ids),
                QuestionBank.owner_id == professor.id,
            )
        )
    )
    if len(banks) != len(payload.question_bank_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une ou plusieurs banques de questions sont invalides",
        )
    if any(bank.grade_level != student_class.grade_level for bank in banks):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Les banques d’entraînement doivent correspondre au niveau de la classe"
            ),
        )
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.class_id == class_id
        )
    )
    session.add_all(
        ClassTrainingQuestionBank(
            class_id=class_id,
            question_bank_id=question_bank_id,
        )
        for question_bank_id in payload.question_bank_ids
    )
    session.commit()
    return question_bank_responses(payload.question_bank_ids, session)


@router.get("/training", response_model=list[QuestionBankResponse])
def list_student_training_question_banks(
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> list[QuestionBankResponse]:
    bank_ids = list(
        session.scalars(
            select(ClassTrainingQuestionBank.question_bank_id)
            .join(Student, Student.class_id == ClassTrainingQuestionBank.class_id)
            .join(StudentClass, StudentClass.id == Student.class_id)
            .join(
                QuestionBank,
                QuestionBank.id == ClassTrainingQuestionBank.question_bank_id,
            )
            .where(
                Student.account_id == student.id,
                QuestionBank.grade_level == StudentClass.grade_level,
            )
        )
    )
    return question_bank_responses(bank_ids, session)


@router.post(
    "/training/{question_bank_id}/start",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_training_quiz(
    question_bank_id: int,
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> StudentQuizJoinResponse:
    membership = session.execute(
        select(Student, StudentClass)
        .join(StudentClass, StudentClass.id == Student.class_id)
        .where(Student.account_id == student.id)
    ).first()
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail="L’élève doit être affecté à une classe",
        )
    class_student, student_class = membership
    bank = session.scalar(
        select(QuestionBank)
        .join(
            ClassTrainingQuestionBank,
            ClassTrainingQuestionBank.question_bank_id == QuestionBank.id,
        )
        .where(
            QuestionBank.id == question_bank_id,
            QuestionBank.owner_id == student.owner_id,
            QuestionBank.grade_level == student_class.grade_level,
            ClassTrainingQuestionBank.class_id == student_class.id,
        )
    )
    if bank is None:
        raise HTTPException(status_code=404, detail="Entraînement introuvable")
    question_ids = draw_training_question_ids(bank.id, session)
    if not question_ids:
        raise HTTPException(
            status_code=409,
            detail="Cette banque ne contient encore aucune question",
        )
    quiz = training_profile_quiz(student.owner_id, session)
    discard_previous_training_sessions(student, class_student, session)
    now = datetime.now(UTC)
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        quiz_title=bank.chapter,
        source_language=quiz.source_language,
        duration_seconds=28800,
        allow_previous_questions=False,
        same_questions_for_all=False,
        class_id=student_class.id,
        class_name=student_class.name,
        join_code=generate_join_code(session),
        status="in_progress",
        started_at=now,
    )
    session.add(quiz_session)
    session.flush()
    session.add_all(
        QuizSessionQuestion(
            session_id=quiz_session.id,
            question_id=question_id,
            position=position,
            points=0,
        )
        for position, question_id in enumerate(question_ids)
    )
    participant_token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_id=class_student.id,
        student_identifier=student.identifier,
        student_display_name=student.display_name,
        access_token_hash=participant_token_hash(participant_token),
        current_position=0,
    )
    session.add(participant)
    session.commit()
    state = student_state_response(quiz_session, quiz, participant, session)
    return StudentQuizJoinResponse(
        **state.model_dump(),
        participant_token=participant_token,
    )


def makeup_session_response(
    makeup: MakeupSession, session: DbSession
) -> MakeupSessionResponse:
    quizzes = list(
        session.scalars(
            select(Quiz)
            .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
            .where(MakeupSessionQuiz.session_id == makeup.id)
            .order_by(Quiz.title, Quiz.id)
        )
    )
    participant_count = session.scalar(
        select(func.count(QuizParticipant.id))
        .join(QuizSession, QuizSession.id == QuizParticipant.session_id)
        .where(QuizSession.makeup_session_id == makeup.id)
    )
    return MakeupSessionResponse(
        id=makeup.id,
        class_id=makeup.class_id,
        class_name=makeup.class_name,
        join_code=makeup.join_code,
        status=makeup.status,
        quizzes=[
            MakeupQuizOption(
                id=quiz.id,
                title=quiz.title,
                duration_seconds=quiz.duration_seconds,
            )
            for quiz in quizzes
        ],
        participant_count=participant_count or 0,
        created_at=makeup.created_at,
    )


def owned_makeup_session(
    session_id: int, professor: ProfessorUser, session: DbSession
) -> MakeupSession:
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.id == session_id,
            MakeupSession.owner_id == professor.id,
        )
    )
    if makeup is None:
        raise HTTPException(status_code=404, detail="Session de rattrapage introuvable")
    return makeup


@router.get("/makeup/sessions", response_model=list[MakeupSessionResponse])
def list_makeup_sessions(
    professor: ProfessorUser, session: DbSession
) -> list[MakeupSessionResponse]:
    makeups = list(
        session.scalars(
            select(MakeupSession)
            .where(MakeupSession.owner_id == professor.id)
            .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
        )
    )
    return [makeup_session_response(item, session) for item in makeups]


@router.post(
    "/makeup/sessions",
    response_model=MakeupSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_makeup_session(
    payload: MakeupSessionCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == payload.class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    quiz_ids = set(payload.quiz_ids)
    quizzes = list(
        session.scalars(
            select(Quiz).where(
                Quiz.id.in_(quiz_ids),
                Quiz.owner_id == professor.id,
                Quiz.mode == "exam",
            )
        )
    )
    if student_class is None or len(quizzes) != len(quiz_ids):
        raise HTTPException(status_code=422, detail="Classe ou quiz invalide")
    makeup = MakeupSession(
        owner_id=professor.id,
        class_id=student_class.id,
        class_name=student_class.name,
        join_code=generate_join_code(session),
        status="waiting",
    )
    session.add(makeup)
    session.flush()
    session.add_all(
        MakeupSessionQuiz(session_id=makeup.id, quiz_id=quiz_id) for quiz_id in quiz_ids
    )
    session.commit()
    return makeup_session_response(makeup, session)


@router.post(
    "/makeup/sessions/{session_id}/{action}",
    response_model=MakeupSessionResponse,
)
def control_makeup_session(
    session_id: int,
    action: str,
    professor: ProfessorUser,
    session: DbSession,
) -> MakeupSessionResponse:
    makeup = owned_makeup_session(session_id, professor, session)
    allowed = {
        "start": ("waiting", "in_progress"),
        "pause": ("in_progress", "paused"),
        "resume": ("paused", "in_progress"),
        "finish": ("in_progress", "finished"),
        "cancel": ("waiting", "cancelled"),
    }
    if action not in allowed:
        raise HTTPException(status_code=404)
    expected, target = allowed[action]
    if makeup.status != expected:
        raise HTTPException(
            status_code=409, detail="Action impossible pour cette session"
        )
    children = list(
        session.scalars(
            select(QuizSession).where(QuizSession.makeup_session_id == makeup.id)
        )
    )
    if action == "start" and not children:
        raise HTTPException(
            status_code=409,
            detail="Au moins un élève doit choisir un quiz avant le démarrage",
        )
    now = datetime.now(UTC)
    for child in children:
        child.status = target
        if action == "start":
            child.started_at = now
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = 0
        elif action == "pause":
            child.paused_at = now
        elif action == "resume" and child.paused_at is not None:
            paused_at = child.paused_at
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=UTC)
            child.paused_duration_seconds += ceil(
                max(0, (now - paused_at).total_seconds())
            )
            child.paused_at = None
        elif action == "finish":
            quiz = session.get(Quiz, child.quiz_id)
            if quiz is not None:
                compute_final_scores(child, session)
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = None
    makeup.status = target
    session.commit()
    return makeup_session_response(makeup, session)


@router.post(
    "/makeup/join",
    response_model=MakeupSessionJoinResponse,
)
def join_makeup_session(
    payload: QuizJoin,
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> MakeupSessionJoinResponse:
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == payload.join_code,
            MakeupSession.status == "waiting",
        )
    )
    if makeup is None:
        raise HTTPException(
            status_code=403, detail="Impossible de rejoindre ce rattrapage"
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=403, detail="Impossible de rejoindre ce rattrapage"
        )
    eligible = list(
        session.scalars(
            select(Quiz)
            .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
            .where(
                MakeupSessionQuiz.session_id == makeup.id,
                Quiz.id.in_(
                    select(QuizSession.quiz_id)
                    .join(
                        QuizParticipant,
                        QuizParticipant.session_id == QuizSession.id,
                    )
                    .where(
                        QuizParticipant.student_id == membership.id,
                        QuizSession.status == "finished",
                    )
                ),
            )
            .order_by(Quiz.title, Quiz.id)
        )
    )
    return MakeupSessionJoinResponse(
        join_code=makeup.join_code,
        class_name=makeup.class_name,
        status="waiting",
        quizzes=[
            MakeupQuizOption(
                id=quiz.id,
                title=quiz.title,
                duration_seconds=quiz.duration_seconds,
            )
            for quiz in eligible
        ],
    )


@router.post(
    "/makeup/{join_code}/select",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def select_makeup_quiz(
    join_code: str,
    payload: MakeupQuizSelection,
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> StudentQuizJoinResponse:
    makeup = session.scalar(
        select(MakeupSession).where(
            MakeupSession.join_code == join_code.strip().upper(),
            MakeupSession.status == "waiting",
        )
    )
    if makeup is None:
        raise HTTPException(
            status_code=409, detail="Ce rattrapage n’accepte plus de choix"
        )
    membership = session.scalar(
        select(Student).where(
            Student.class_id == makeup.class_id,
            Student.account_id == account.id,
        )
    )
    quiz = session.scalar(
        select(Quiz)
        .join(MakeupSessionQuiz, MakeupSessionQuiz.quiz_id == Quiz.id)
        .where(
            MakeupSessionQuiz.session_id == makeup.id,
            Quiz.id == payload.quiz_id,
        )
    )
    passed = (
        session.scalar(
            select(QuizParticipant.id)
            .join(QuizSession, QuizSession.id == QuizParticipant.session_id)
            .where(
                QuizParticipant.student_id == (membership.id if membership else -1),
                QuizSession.quiz_id == payload.quiz_id,
                QuizSession.status == "finished",
            )
            .limit(1)
        )
        is not None
    )
    existing = session.scalar(
        select(QuizSession.id)
        .join(QuizParticipant, QuizParticipant.session_id == QuizSession.id)
        .where(
            QuizSession.makeup_session_id == makeup.id,
            QuizParticipant.student_id == (membership.id if membership else -1),
        )
    )
    if membership is None or quiz is None or not passed or existing is not None:
        raise HTTPException(status_code=409, detail="Sélection de quiz invalide")
    child = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        same_questions_for_all=False,
        class_id=makeup.class_id,
        class_name=makeup.class_name,
        join_code=generate_join_code(session),
        status="waiting",
        makeup_session_id=makeup.id,
    )
    session.add(child)
    session.flush()
    existing_draw_rows = list(
        session.execute(
            select(
                QuizSessionStudentQuestion.session_id,
                QuizSessionStudentQuestion.question_id,
            )
            .join(
                QuizSession,
                QuizSession.id == QuizSessionStudentQuestion.session_id,
            )
            .where(
                QuizSession.makeup_session_id == makeup.id,
                QuizSession.quiz_id == quiz.id,
            )
        )
    )
    questions_by_session: dict[int, list[int]] = defaultdict(list)
    for existing_session_id, question_id in existing_draw_rows:
        questions_by_session[existing_session_id].append(question_id)
    used_draws = {
        tuple(sorted(question_ids)) for question_ids in questions_by_session.values()
    }
    question_ids = draw_unique_question_ids(quiz, session, used_draws)
    points = points_for_drawn_questions(quiz, question_ids, session)
    session.add_all(
        QuizSessionStudentQuestion(
            session_id=child.id,
            student_id=membership.id,
            student_identifier=membership.identifier,
            question_id=question_id,
            position=position,
            points=points[question_id],
        )
        for position, question_id in enumerate(question_ids)
    )
    token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=child.id,
        student_id=membership.id,
        student_identifier=membership.identifier,
        student_display_name=membership.display_name,
        access_token_hash=participant_token_hash(token),
    )
    session.add(participant)
    session.commit()
    state = student_state_response(child, quiz, participant, session)
    return StudentQuizJoinResponse(**state.model_dump(), participant_token=token)


@router.get("/{quiz_id}/preview", response_model=list[QuestionResponse])
def preview_quiz(
    quiz_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionResponse]:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != "exam":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz introuvable",
        )
    return load_question_responses(draw_question_ids(quiz, session), session)


@router.post(
    "/{quiz_id}/update",
    response_model=QuizResponse,
)
def update_quiz(
    quiz_id: int,
    payload: QuizCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizResponse:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != "exam":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz introuvable",
        )
    active_session_id = session.scalar(
        select(QuizSession.id)
        .where(
            QuizSession.quiz_id == quiz.id,
            QuizSession.status.in_(["waiting", "in_progress", "paused"]),
        )
        .limit(1)
    )
    if active_session_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un quiz avec une session active ne peut pas être modifié",
        )
    validate_bank_selection(payload, professor, session)
    quiz.title = payload.title
    quiz.mode = "exam"
    quiz.source_language = payload.source_language
    quiz.question_count = payload.question_count
    quiz.duration_seconds = payload.duration_seconds
    quiz.allow_previous_questions = payload.allow_previous_questions
    quiz.same_questions_for_all = False
    quiz.easy_question_count = payload.easy_question_count
    quiz.medium_question_count = payload.medium_question_count
    quiz.hard_question_count = payload.hard_question_count
    quiz.easy_points = payload.easy_points
    quiz.medium_points = payload.medium_points
    quiz.hard_points = payload.hard_points
    session.execute(delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id == quiz.id))
    session.add_all(
        QuizQuestionBank(quiz_id=quiz.id, question_bank_id=bank_id)
        for bank_id in payload.question_bank_ids
    )
    session.commit()
    session.refresh(quiz)
    return quiz_response(quiz, session)


@router.post(
    "/{quiz_id}/launch",
    response_model=QuizSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def launch_quiz(
    quiz_id: int,
    payload: QuizLaunch,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != "exam":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un entraînement est lancé directement par l’élève",
        )
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == payload.class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La classe sélectionnée est invalide",
        )
    students = list(
        session.scalars(
            select(Student).where(
                Student.class_id == student_class.id,
                Student.account_id.is_not(None),
            )
        )
    )
    if not students:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La classe doit contenir au moins un élève",
        )
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        same_questions_for_all=False,
        class_id=student_class.id,
        class_name=student_class.name,
        join_code=generate_join_code(session),
        status="waiting",
    )
    session.add(quiz_session)
    session.flush()
    assignments: list[QuizSessionStudentQuestion] = []
    used_draws: set[tuple[int, ...]] = set()
    for student in students:
        question_ids = draw_unique_question_ids(quiz, session, used_draws)
        assigned_points = points_for_drawn_questions(quiz, question_ids, session)
        assignments.extend(
            QuizSessionStudentQuestion(
                session_id=quiz_session.id,
                student_id=student.id,
                student_identifier=student.identifier,
                question_id=question_id,
                position=position,
                points=assigned_points[question_id],
            )
            for position, question_id in enumerate(question_ids)
        )
    session.add_all(assignments)
    session.commit()
    session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/join",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_quiz(
    payload: QuizJoin,
    request: Request,
    session: DbSession,
    account: StudentAccount = Depends(current_student),
) -> StudentQuizJoinResponse:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == payload.join_code, Quiz.mode == "exam")
    ).first()
    if row is None:
        reject_quiz_join(request, session, "join:unknown")
    quiz_session, quiz = row
    join_subject = f"join:session:{quiz_session.id}"
    if quiz_session.status != "waiting":
        reject_quiz_join(request, session, join_subject)
    if quiz_session.class_id is None:
        reject_quiz_join(request, session, join_subject)
    student = session.scalar(
        select(Student).where(
            Student.class_id == quiz_session.class_id,
            Student.account_id == account.id,
        )
    )
    if student is None:
        reject_quiz_join(request, session, join_subject)
    if quiz_session.same_questions_for_all is False:
        assigned_question_id = session.scalar(
            select(QuizSessionStudentQuestion.question_id)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .limit(1)
        )
        if assigned_question_id is None:
            reject_quiz_join(request, session, join_subject)
        session.execute(
            update(QuizSessionStudentQuestion)
            .where(
                QuizSessionStudentQuestion.session_id == quiz_session.id,
                QuizSessionStudentQuestion.student_id == student.id,
            )
            .values(student_identifier=student.identifier)
        )
    existing = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.student_id == student.id,
        )
    )
    if existing is not None:
        reject_quiz_join(request, session, join_subject)
    if quiz_session.same_questions_for_all is not False:
        common_questions = list(
            session.execute(
                select(
                    QuizSessionQuestion.question_id,
                    QuizSessionQuestion.points,
                )
                .where(QuizSessionQuestion.session_id == quiz_session.id)
                .order_by(QuizSessionQuestion.position)
            ).all()
        )
        if not common_questions:
            reject_quiz_join(request, session, join_subject)
        randomizer.shuffle(common_questions)
        session.add_all(
            QuizSessionStudentQuestion(
                session_id=quiz_session.id,
                student_id=student.id,
                student_identifier=student.identifier,
                question_id=question_id,
                position=position,
                points=points,
            )
            for position, (question_id, points) in enumerate(common_questions)
        )
    participant_token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_id=student.id,
        student_identifier=student.identifier,
        student_display_name=student.display_name,
        access_token_hash=participant_token_hash(participant_token),
    )
    session.add(participant)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        reject_quiz_join(request, session, join_subject)
    state = student_state_response(quiz_session, quiz, participant, session)
    return StudentQuizJoinResponse(
        **state.model_dump(),
        participant_token=participant_token,
    )


@router.get(
    "/student/sessions/{join_code}",
    response_model=StudentQuizStateResponse,
)
def get_student_quiz_state(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    state = student_state_response(quiz_session, quiz, participant, session)
    discard_finished_training_session(quiz_session, quiz, session)
    return state


@router.post(
    "/student/sessions/{join_code}/answer",
    response_model=StudentQuizStateResponse,
)
def submit_student_answer(
    join_code: str,
    payload: StudentQuizAnswer,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le quiz n’accepte pas de réponses actuellement",
        )
    if participant.student_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="L’élève n’existe plus",
        )
    question_id = current_question_id(quiz_session, participant, session)
    if question_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune question en cours",
        )
    existing_answer = session.scalar(
        select(QuizAnswer).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.participant_id == participant.id,
            QuizAnswer.question_id == question_id,
        )
    )
    question = session.get(Question, question_id)
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id == question_id)
            .order_by(QuestionChoice.position)
        )
    )
    choices_by_id = {choice.id: choice for choice in choices}
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La question actuelle n’est pas disponible",
        )

    feedback: TrainingFeedback | None = None
    if question.answer_mode == "written":
        written_answer = (payload.written_answer or "").strip()
        if not written_answer or payload.selected_choice_ids is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Une réponse rédactionnelle est requise",
            )
        answer_data = {"written_answer": written_answer}
        expected_answer = next(
            (choice.label for choice in choices if choice.is_correct),
            "",
        )
        if quiz.mode == "training":
            feedback = TrainingFeedback(
                question_id=question.id,
                is_correct=written_answer.casefold() == expected_answer.casefold(),
                correct_choice_ids=[],
                expected_answer=expected_answer,
            )
    else:
        if payload.selected_choice_ids is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Au moins une proposition doit être sélectionnée",
            )
        selected_ids = list(dict.fromkeys(payload.selected_choice_ids or []))
        if payload.written_answer is not None or (
            question.answer_mode == "single" and len(selected_ids) != 1
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La réponse envoyée ne correspond pas au type de la question",
            )
        if any(choice_id not in choices_by_id for choice_id in selected_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Une proposition sélectionnée est invalide",
            )
        answer_data = {"selected_choice_ids": selected_ids}
        if quiz.mode == "training":
            correct_ids = [choice.id for choice in choices if choice.is_correct]
            feedback = TrainingFeedback(
                question_id=question.id,
                is_correct=set(selected_ids) == set(correct_ids),
                correct_choice_ids=correct_ids,
            )

    if existing_answer is None:
        session.add(
            QuizAnswer(
                session_id=quiz_session.id,
                participant_id=participant.id,
                question_id=question_id,
                answer_data=json.dumps(answer_data, ensure_ascii=False),
                score=0,
                is_graded=False,
            )
        )
    else:
        existing_answer.answer_data = json.dumps(answer_data, ensure_ascii=False)
        existing_answer.score = 0
        existing_answer.is_graded = False
    total_questions = len(session_question_ids(quiz_session, session, participant))
    if (
        participant.current_position is not None
        and participant.current_position + 1 < total_questions
    ):
        participant.current_position += 1
    else:
        participant.current_position = None
    session.flush()
    unfinished_count = session.scalar(
        select(func.count(QuizParticipant.id)).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.current_position.is_not(None),
        )
    )
    if unfinished_count == 0:
        quiz_session.status = "finished"
        if quiz.mode == "exam":
            compute_final_scores(quiz_session, session)
    session.commit()
    state = student_state_response(quiz_session, quiz, participant, session)
    if feedback is not None:
        state.training_feedback = feedback
    discard_finished_training_session(quiz_session, quiz, session)
    return state


@router.post(
    "/student/sessions/{join_code}/navigate",
    response_model=StudentQuizStateResponse,
)
def navigate_student_quiz(
    join_code: str,
    payload: StudentQuizNavigation,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> StudentQuizStateResponse:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    target_position = payload.question_number - 1
    allow_previous_questions = quiz_session.allow_previous_questions
    if allow_previous_questions is None:
        allow_previous_questions = quiz.allow_previous_questions
    if (
        quiz_session.status != "in_progress"
        or not allow_previous_questions
        or participant.current_position is None
        or target_position >= participant.current_position
        or target_position < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le retour à cette question n’est pas autorisé",
        )
    participant.current_position = target_position
    session.commit()
    return student_state_response(quiz_session, quiz, participant, session)


@router.post(
    "/student/sessions/{join_code}/violation",
    status_code=status.HTTP_204_NO_CONTENT,
)
def report_student_violation(
    join_code: str,
    payload: StudentQuizViolation,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_violation_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    now = datetime.now(UTC)
    last_violation_at = participant.last_violation_at
    if last_violation_at is not None and last_violation_at.tzinfo is None:
        last_violation_at = last_violation_at.replace(tzinfo=UTC)
    if (
        participant.last_violation_type == payload.event_type
        and last_violation_at is not None
        and (now - last_violation_at).total_seconds() < VIOLATION_DEDUPLICATION_SECONDS
    ):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    participant.violation_count += 1
    participant.last_violation_type = payload.event_type
    participant.last_violation_at = now
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/student/sessions/{join_code}/questions/{question_id}/image")
def get_student_question_image(
    join_code: str,
    question_id: int,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la question introuvable",
        )
    if current_question_id(quiz_session, participant, session) != question_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la question introuvable",
        )
    question = session.get(Question, question_id)
    if (
        question is None
        or question.image_data is None
        or question.image_content_type is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la question introuvable",
        )
    return Response(
        content=question.image_data,
        media_type=question.image_content_type,
    )


@router.get("/student/sessions/{join_code}/choices/{choice_id}/image")
def get_student_choice_image(
    join_code: str,
    choice_id: int,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    quiz_session, quiz, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la réponse introuvable",
        )
    question_id = current_question_id(quiz_session, participant, session)
    choice = session.scalar(
        select(QuestionChoice).where(
            QuestionChoice.id == choice_id,
            QuestionChoice.question_id == question_id,
        )
    )
    if choice is None or choice.image_data is None or choice.image_content_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image de la réponse introuvable",
        )
    return Response(
        content=choice.image_data,
        media_type=choice.image_content_type,
    )
