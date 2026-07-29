import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from random import SystemRandom
from secrets import token_urlsafe
from string import ascii_uppercase, digits
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.audit import audit_event
from app.dependencies import DbSession, ProfessorUser
from app.grading import compute_final_scores
from app.models import (
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
    Student,
    StudentClass,
)
from app.requests import client_ip
from app.routers.question_banks import question_response
from app.schemas import (
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
    StudentQuizJoinResponse,
    StudentQuizNavigation,
    StudentQuizQuestionResponse,
    StudentQuizSessionResponse,
    StudentQuizStateResponse,
    StudentQuizViolation,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])
randomizer = SystemRandom()
JOIN_CODE_ALPHABET = ascii_uppercase + digits
VIOLATION_DEDUPLICATION_SECONDS = 2


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


DIFFICULTY_EASE_PRIORITY = {"easy": 2, "medium": 1, "hard": 0}


def difficulty_counts(
    payload: Quiz | QuizCreate,
    available: dict[str, int] | None = None,
) -> dict[str, int]:
    percentages = {
        "easy": payload.easy_percentage,
        "medium": payload.medium_percentage,
        "hard": payload.hard_percentage,
    }
    exact = {
        difficulty: payload.question_count * percentage / 100
        for difficulty, percentage in percentages.items()
    }
    counts = {difficulty: int(value) for difficulty, value in exact.items()}
    remaining = payload.question_count - sum(counts.values())
    priorities = sorted(
        percentages,
        key=lambda difficulty: (
            exact[difficulty] - counts[difficulty],
            percentages[difficulty],
            DIFFICULTY_EASE_PRIORITY[difficulty],
        ),
        reverse=True,
    )
    for difficulty in priorities[:remaining]:
        counts[difficulty] += 1
    if available is None:
        return counts
    counts = {
        difficulty: min(count, available.get(difficulty, 0))
        for difficulty, count in counts.items()
    }
    remaining = payload.question_count - sum(counts.values())
    while remaining:
        candidates = [
            difficulty
            for difficulty in percentages
            if counts[difficulty] < available.get(difficulty, 0)
        ]
        if not candidates:
            break
        difficulty = max(
            candidates,
            key=lambda item: (
                percentages[item],
                DIFFICULTY_EASE_PRIORITY[item],
            ),
        )
        counts[difficulty] += 1
        remaining -= 1
    return counts


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
    if sum(available.values()) < payload.question_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Nombre total de questions insuffisant dans les banques sélectionnées",
        )
    return difficulty_counts(payload, available)


def draw_question_ids(quiz: Quiz, session: DbSession) -> list[int]:
    bank_ids = quiz_bank_ids(quiz.id, session)
    requested = difficulty_counts_for_banks(quiz, bank_ids, session)
    selected_ids: list[int] = []
    for difficulty, count in requested.items():
        if count == 0:
            continue
        candidates = list(
            session.scalars(
                select(Question.id).where(
                    Question.question_bank_id.in_(bank_ids),
                    Question.difficulty == difficulty,
                )
            )
        )
        selected_ids.extend(randomizer.sample(candidates, count))
    randomizer.shuffle(selected_ids)
    return selected_ids


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
        title=quiz.title,
        source_language=quiz.source_language,
        question_count=quiz.question_count,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        easy_percentage=quiz.easy_percentage,
        medium_percentage=quiz.medium_percentage,
        hard_percentage=quiz.hard_percentage,
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
) -> list[int]:
    return list(
        session.scalars(
            select(QuizSessionQuestion.question_id)
            .where(QuizSessionQuestion.session_id == quiz_session.id)
            .order_by(QuizSessionQuestion.position)
        )
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
    return session.scalar(
        select(QuizSessionQuestion.question_id).where(
            QuizSessionQuestion.session_id == quiz_session.id,
            QuizSessionQuestion.position == participant.current_position,
        )
    )


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
    question_ids = session_question_ids(quiz_session, session)
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
        quiz_title=quiz.title,
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
        total_questions=len(question_ids),
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
        quiz_title=quiz.title,
        source_language=quiz.source_language,
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
    return started_at + timedelta(seconds=quiz.duration_seconds + paused_duration)


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
    session.execute(delete(QuizSession).where(QuizSession.id.in_(session_ids)))


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
    question_ids = session_question_ids(quiz_session, session)
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
        allow_previous_questions=quiz.allow_previous_questions,
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
) -> list[QuizResponse]:
    quizzes = list(
        session.scalars(
            select(Quiz)
            .where(Quiz.owner_id == professor.id)
            .order_by(Quiz.created_at.desc(), Quiz.id.desc())
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
        title=payload.title,
        source_language=payload.source_language,
        question_count=payload.question_count,
        duration_seconds=payload.duration_seconds,
        allow_previous_questions=payload.allow_previous_questions,
        easy_percentage=payload.easy_percentage,
        medium_percentage=payload.medium_percentage,
        hard_percentage=payload.hard_percentage,
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
) -> list[QuizSessionResponse]:
    expire_owned_quiz_sessions(professor, session)
    purge_expired_quiz_results(professor, request, session)
    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            Quiz.owner_id == professor.id,
            QuizSession.status == "finished",
        )
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.created_at.desc(),
            QuizSession.id.desc(),
        )
    )
    return [
        session_response(quiz_session, quiz, session) for quiz_session, quiz in rows
    ]


def answer_review(
    answer: QuizAnswer,
    question: Question,
    position: int,
    choices: list[QuestionChoice],
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
        max_score=max(
            0,
            sum(choice.points for choice in choices if choice.is_correct),
        ),
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
            select(QuizAnswer, Question, QuizSessionQuestion.position)
            .join(Question, Question.id == QuizAnswer.question_id)
            .join(
                QuizSessionQuestion,
                (QuizSessionQuestion.session_id == QuizAnswer.session_id)
                & (QuizSessionQuestion.question_id == QuizAnswer.question_id),
            )
            .where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
            .order_by(QuizSessionQuestion.position)
        )
    )
    question_ids = [question.id for _, question, _ in rows]
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
            position,
            choices_by_question[question.id],
        )
        for answer, question, position in rows
    ]


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
        select(QuizAnswer, Question, QuizSessionQuestion.position)
        .join(Question, Question.id == QuizAnswer.question_id)
        .join(
            QuizSessionQuestion,
            (QuizSessionQuestion.session_id == QuizAnswer.session_id)
            & (QuizSessionQuestion.question_id == QuizAnswer.question_id),
        )
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
    answer, question, position = row
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
    max_score = max(
        0,
        sum(choice.points for choice in choices if choice.is_correct),
    )
    if payload.score > max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La note ne peut pas dépasser {max_score:g}",
        )
    answer.score = payload.score
    answer.is_graded = True
    session.commit()
    return answer_review(answer, question, position, choices)


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
    request: Request,
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
        ip=client_ip(request),
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


@router.get("/{quiz_id}/preview", response_model=list[QuestionResponse])
def preview_quiz(
    quiz_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionResponse]:
    quiz = owned_quiz(quiz_id, professor, session)
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
    quiz.source_language = payload.source_language
    quiz.question_count = payload.question_count
    quiz.duration_seconds = payload.duration_seconds
    quiz.allow_previous_questions = payload.allow_previous_questions
    quiz.easy_percentage = payload.easy_percentage
    quiz.medium_percentage = payload.medium_percentage
    quiz.hard_percentage = payload.hard_percentage
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
    question_ids = draw_question_ids(quiz, session)
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
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        class_id=student_class.id,
        class_name=student_class.name,
        join_code=generate_join_code(session),
        status="waiting",
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
) -> StudentQuizJoinResponse:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == payload.join_code)
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
            Student.identifier == payload.student_identifier,
        )
    )
    if student is None:
        reject_quiz_join(request, session, join_subject)
    existing = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.student_id == student.id,
        )
    )
    if existing is not None:
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
    return student_state_response(quiz_session, quiz, participant, session)


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

    if question.answer_mode == "written":
        written_answer = (payload.written_answer or "").strip()
        if not written_answer or payload.selected_choice_ids is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Une réponse rédactionnelle est requise",
            )
        answer_data = {"written_answer": written_answer}
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
    total_questions = len(session_question_ids(quiz_session, session))
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
        compute_final_scores(quiz_session, session)
    session.commit()
    return student_state_response(quiz_session, quiz, participant, session)


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
    if (
        quiz_session.status != "in_progress"
        or not quiz.allow_previous_questions
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
