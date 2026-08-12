import csv
import io
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil, comb
from random import SystemRandom
from secrets import token_urlsafe
from statistics import median
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
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.audit import audit_event
from app.class_names import format_class_name
from app.dependencies import DbSession, ProfessorUser
from app.grading import compute_final_scores
from app.models import (
    ClassTrainingQuestionBank,
    MakeupSession,
    MakeupSessionQuiz,
    MakeupSessionSelection,
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizJoinCode,
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
    TrainingHistoryItem,
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
    selected: list[Question] = []
    for difficulty, count in requested.items():
        if count > 0:
            selected.extend(
                randomizer.sample(candidates_by_difficulty[difficulty], count)
            )
    question_ids = [question.id for question in selected]
    randomizer.shuffle(question_ids)
    return question_ids


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


def quiz_responses(quizzes: list[Quiz], session: DbSession) -> list[QuizResponse]:
    if not quizzes:
        return []
    banks_by_quiz: dict[int, list[QuizBankSummary]] = {quiz.id: [] for quiz in quizzes}
    rows = session.execute(
        select(
            QuizQuestionBank.quiz_id,
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
        .where(QuizQuestionBank.quiz_id.in_(banks_by_quiz))
        .group_by(QuizQuestionBank.quiz_id, QuestionBank.id)
        .order_by(
            QuizQuestionBank.quiz_id,
            QuestionBank.grade_level,
            QuestionBank.chapter,
        )
    )
    for quiz_id, bank, count, easy_count, medium_count, hard_count in rows:
        banks_by_quiz[quiz_id].append(
            QuizBankSummary(
                id=bank.id,
                grade_level=bank.grade_level,
                chapter=bank.chapter,
                question_count=count,
                easy_question_count=easy_count or 0,
                medium_question_count=medium_count or 0,
                hard_question_count=hard_count or 0,
            )
        )
    return [
        QuizResponse(
            id=quiz.id,
            mode=quiz.mode,
            title=quiz.title,
            source_language=quiz.source_language,
            question_count=quiz.question_count,
            duration_seconds=quiz.duration_seconds,
            allow_previous_questions=quiz.allow_previous_questions,
            allow_negative_points=quiz.allow_negative_points,
            same_questions_for_all=quiz.same_questions_for_all,
            easy_question_count=quiz.easy_question_count,
            medium_question_count=quiz.medium_question_count,
            hard_question_count=quiz.hard_question_count,
            question_banks=banks_by_quiz[quiz.id],
            created_at=quiz.created_at,
        )
        for quiz in quizzes
    ]


def quiz_response(quiz: Quiz, session: DbSession) -> QuizResponse:
    return quiz_responses([quiz], session)[0]


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
        allow_negative_points=False,
        same_questions_for_all=False,
        easy_question_count=0,
        medium_question_count=0,
        hard_question_count=0,
        easy_points=0,
        medium_points=0,
        hard_points=0,
    )
    session.add(quiz)
    try:
        session.flush()
        session.add(TrainingQuizProfile(owner_id=owner_id, quiz_id=quiz.id))
        session.flush()
    except IntegrityError:
        # A concurrent request created the training profile first; callers
        # have only performed reads so far, so rolling back is safe.
        session.rollback()
        quiz = session.scalar(
            select(Quiz)
            .join(TrainingQuizProfile, TrainingQuizProfile.quiz_id == Quiz.id)
            .where(TrainingQuizProfile.owner_id == owner_id)
        )
        if quiz is None:
            raise
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
    question_ids = session_question_ids(quiz_session, session, participant)
    if not question_ids:
        return {}
    maximums = dict(
        session.execute(
            select(
                QuestionChoice.question_id,
                func.sum(
                    case((QuestionChoice.points > 0, QuestionChoice.points), else_=0)
                ),
            )
            .where(QuestionChoice.question_id.in_(question_ids))
            .group_by(QuestionChoice.question_id)
        ).all()
    )
    return {
        question_id: float(maximums.get(question_id) or 0)
        for question_id in question_ids
    }


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


def participant_maximum_scores(
    quiz_session: QuizSession,
    participants: list[QuizParticipant],
    session: DbSession,
) -> dict[int, float]:
    return {
        participant.id: round(
            sum(session_question_points(quiz_session, session, participant).values()),
            2,
        )
        for participant in participants
    }


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    expire_quiz_session(quiz_session, quiz, session)
    participant_query = select(QuizParticipant).where(
        QuizParticipant.session_id == quiz_session.id
    )
    if quiz_session.status in {"waiting", "in_progress", "paused"}:
        participant_query = participant_query.where(QuizParticipant.left_at.is_(None))
    participants = list(
        session.scalars(
            participant_query.order_by(QuizParticipant.joined_at, QuizParticipant.id)
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
    maximum_scores = participant_maximum_scores(quiz_session, participants, session)
    median_maximum_score = (
        float(median(maximum_scores.values())) if maximum_scores else 0
    )
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
        class_name=quiz_session_class_name(quiz_session, session),
        join_code=quiz_session.join_code,
        status=quiz_session.status,
        participant_count=len(participants),
        median_maximum_score=median_maximum_score,
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
                maximum_score=maximum_scores[participant.id],
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
        grades_published_at=quiz_session.grades_published_at,
    )


def student_session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizSessionResponse:
    return StudentQuizSessionResponse(
        quiz_title=quiz_session.quiz_title or quiz.title,
        source_language=quiz_session.source_language or quiz.source_language,
        class_name=quiz_session_class_name(quiz_session, session),
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
    for quiz_session, quiz in rows:
        expire_quiz_session(quiz_session, quiz, session)


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


def delete_makeup_session_records(
    makeup_session_id: int,
    session: DbSession,
) -> None:
    child_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                QuizSession.makeup_session_id == makeup_session_id
            )
        )
    )
    delete_quiz_session_records(child_ids, session)
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.session_id == makeup_session_id
        )
    )
    session.execute(
        delete(MakeupSessionQuiz).where(
            MakeupSessionQuiz.session_id == makeup_session_id
        )
    )
    session.execute(delete(MakeupSession).where(MakeupSession.id == makeup_session_id))


def quiz_session_class_name(quiz_session: QuizSession, session: DbSession) -> str:
    if quiz_session.class_id is None:
        return quiz_session.class_name
    student_class = session.get(StudentClass, quiz_session.class_id)
    if student_class is None:
        return quiz_session.class_name
    return format_class_name(student_class.grade_level, student_class.name)


def discard_finished_training_session(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> None:
    # Finished training sessions are the source of the student's history.
    return


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
                QuizSession.status != "finished",
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
                Quiz.mode == "exam",
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
        else f"{purpose}:code:{normalized_join_code}"
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
            QuizParticipant.left_at.is_(None),
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
        allow_code_execution=question.allow_code_execution,
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
    answered_question_ids = set(
        session.scalars(
            select(QuizAnswer.question_id).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    has_answered = question_id is not None and question_id in answered_question_ids
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
    if existing_answer is not None:
        try:
            saved_answer = json.loads(existing_answer.answer_data)
        except TypeError, ValueError:
            saved_answer = {}
        if not isinstance(saved_answer, dict):
            saved_answer = {}
    else:
        saved_answer = {}
    answered_count = len(answered_question_ids)
    accessible_positions = {
        position
        for position, assigned_question_id in enumerate(question_ids)
        if assigned_question_id in answered_question_ids
    }
    if accessible_positions:
        next_position = max(accessible_positions) + 1
        if next_position < len(question_ids):
            accessible_positions.add(next_position)
    if participant.current_position is not None:
        accessible_positions.add(participant.current_position)
    state = StudentQuizStateResponse(
        **student_session_response(
            quiz_session, quiz, participant, session
        ).model_dump(),
        question_number=(
            participant.current_position + 1
            if participant.current_position is not None
            and quiz_session.status == "in_progress"
            else None
        ),
        total_questions=len(question_ids),
        has_answered=has_answered,
        answered_count=answered_count,
        allow_previous_questions=(
            quiz_session.allow_previous_questions
            if quiz_session.allow_previous_questions is not None
            else quiz.allow_previous_questions
        ),
        accessible_question_numbers=[
            position + 1 for position in sorted(accessible_positions)
        ],
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
    if quiz.mode == "training" and quiz_session.status == "finished":
        score, maximum, pending = training_result(quiz_session, participant, session)
        state.potential_score = score
        state.potential_maximum_score = maximum
        state.pending_manual_review_count = pending
    return state


def training_result(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
) -> tuple[float, float, int]:
    question_ids = session_question_ids(quiz_session, session, participant)
    if not question_ids:
        return 0.0, 0.0, 0
    questions = {
        question.id: question
        for question in session.scalars(
            select(Question).where(Question.id.in_(question_ids))
        )
    }
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    for choice in session.scalars(
        select(QuestionChoice).where(QuestionChoice.question_id.in_(question_ids))
    ):
        choices_by_question[choice.question_id].append(choice)
    answers = {
        answer.question_id: answer
        for answer in session.scalars(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    }
    score = 0.0
    maximum = 0.0
    pending = 0
    for question_id in question_ids:
        question = questions.get(question_id)
        if question is None:
            continue
        if question.answer_mode == "written":
            if question_id in answers:
                pending += 1
            continue
        choices = choices_by_question[question_id]
        maximum += sum(choice.points for choice in choices if choice.points > 0)
        answer = answers.get(question_id)
        if answer is None:
            continue
        try:
            answer_data = json.loads(answer.answer_data)
        except TypeError, ValueError:
            answer_data = {}
        selected_ids = set(
            answer_data.get("selected_choice_ids", [])
            if isinstance(answer_data, dict)
            else []
        )
        score += sum(
            choice.points
            for choice in choices
            if choice.id in selected_ids and choice.points >= 0
        )
    return round(score, 2), round(maximum, 2), pending


def generate_join_code(session: DbSession) -> str:
    for _ in range(20):
        code = "".join(randomizer.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        reserved = session.execute(
            sqlite_insert(QuizJoinCode)
            .values(code=code)
            .on_conflict_do_nothing(index_elements=[QuizJoinCode.code])
        )
        if reserved.rowcount == 1:
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
            .order_by(Quiz.title, Quiz.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return quiz_responses(quizzes, session)


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
        allow_negative_points=payload.allow_negative_points,
        same_questions_for_all=False,
        easy_question_count=payload.easy_question_count,
        medium_question_count=payload.medium_question_count,
        hard_question_count=payload.hard_question_count,
        easy_points=0,
        medium_points=0,
        hard_points=0,
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
    obsolete_cancelled_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.status == "cancelled",
                ~QuizSession.id.in_(select(QuizAnswer.session_id)),
            )
        )
    )
    if obsolete_cancelled_ids:
        delete_quiz_session_records(obsolete_cancelled_ids, session)
        session.commit()
    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            Quiz.owner_id == professor.id,
            Quiz.mode == "exam",
            QuizSession.status.in_(["waiting", "in_progress", "paused"]),
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
                    safe_spreadsheet_cell(result.class_name or ""),
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
    try:
        submitted = json.loads(answer.answer_data)
    except TypeError, ValueError:
        submitted = {}
    if not isinstance(submitted, dict):
        submitted = {}
    choices_by_id = {choice.id: choice for choice in choices}
    if question.answer_mode == "written":
        submitted_answers = [str(submitted.get("written_answer", ""))]
        is_correct = (
            answer.score >= max_score if answer.is_graded and max_score > 0 else None
        )
    else:
        selected_choice_ids = submitted.get("selected_choice_ids", [])
        if not isinstance(selected_choice_ids, list):
            selected_choice_ids = []
        selected_choice_ids = [
            choice_id for choice_id in selected_choice_ids if type(choice_id) is int
        ]
        submitted_answers = [
            choices_by_id[choice_id].label
            for choice_id in selected_choice_ids
            if choice_id in choices_by_id
        ]
        is_correct = set(selected_choice_ids) == {
            choice.id for choice in choices if choice.is_correct
        }
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
        is_correct=is_correct,
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
    rows.sort(key=lambda row: question_order.get(row[1].id, len(question_order)))
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
            question_order.get(question.id, 0),
            choices_by_question[question.id],
            question_points.get(question.id, 0),
        )
        for answer, question in rows
    ]


@router.get(
    "/student/history",
    response_model=list[StudentQuizHistoryItem],
    include_in_schema=False,
    deprecated=True,
)
@router.get(
    "/student/results",
    response_model=list[StudentQuizHistoryItem],
)
def list_student_quiz_history(
    student: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> list[StudentQuizHistoryItem]:
    membership_ids = list(
        session.scalars(select(Student.id).where(Student.account_id == student.id))
    )
    if not membership_ids:
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
                QuizParticipant.student_id.in_(membership_ids),
                QuizSession.status == "finished",
                QuizSession.grades_published_at.is_not(None),
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
        question_points = session_question_points(quiz_session, session, participant)
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
                    question_points.get(question.id, 0),
                )
                submitted_answers = review.submitted_answers
                try:
                    submitted_data = json.loads(answer.answer_data)
                except TypeError, ValueError:
                    submitted_data = {}
                if not isinstance(submitted_data, dict):
                    submitted_data = {}
                if question.answer_mode == "written":
                    is_correct = (
                        answer.is_graded
                        and review.max_score > 0
                        and answer.score >= review.max_score
                    )
                else:
                    selected_ids = set(
                        submitted_data.get("selected_choice_ids", [])
                        if isinstance(
                            submitted_data.get("selected_choice_ids", []), list
                        )
                        else []
                    )
                    correct_ids = {
                        choice.id for choice in question_choices if choice.is_correct
                    }
                    is_correct = selected_ids == correct_ids
            else:
                submitted_answers = []
                is_correct = False
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
                    is_correct=is_correct,
                )
            )
        history.append(
            StudentQuizHistoryItem(
                session_id=quiz_session.id,
                quiz_title=quiz_session.quiz_title or "Quiz",
                class_name=quiz_session_class_name(quiz_session, session),
                started_at=quiz_session.started_at,
                score=(
                    round(
                        sum(answer.score for answer in answers_by_question.values()), 2
                    )
                    if quiz_session.grades_published_at is not None
                    else None
                ),
                maximum_score=(
                    round(
                        sum(question_points.values()),
                        2,
                    )
                    if quiz_session.grades_published_at is not None
                    else None
                ),
                answers=answers,
            )
        )
    return history


@router.post(
    "/sessions/{session_id}/publish-grades",
    response_model=QuizSessionResponse,
)
def publish_quiz_grades(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les notes ne peuvent être publiées qu'une fois le quiz terminé",
        )
    pending_count = session.scalar(
        select(func.count(QuizAnswer.id)).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.is_graded.is_(False),
        )
    )
    if pending_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Toutes les réponses doivent être corrigées avant publication",
        )
    if quiz_session.grades_published_at is None:
        quiz_session.grades_published_at = datetime.now(UTC)
        audit_event(
            "quiz.grades_published",
            professor_id=professor.id,
            session_id=quiz_session.id,
        )
        session.commit()
        session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


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
    if quiz_session.grades_published_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les notes publiées ne peuvent plus être modifiées",
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
        started_at = datetime.now(UTC)
        transition = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status == "waiting",
            )
            .values(status="in_progress", started_at=started_at)
            .execution_options(synchronize_session=False)
        )
        if transition.rowcount != 1:
            session.rollback()
            session.refresh(quiz_session)
            return session_response(quiz_session, quiz, session)
        participants = list(
            session.scalars(
                select(QuizParticipant).where(
                    QuizParticipant.session_id == quiz_session.id,
                    QuizParticipant.left_at.is_(None),
                )
            )
        )
        if not participants:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Au moins un élève doit rejoindre le quiz avant son démarrage",
            )
        quiz_session.status = "in_progress"
        quiz_session.started_at = started_at
        for participant in participants:
            participant.current_position = 0
        session.commit()
        session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.delete(
    "/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_quiz(
    quiz_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz = owned_quiz(quiz_id, professor, session)
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
            detail="Un quiz avec une session active ne peut pas être supprimé",
        )
    if (
        session.scalar(
            select(QuizSession.id)
            .where(
                QuizSession.quiz_id == quiz.id,
                QuizSession.status == "finished",
            )
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Impossible de supprimer ce quiz car il possède des résultats "
                "qui doivent être conservés"
            ),
        )
    if (
        session.scalar(
            select(MakeupSessionQuiz.session_id)
            .where(MakeupSessionQuiz.quiz_id == quiz.id)
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer ce quiz car un rattrapage l’utilise",
        )
    session.execute(delete(QuizQuestionBank).where(QuizQuestionBank.quiz_id == quiz_id))
    session.execute(
        delete(TrainingQuizProfile).where(TrainingQuizProfile.quiz_id == quiz_id)
    )
    session.execute(
        delete(MakeupSessionQuiz).where(MakeupSessionQuiz.quiz_id == quiz_id)
    )
    cancelled_session_ids = list(
        session.scalars(
            select(QuizSession.id).where(
                QuizSession.quiz_id == quiz.id,
                QuizSession.status == "cancelled",
            )
        )
    )
    delete_quiz_session_records(cancelled_session_ids, session)
    session.execute(delete(Quiz).where(Quiz.id == quiz_id))
    session.commit()
    audit_event(
        "quiz.deleted",
        professor_id=professor.id,
        quiz_id=quiz_id,
    )


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
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_quiz_session(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status not in {"waiting", "in_progress", "paused"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette session ne peut plus être annulée",
        )
    if (
        session.scalar(
            select(QuizAnswer.id)
            .where(QuizAnswer.session_id == quiz_session.id)
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Impossible d’annuler ce quiz car des réponses ont déjà été "
                "enregistrées. Terminez la session pour conserver les résultats"
            ),
        )
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()
    audit_event(
        "quiz.session_cancelled_and_deleted",
        professor_id=professor.id,
        session_id=session_id,
    )


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


@router.get(
    "/training/{question_bank_id}/history",
    response_model=list[TrainingHistoryItem],
)
def list_student_training_history(
    question_bank_id: int,
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> list[TrainingHistoryItem]:
    membership = session.scalar(select(Student).where(Student.account_id == student.id))
    if membership is None:
        raise HTTPException(
            status_code=409, detail="L’élève doit être affecté à une classe"
        )
    rows = list(
        session.execute(
            select(QuizSession, QuizParticipant)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                QuizSession.training_question_bank_id == question_bank_id,
                QuizSession.status == "finished",
                QuizParticipant.student_id == membership.id,
                QuizSession.started_at.is_not(None),
            )
            .order_by(QuizSession.started_at, QuizSession.id)
        )
    )
    return [
        TrainingHistoryItem(
            session_id=quiz_session.id,
            question_bank_id=question_bank_id,
            started_at=quiz_session.started_at,
            score=score,
            maximum_score=maximum,
            pending_manual_review_count=pending,
        )
        for quiz_session, participant in rows
        for score, maximum, pending in [
            training_result(quiz_session, participant, session)
        ]
    ]


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
        allow_negative_points=False,
        same_questions_for_all=False,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status="in_progress",
        started_at=now,
        training_question_bank_id=bank.id,
    )
    session.add(quiz_session)
    session.flush()
    session.add_all(
        QuizSessionQuestion(
            session_id=quiz_session.id,
            question_id=question_id,
            position=position,
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
        class_name=(
            format_class_name(student_class.grade_level, student_class.name)
            if makeup.class_id is not None
            and (student_class := session.get(StudentClass, makeup.class_id))
            is not None
            else makeup.class_name
        ),
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
    obsolete_cancelled_ids = list(
        session.scalars(
            select(MakeupSession.id).where(
                MakeupSession.owner_id == professor.id,
                MakeupSession.status == "cancelled",
                ~MakeupSession.id.in_(
                    select(QuizSession.makeup_session_id)
                    .join(QuizAnswer, QuizAnswer.session_id == QuizSession.id)
                    .where(QuizSession.makeup_session_id.is_not(None))
                ),
            )
        )
    )
    for makeup_session_id in obsolete_cancelled_ids:
        delete_makeup_session_records(makeup_session_id, session)
    if obsolete_cancelled_ids:
        session.commit()
    makeups = list(
        session.scalars(
            select(MakeupSession)
            .where(
                MakeupSession.owner_id == professor.id,
                MakeupSession.status != "cancelled",
            )
            .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
        )
    )
    return [makeup_session_response(item, session) for item in makeups]


def class_finished_quiz_ids(
    student_class_id: int, professor: ProfessorUser, session: DbSession
) -> set[int]:
    """Quizzes for which the class already completed an exam session."""
    return set(
        session.scalars(
            select(QuizSession.quiz_id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.class_id == student_class_id,
                QuizSession.status == "finished",
            )
        )
    )


@router.get("/makeup/quiz-options", response_model=list[QuizResponse])
def makeup_quiz_options(
    class_id: Annotated[int, Query(ge=1)],
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizResponse]:
    """Quizzes a class may make up: only those the class has already taken."""
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    finished_ids = class_finished_quiz_ids(student_class.id, professor, session)
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(
                Quiz.owner_id == professor.id,
                Quiz.mode == "exam",
                Quiz.id.in_(finished_ids),
            )
            .order_by(Quiz.title, Quiz.id)
        )
    )
    return quiz_responses(quizzes, session)


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
    eligible = class_finished_quiz_ids(student_class.id, professor, session)
    if not quiz_ids.issubset(eligible):
        raise HTTPException(
            status_code=422,
            detail="Seuls les quiz déjà passés par la classe peuvent être rattrapés",
        )
    makeup = MakeupSession(
        owner_id=professor.id,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
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
) -> MakeupSessionResponse | Response:
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
    if action == "cancel":
        has_answers = (
            session.scalar(
                select(QuizAnswer.id)
                .join(QuizSession, QuizSession.id == QuizAnswer.session_id)
                .where(QuizSession.makeup_session_id == makeup.id)
                .limit(1)
            )
            is not None
        )
        if has_answers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Impossible d’annuler ce rattrapage car des réponses ont déjà "
                    "été enregistrées"
                ),
            )
        delete_makeup_session_records(makeup.id, session)
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    transition = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == expected,
        )
        .values(status=target)
        .execution_options(synchronize_session=False)
    )
    if transition.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Action impossible pour cette session"
        )
    makeup.status = target
    children = list(
        session.scalars(
            select(QuizSession).where(QuizSession.makeup_session_id == makeup.id)
        )
    )
    if action == "start" and not children:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Au moins un élève doit choisir un quiz avant le démarrage",
        )
    now = datetime.now(UTC)
    for child in children:
        if action == "start":
            if child.status != "waiting":
                continue
            child.status = "in_progress"
            child.started_at = now
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = 0
        elif action == "pause":
            if child.status != "in_progress":
                continue
            child.status = "paused"
            child.paused_at = now
        elif action == "resume":
            if child.status != "paused" or child.paused_at is None:
                continue
            paused_at = child.paused_at
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=UTC)
            child.paused_duration_seconds = (child.paused_duration_seconds or 0) + ceil(
                max(0, (now - paused_at).total_seconds())
            )
            child.paused_at = None
            child.status = "in_progress"
        elif action == "finish":
            if child.status not in {"in_progress", "paused"}:
                continue
            child.status = "finished"
            quiz = session.get(Quiz, child.quiz_id)
            if quiz is not None:
                compute_final_scores(child, session)
            for participant in session.scalars(
                select(QuizParticipant).where(QuizParticipant.session_id == child.id)
            ):
                participant.current_position = None
    session.commit()
    return makeup_session_response(makeup, session)


@router.post(
    "/makeup/join",
    response_model=MakeupSessionJoinResponse,
)
def join_makeup_session(
    payload: QuizJoin,
    request: Request,
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
        # Bound join-code brute-force per student account, never per IP.
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
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
    request: Request,
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
        enforce_public_rate_limit(
            request,
            session,
            "quiz_join_rate_limiter",
            f"makeup-join:account:{account.id}",
        )
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
    waiting = session.execute(
        update(MakeupSession)
        .where(
            MakeupSession.id == makeup.id,
            MakeupSession.status == "waiting",
        )
        .values(status="waiting")
        .execution_options(synchronize_session=False)
    )
    if waiting.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Ce rattrapage n’accepte plus de choix"
        )
    claimed = session.execute(
        sqlite_insert(MakeupSessionSelection)
        .values(session_id=makeup.id, student_id=membership.id)
        .on_conflict_do_nothing(
            index_elements=[
                MakeupSessionSelection.session_id,
                MakeupSessionSelection.student_id,
            ]
        )
    )
    if claimed.rowcount != 1:
        raise HTTPException(status_code=409, detail="Sélection de quiz invalide")
    child = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_negative_points=quiz.allow_negative_points,
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
    session.add_all(
        QuizSessionStudentQuestion(
            session_id=child.id,
            student_id=membership.id,
            student_identifier=membership.identifier,
            question_id=question_id,
            position=position,
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
    return load_question_responses(list(draw_question_ids(quiz, session)), session)


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
    quiz.allow_negative_points = payload.allow_negative_points
    quiz.same_questions_for_all = False
    quiz.easy_question_count = payload.easy_question_count
    quiz.medium_question_count = payload.medium_question_count
    quiz.hard_question_count = payload.hard_question_count
    quiz.easy_points = 0
    quiz.medium_points = 0
    quiz.hard_points = 0
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
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=False,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status="waiting",
    )
    session.add(quiz_session)
    session.flush()
    assignments: list[QuizSessionStudentQuestion] = []
    used_draws: set[tuple[int, ...]] = set()
    for student in students:
        assigned_question_ids = draw_unique_question_ids(quiz, session, used_draws)
        assignments.extend(
            QuizSessionStudentQuestion(
                session_id=quiz_session.id,
                student_id=student.id,
                student_identifier=student.identifier,
                question_id=question_id,
                position=position,
            )
            for position, question_id in enumerate(assigned_question_ids)
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
        reject_quiz_join(request, session, f"join:unknown:{account.id}")
    quiz_session, quiz = row
    join_subject = f"join:session:{quiz_session.id}"
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
        if existing.left_at is None or quiz_session.status not in {
            "waiting",
            "in_progress",
            "paused",
        }:
            reject_quiz_join(request, session, join_subject)
        participant_token = token_urlsafe(32)
        active_session = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
            .values(status=QuizSession.status)
            .execution_options(synchronize_session=False)
        )
        if active_session.rowcount != 1:
            session.rollback()
            reject_quiz_join(request, session, join_subject)
        reconnected = session.execute(
            update(QuizParticipant)
            .where(
                QuizParticipant.id == existing.id,
                QuizParticipant.left_at.is_not(None),
            )
            .values(
                access_token_hash=participant_token_hash(participant_token),
                left_at=None,
                student_identifier=student.identifier,
                student_display_name=student.display_name,
            )
            .execution_options(synchronize_session=False)
        )
        if reconnected.rowcount != 1:
            session.rollback()
            reject_quiz_join(request, session, join_subject)
        session.commit()
        session.refresh(existing)
        state = student_state_response(quiz_session, quiz, existing, session)
        return StudentQuizJoinResponse(
            **state.model_dump(), participant_token=participant_token
        )
    if quiz_session.status != "waiting":
        reject_quiz_join(request, session, join_subject)
    waiting = session.execute(
        update(QuizSession)
        .where(
            QuizSession.id == quiz_session.id,
            QuizSession.status == "waiting",
        )
        .values(status="waiting")
        .execution_options(synchronize_session=False)
    )
    if waiting.rowcount != 1:
        session.rollback()
        reject_quiz_join(request, session, join_subject)
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


@router.post(
    "/student/sessions/{join_code}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_student_quiz(
    join_code: str,
    request: Request,
    session: DbSession,
    quiz_token: Annotated[str | None, Header(alias="X-Quiz-Token")] = None,
) -> Response:
    _, _, participant = authenticated_participant(
        join_code, quiz_token, request, session
    )
    enforce_public_rate_limit(
        request,
        session,
        "quiz_participant_rate_limiter",
        f"participant:{participant.id}",
    )
    participant.left_at = datetime.now(UTC)
    participant.access_token_hash = None
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    question = session.get(Question, question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La question actuelle n’est pas disponible",
        )
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id == question_id)
            .order_by(QuestionChoice.position)
        )
    )
    choices_by_id = {choice.id: choice for choice in choices}

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
                is_correct=None,
                correct_choice_ids=[],
                expected_answer=expected_answer,
                submitted_answer=written_answer,
                requires_manual_review=True,
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

    # Atomic upsert: concurrent submissions for the same question can never
    # create duplicate answers nor crash on the uniqueness constraint.
    answer_statement = sqlite_insert(QuizAnswer).values(
        session_id=quiz_session.id,
        participant_id=participant.id,
        question_id=question_id,
        answer_data=json.dumps(answer_data, ensure_ascii=False),
        score=0,
        is_graded=False,
    )
    session.execute(
        answer_statement.on_conflict_do_update(
            index_elements=[
                QuizAnswer.session_id,
                QuizAnswer.participant_id,
                QuizAnswer.question_id,
            ],
            set_={
                "answer_data": answer_statement.excluded.answer_data,
                "score": 0,
                "is_graded": False,
            },
        )
    )
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
        transition = session.execute(
            update(QuizSession)
            .where(
                QuizSession.id == quiz_session.id,
                QuizSession.status == "in_progress",
            )
            .values(status="finished")
            .execution_options(synchronize_session=False)
        )
        if transition.rowcount == 1:
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
    question_ids = session_question_ids(quiz_session, session, participant)
    answered_question_ids = set(
        session.scalars(
            select(QuizAnswer.question_id).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    accessible_positions = {
        position
        for position, question_id in enumerate(question_ids)
        if question_id in answered_question_ids
    }
    if accessible_positions:
        next_position = max(accessible_positions) + 1
        if next_position < len(question_ids):
            accessible_positions.add(next_position)
    if participant.current_position is not None:
        accessible_positions.add(participant.current_position)
    if (
        quiz_session.status != "in_progress"
        or not allow_previous_questions
        or participant.current_position is None
        or target_position not in accessible_positions
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
    participant.violation_count = (participant.violation_count or 0) + 1
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
