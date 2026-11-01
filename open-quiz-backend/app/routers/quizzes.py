from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from random import SystemRandom
from statistics import median
from string import ascii_uppercase, digits
from typing import Annotated

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from starlette.requests import HTTPConnection

from app.audit import audit_event
from app.class_names import format_class_name
from app.dependencies import DbSession, ProfessorUser
from app.errors import ErrorCode, api_error
from app.live_quiz import (
    active_quiz_sessions_topic,
    makeup_sessions_topic,
    quiz_session_topic,
    student_session_topic,
)
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionBank,
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
    User,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.question_responses import load_question_records, load_question_responses
from app.quiz_session_records import (
    delete_quiz_session_records,
)
from app.schemas import (
    QuestionResponse,
    QuizBankSummary,
    QuizCreate,
    QuizLaunch,
    QuizParticipantResponse,
    QuizResponse,
    QuizSessionResponse,
    StudentAnswerSummary,
    StudentQuizChoiceResponse,
    StudentQuizQuestionResponse,
    StudentQuizSessionResponse,
    StudentQuizStateResponse,
)
from app.services.grading import (
    decoded_answer_data,
    participant_maximum_scores,
    training_result,
)
from app.services.question_assignments import (
    accessible_question_positions,
    current_question_id,
    session_question_count,
    session_question_ids,
)
from app.services.question_draws import (
    difficulty_counts_for_banks,
    draw_question_ids,
    draw_unique_question_ids,
    question_draw_pool,
    quiz_bank_ids,
)
from app.services.session_lifecycle import (
    answer_review_enabled,
    as_utc,
    discard_active_training_sessions,
    expire_owned_quiz_sessions,
    expire_quiz_session,
    quiz_ends_at,
)
from app.session_status import ACTIVE_SESSION_STATUSES

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])
randomizer = SystemRandom()
JOIN_CODE_ALPHABET = ascii_uppercase + digits
VIOLATION_DEDUPLICATION_SECONDS = 2


def publish_quiz_update(
    request: HTTPConnection,
    quiz_session: QuizSession,
    session: DbSession,
    *,
    active_sessions_changed: bool = True,
    makeup_sessions_changed: bool = True,
) -> None:
    hub = request.app.state.live_quiz_hub
    publish_quiz_topics(request, quiz_session.id, quiz_session.join_code)
    if active_sessions_changed:
        owner_id = session.scalar(
            select(Quiz.owner_id).where(Quiz.id == quiz_session.quiz_id)
        )
        if owner_id is not None:
            hub.publish(active_quiz_sessions_topic(owner_id))
    if makeup_sessions_changed and quiz_session.makeup_session_id is not None:
        makeup_owner_id = session.scalar(
            select(MakeupSession.owner_id).where(
                MakeupSession.id == quiz_session.makeup_session_id
            )
        )
        if makeup_owner_id is not None:
            hub.publish(makeup_sessions_topic(makeup_owner_id))


def publish_quiz_topics(
    request: HTTPConnection, session_id: int, join_code: str
) -> None:
    hub = request.app.state.live_quiz_hub
    hub.publish(quiz_session_topic(session_id))
    hub.publish(student_session_topic(join_code))


def publish_makeup_update(request: HTTPConnection, owner_id: int) -> None:
    request.app.state.live_quiz_hub.publish(makeup_sessions_topic(owner_id))


def publish_active_quiz_sessions_update(request: HTTPConnection, owner_id: int) -> None:
    request.app.state.live_quiz_hub.publish(active_quiz_sessions_topic(owner_id))


def enforce_public_rate_limit(
    request: HTTPConnection,
    session: DbSession,
    limiter_name: str,
    subject: str,
) -> None:
    limiter = getattr(request.app.state, limiter_name)
    retry_after = limiter.reserve(session, subject)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=api_error(
                ErrorCode.QUIZ_RATE_LIMITED, "Trop de tentatives pour rejoindre le quiz"
            ),
            headers={"Retry-After": str(retry_after)},
        )


def quiz_join_rejected() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=api_error(
            ErrorCode.QUIZ_JOIN_REJECTED, "Impossible de rejoindre ce quiz"
        ),
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


def owned_quiz(quiz_id: int, professor: ProfessorUser, session: DbSession) -> Quiz:
    quiz = session.scalar(
        select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
    )
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"),
        )
    return quiz


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
            detail=api_error(
                ErrorCode.QUESTION_BANK_SELECTION_INVALID,
                "Une ou plusieurs banques de questions sont invalides",
            ),
        )
    difficulty_counts_for_banks(payload, payload.question_bank_ids, session)
    return banks


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
            allow_answer_review=quiz.allow_answer_review,
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
        allow_answer_review=False,
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
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_FOUND, "Session de quiz introuvable"
            ),
        )
    return row


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    expire_quiz_session(quiz_session, quiz, session)
    participant_query = select(QuizParticipant).where(
        QuizParticipant.session_id == quiz_session.id
    )
    if quiz_session.status in ACTIVE_SESSION_STATUSES:
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
    if quiz_session.status not in ACTIVE_SESSION_STATUSES:
        participants = [
            p
            for p in participants
            if not (
                p.left_at is not None
                and (
                    quiz_session.started_at is None
                    or p.left_at <= quiz_session.started_at
                )
                and answers_by_student.get(p.id, (0, 0, 0))[0] == 0
            )
        ]
    maximum_scores = participant_maximum_scores(quiz_session, participants, session)
    median_maximum_score = (
        float(median(maximum_scores.values())) if maximum_scores else 0
    )
    total_questions = session_question_count(quiz_session, session)
    review_enabled = answer_review_enabled(quiz_session, quiz)

    def has_finished(participant: QuizParticipant) -> bool:
        if participant.submitted_at is not None:
            return True
        # Sessions launched before the final submission existed, and quizzes
        # without the review step, are done as soon as every answer is in.
        answered_count = answers_by_student.get(participant.id, (0, 0, 0))[0]
        return (
            not review_enabled
            and participant.current_position is None
            and answered_count > 0
            and answered_count >= total_questions
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
                has_finished=has_finished(participant),
                score=(
                    answers_by_student.get(participant.id, (0, 0, 0))[1]
                    if quiz_session.status == "finished"
                    else 0
                ),
                maximum_score=maximum_scores.get(participant.id, 0.0),
                pending_manual_grading_count=(
                    answers_by_student.get(participant.id, (0, 0, 0))[2]
                    if quiz_session.status == "finished"
                    else 0
                ),
                violation_count=(
                    0
                    if participant.last_violation_type == "paste_attempt"
                    else participant.violation_count
                ),
                last_violation_type=(
                    None
                    if participant.last_violation_type == "paste_attempt"
                    else participant.last_violation_type
                ),
                last_violation_at=(
                    None
                    if participant.last_violation_type == "paste_attempt"
                    else participant.last_violation_at
                ),
                joined_at=participant.joined_at,
            )
            for participant in participants
        ],
        total_questions=total_questions,
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


def quiz_session_class_name(quiz_session: QuizSession, session: DbSession) -> str:
    if quiz_session.class_id is None:
        return quiz_session.class_name
    student_class = session.get(StudentClass, quiz_session.class_id)
    if student_class is None:
        return quiz_session.class_name
    return format_class_name(student_class.grade_level, student_class.name)


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
    request: HTTPConnection,
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
            detail=api_error(
                ErrorCode.QUIZ_PARTICIPANT_TOKEN_MISSING,
                "Jeton de participation au quiz manquant",
            ),
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
            detail=api_error(
                ErrorCode.QUIZ_PARTICIPANT_TOKEN_INVALID,
                "Jeton de participation au quiz invalide",
            ),
        )
    participant = row[2]
    active_account = session.scalar(
        select(StudentAccount.is_active)
        .join(Student, Student.account_id == StudentAccount.id)
        .where(Student.id == participant.student_id)
    )
    if active_account is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=api_error(
                ErrorCode.QUIZ_PARTICIPANT_TOKEN_INVALID,
                "Jeton de participation au quiz invalide",
            ),
        )
    return row


def public_answer_mode(question: Question) -> str:
    """The answer mode a student may see.

    Hidden choice modes must have the same API and control shape. The server
    still validates and grades against the real stored mode.
    """
    if not question.answer_mode_disclosed and question.answer_mode in {
        "single",
        "multiple",
    }:
        return "multiple"
    return question.answer_mode


def student_answer_summaries(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    question_ids: list[int],
    session: DbSession,
) -> list[StudentAnswerSummary]:
    """What a participant answered, for the review before final submission.

    Only the participant's own wording is returned: nothing here discloses the
    expected answer of a question that is still running for the class.
    """
    answers = {
        answer.question_id: answer
        for answer in session.scalars(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    }
    questions_by_id, choices_by_question = load_question_records(question_ids, session)
    summaries: list[StudentAnswerSummary] = []
    for position, question_id in enumerate(question_ids):
        question = questions_by_id.get(question_id)
        answer = answers.get(question_id)
        if question is None or answer is None:
            continue
        submitted = decoded_answer_data(answer)
        if question.answer_mode == "written":
            submitted_answers = [str(submitted.get("written_answer", ""))]
        else:
            choices_by_id = {
                choice.id: choice for choice in choices_by_question.get(question_id, [])
            }
            submitted_ids = submitted.get("selected_choice_ids", [])
            if not isinstance(submitted_ids, list):
                submitted_ids = []
            submitted_answers = [
                choices_by_id[choice_id].label
                for choice_id in submitted_ids
                if type(choice_id) is int and choice_id in choices_by_id
            ]
        summaries.append(
            StudentAnswerSummary(
                question_number=position + 1,
                question_id=question.id,
                prompt=question.prompt,
                answer_mode=public_answer_mode(question),
                submitted_answers=submitted_answers,
            )
        )
    return summaries


def student_question_response(
    question_id: int,
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizQuestionResponse:
    questions_by_id, choices_by_question = load_question_records([question_id], session)
    question = questions_by_id.get(question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_QUESTION_UNAVAILABLE,
                "La question actuelle n’est pas disponible",
            ),
        )
    choices = (
        []
        if question.answer_mode == "written"
        else choices_by_question.get(question.id, [])
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
        answer_mode=public_answer_mode(question),
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
    # A participant who has submitted every assigned answer has no current
    # question while classmates may still be working. Keep that completed
    # state explicit so the frontend can render its waiting message instead of
    # an otherwise empty in-progress page.
    has_answered = (
        question_id in answered_question_ids
        if question_id is not None
        else bool(question_ids) and set(question_ids).issubset(answered_question_ids)
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
        decoded_answer_data(existing_answer) if existing_answer is not None else {}
    )
    answered_count = len(answered_question_ids)
    review_enabled = answer_review_enabled(quiz_session, quiz)
    # A participant who answered everything but has not confirmed yet keeps
    # the session open for themselves: they may re-read, and correct when the
    # quiz allows going back, until they submit their paper.
    awaiting_final_submission = (
        review_enabled
        and quiz_session.status in ("in_progress", "paused")
        and participant.submitted_at is None
        and participant.current_position is None
        and bool(question_ids)
        and set(question_ids).issubset(answered_question_ids)
    )
    accessible_positions = accessible_question_positions(
        question_ids,
        answered_question_ids,
        participant.current_position,
    )
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
        allow_answer_review=review_enabled,
        awaiting_final_submission=awaiting_final_submission,
        answer_summaries=(
            student_answer_summaries(quiz_session, participant, question_ids, session)
            if awaiting_final_submission
            else []
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


def generate_join_code(session: DbSession) -> str:
    for _ in range(20):
        code = "".join(randomizer.choice(JOIN_CODE_ALPHABET) for _ in range(6))
        reserved_code = session.scalar(
            insert(QuizJoinCode)
            .values(code=code)
            .on_conflict_do_nothing(index_elements=[QuizJoinCode.code])
            .returning(QuizJoinCode.code)
        )
        if reserved_code is not None:
            return code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=api_error(
            ErrorCode.QUIZ_CODE_GENERATION_FAILED,
            "Impossible de générer un code de quiz",
        ),
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
        allow_answer_review=payload.allow_answer_review,
        allow_negative_points=payload.allow_negative_points,
        same_questions_for_all=payload.same_questions_for_all,
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


def active_session_responses(
    professor: User,
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
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .order_by(QuizSession.created_at.desc(), QuizSession.id.desc())
        .limit(20)
    )
    return [
        session_response(quiz_session, quiz, session) for quiz_session, quiz in rows
    ]


@router.get("/sessions/active", response_model=list[QuizSessionResponse])
def list_active_sessions(
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizSessionResponse]:
    return active_session_responses(professor, session)


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
                api_error(
                    ErrorCode.QUIZ_SESSION_NOT_DELETABLE,
                    "Seules les sessions terminées ou annulées peuvent être supprimées",
                )
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
    request: Request,
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
                detail=api_error(
                    ErrorCode.QUIZ_SESSION_NO_PARTICIPANTS,
                    "Au moins un élève doit rejoindre le quiz avant son démarrage",
                ),
            )
        quiz_session.status = "in_progress"
        quiz_session.started_at = started_at
        for participant in participants:
            participant.current_position = 0
        session.commit()
        session.refresh(quiz_session)
        publish_quiz_update(request, quiz_session, session)
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
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .limit(1)
    )
    if active_session_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_HAS_ACTIVE_SESSION,
                "Un quiz avec une session active ne peut pas être supprimé",
            ),
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
                api_error(
                    ErrorCode.QUIZ_HAS_RESULTS,
                    "Impossible de supprimer ce quiz car il possède des résultats "
                    "qui doivent être conservés",
                )
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
            detail=api_error(
                ErrorCode.QUIZ_USED_BY_MAKEUP,
                "Impossible de supprimer ce quiz car un rattrapage l’utilise",
            ),
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
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_RUNNING,
                "Seul un quiz en cours peut être mis en pause",
            ),
        )
    quiz_session.status = "paused"
    quiz_session.paused_at = datetime.now(UTC)
    session.commit()
    session.refresh(quiz_session)
    publish_quiz_update(request, quiz_session, session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/resume",
    response_model=QuizSessionResponse,
)
def resume_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "paused" or quiz_session.paused_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_PAUSED,
                "Seul un quiz en pause peut être repris",
            ),
        )
    paused_at = as_utc(quiz_session.paused_at)
    quiz_session.paused_duration_seconds = (
        quiz_session.paused_duration_seconds or 0
    ) + ceil(max(0, (datetime.now(UTC) - paused_at).total_seconds()))
    quiz_session.paused_at = None
    quiz_session.status = "in_progress"
    session.commit()
    session.refresh(quiz_session)
    publish_quiz_update(request, quiz_session, session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_quiz_session(
    session_id: int,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    expire_quiz_session(quiz_session, quiz, session)
    if quiz_session.status not in ACTIVE_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_CANCELLABLE,
                "Cette session ne peut plus être annulée",
            ),
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
                api_error(
                    ErrorCode.QUIZ_SESSION_HAS_ANSWERS,
                    "Impossible d’annuler ce quiz car des réponses ont déjà été "
                    "enregistrées. Terminez la session pour conserver les résultats",
                )
            ),
        )
    join_code = quiz_session.join_code
    delete_quiz_session_records([quiz_session.id], session)
    session.commit()
    publish_quiz_topics(request, session_id, join_code)
    publish_active_quiz_sessions_update(request, professor.id)
    audit_event(
        "quiz.session_cancelled_and_deleted",
        professor_id=professor.id,
        session_id=session_id,
    )


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
            detail=api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"),
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
            detail=api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"),
        )
    active_session_id = session.scalar(
        select(QuizSession.id)
        .where(
            QuizSession.quiz_id == quiz.id,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .limit(1)
    )
    if active_session_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_HAS_ACTIVE_SESSION,
                "Un quiz avec une session active ne peut pas être modifié",
            ),
        )
    validate_bank_selection(payload, professor, session)
    quiz.title = payload.title
    quiz.mode = "exam"
    quiz.source_language = payload.source_language
    quiz.question_count = payload.question_count
    quiz.duration_seconds = payload.duration_seconds
    quiz.allow_previous_questions = payload.allow_previous_questions
    quiz.allow_answer_review = payload.allow_answer_review
    quiz.allow_negative_points = payload.allow_negative_points
    quiz.same_questions_for_all = payload.same_questions_for_all
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
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz = owned_quiz(quiz_id, professor, session)
    if quiz.mode != "exam":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_TRAINING_NOT_LAUNCHABLE,
                "Un entraînement est lancé directement par l’élève",
            ),
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
            detail=api_error(
                ErrorCode.QUIZ_CLASS_INVALID, "La classe sélectionnée est invalide"
            ),
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
            detail=api_error(
                ErrorCode.QUIZ_CLASS_EMPTY, "La classe doit contenir au moins un élève"
            ),
        )
    discard_active_training_sessions(
        select(Student.id).where(Student.class_id == student_class.id),
        quiz_bank_ids(quiz.id, session),
        session,
    )
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        quiz_title=quiz.title,
        source_language=quiz.source_language,
        duration_seconds=quiz.duration_seconds,
        allow_previous_questions=quiz.allow_previous_questions,
        allow_answer_review=quiz.allow_answer_review,
        allow_negative_points=quiz.allow_negative_points,
        same_questions_for_all=quiz.same_questions_for_all,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status="waiting",
    )
    session.add(quiz_session)
    session.flush()
    pool = question_draw_pool(quiz, session)
    if quiz.same_questions_for_all:
        session.add_all(
            QuizSessionQuestion(
                session_id=quiz_session.id,
                question_id=question_id,
                position=position,
            )
            for position, question_id in enumerate(pool.draw())
        )
    else:
        assignments: list[QuizSessionStudentQuestion] = []
        used_draws: set[tuple[int, ...]] = set()
        for student in students:
            student_question_ids = draw_unique_question_ids(pool, used_draws)
            assignments.extend(
                QuizSessionStudentQuestion(
                    session_id=quiz_session.id,
                    student_id=student.id,
                    student_identifier=student.identifier,
                    question_id=question_id,
                    position=position,
                )
                for position, question_id in enumerate(student_question_ids)
            )
        session.add_all(assignments)
    session.commit()
    session.refresh(quiz_session)
    publish_active_quiz_sessions_update(request, professor.id)
    return session_response(quiz_session, quiz, session)
