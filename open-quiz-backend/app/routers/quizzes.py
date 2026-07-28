from collections import defaultdict
from datetime import UTC, datetime
from random import SystemRandom
from string import ascii_uppercase, digits

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.dependencies import DbSession, ProfessorUser
from app.models import (
    Question,
    QuestionBank,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    QuizSessionQuestion,
    Student,
    StudentClass,
)
from app.routers.question_banks import question_response
from app.schemas import (
    QuestionResponse,
    QuizBankSummary,
    QuizCreate,
    QuizJoin,
    QuizLaunch,
    QuizParticipantResponse,
    QuizResponse,
    QuizSessionResponse,
    StudentQuizSessionResponse,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])
randomizer = SystemRandom()
JOIN_CODE_ALPHABET = ascii_uppercase + digits


def difficulty_counts(payload: Quiz | QuizCreate) -> dict[str, int]:
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
        ),
        reverse=True,
    )
    for difficulty in priorities[:remaining]:
        counts[difficulty] += 1
    return counts


def owned_quiz(quiz_id: int, professor: ProfessorUser, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
    )
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
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
            detail="One or more question banks are invalid",
        )
    validate_question_availability(
        payload.question_bank_ids,
        difficulty_counts(payload),
        session,
    )
    return banks


def validate_question_availability(
    bank_ids: list[int],
    requested: dict[str, int],
    session: DbSession,
) -> None:
    available = {
        difficulty: count
        for difficulty, count in session.execute(
            select(Question.difficulty, func.count(Question.id))
            .where(Question.question_bank_id.in_(bank_ids))
            .group_by(Question.difficulty)
        )
    }
    shortages = [
        difficulty
        for difficulty, count in requested.items()
        if available.get(difficulty, 0) < count
    ]
    if shortages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Not enough questions for the requested difficulty distribution: "
                + ", ".join(shortages)
            ),
        )


def draw_question_ids(quiz: Quiz, session: DbSession) -> list[int]:
    bank_ids = quiz_bank_ids(quiz.id, session)
    requested = difficulty_counts(quiz)
    validate_question_availability(bank_ids, requested, session)
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
            select(QuestionCode).where(
                QuestionCode.question_id.in_(question_ids)
            )
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
        select(QuestionBank, func.count(Question.id))
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
        question_count=quiz.question_count,
        easy_percentage=quiz.easy_percentage,
        medium_percentage=quiz.medium_percentage,
        hard_percentage=quiz.hard_percentage,
        question_banks=[
            QuizBankSummary(
                id=bank.id,
                grade_level=bank.grade_level,
                chapter=bank.chapter,
                question_count=count,
            )
            for bank, count in rows
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
            detail="Quiz session not found",
        )
    return row


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    participants = list(
        session.scalars(
            select(QuizParticipant)
            .where(QuizParticipant.session_id == quiz_session.id)
            .order_by(QuizParticipant.joined_at, QuizParticipant.id)
        )
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
                joined_at=participant.joined_at,
            )
            for participant in participants
        ],
        created_at=quiz_session.created_at,
        started_at=quiz_session.started_at,
    )


def student_session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
) -> StudentQuizSessionResponse:
    return StudentQuizSessionResponse(
        quiz_title=quiz.title,
        class_name=quiz_session.class_name,
        join_code=quiz_session.join_code,
        status=quiz_session.status,
    )


def generate_join_code(session: DbSession) -> str:
    for _ in range(20):
        code = "".join(randomizer.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        if session.scalar(
            select(QuizSession.id).where(QuizSession.join_code == code)
        ) is None:
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to generate a quiz code",
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
        question_count=payload.question_count,
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
    rows = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(Quiz.owner_id == professor.id)
        .order_by(QuizSession.created_at.desc(), QuizSession.id.desc())
        .limit(20)
    )
    return [
        session_response(quiz_session, quiz, session)
        for quiz_session, quiz in rows
    ]


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
    return session_response(quiz_session, quiz, session)


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
        quiz_session.status = "started"
        quiz_session.started_at = datetime.now(UTC)
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
            detail="The selected class is invalid",
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
    response_model=StudentQuizSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_quiz(
    payload: QuizJoin,
    session: DbSession,
) -> StudentQuizSessionResponse:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == payload.join_code)
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found",
        )
    quiz_session, quiz = row
    if quiz_session.status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quiz has already started",
        )
    if quiz_session.class_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The class used for this quiz no longer exists",
        )
    student = session.scalar(
        select(Student).where(
            Student.class_id == quiz_session.class_id,
            Student.identifier == payload.student_identifier,
        )
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This student does not belong to the selected class",
        )
    existing = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.session_id == quiz_session.id,
            QuizParticipant.student_id == student.id,
        )
    )
    if existing is None:
        session.add(
            QuizParticipant(
                session_id=quiz_session.id,
                student_id=student.id,
                student_identifier=student.identifier,
                student_display_name=student.display_name,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return student_session_response(quiz_session, quiz)


@router.get(
    "/public/sessions/{join_code}",
    response_model=StudentQuizSessionResponse,
)
def get_public_quiz_session(
    join_code: str,
    session: DbSession,
) -> StudentQuizSessionResponse:
    row = session.execute(
        select(QuizSession, Quiz)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.join_code == join_code.strip().upper())
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found",
        )
    return student_session_response(row[0], row[1])
