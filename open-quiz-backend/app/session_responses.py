"""Response bodies describing quiz sessions to teachers and students."""

from hashlib import sha256
from statistics import median

from fastapi import (
    status,
)
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.choice_tokens import ChoiceTokens
from app.class_names import format_class_name
from app.dependencies import DbSession
from app.enums import AnswerMode, Difficulty, QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Question,
    QuestionBank,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizQuestionBank,
    QuizSession,
    Student,
    StudentClass,
    User,
)
from app.question_responses import load_question_records
from app.quiz_session_records import (
    delete_quiz_session_records,
)
from app.schemas import (
    MakeupParticipantResponse,
    MakeupQuizOption,
    MakeupSessionResponse,
    QuizBankSummary,
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
    rounded_score,
    training_result,
)
from app.services.question_assignments import (
    accessible_question_positions,
    current_question_id,
    session_question_count,
    session_question_ids,
)
from app.services.session_lifecycle import (
    answer_review_enabled,
    delete_makeup_session_records,
    quiz_ends_at,
)
from app.session_status import ACTIVE_SESSION_STATUSES

# Monitoring events no longer reported as alerts; one still stored is hidden.
RETIRED_VIOLATION_TYPES = frozenset({"paste_attempt", "copy_attempt"})


def quiz_responses(quizzes: list[Quiz], session: DbSession) -> list[QuizResponse]:
    if not quizzes:
        return []
    banks_by_quiz: dict[int, list[QuizBankSummary]] = {quiz.id: [] for quiz in quizzes}
    rows = session.execute(
        select(
            QuizQuestionBank.quiz_id,
            QuestionBank,
            func.count(Question.id),
            func.sum(case((Question.difficulty == Difficulty.EASY, 1), else_=0)),
            func.sum(case((Question.difficulty == Difficulty.MEDIUM, 1), else_=0)),
            func.sum(case((Question.difficulty == Difficulty.HARD, 1), else_=0)),
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


LiveAnswerCounts = dict[int, tuple[int, float, int]]


def session_participants(
    quiz_session: QuizSession, session: Session
) -> tuple[list[QuizParticipant], LiveAnswerCounts]:
    """Who a session lists, and per participant answers, score and pending.

    A running session lists those present; a closed one also lists those who
    left, except anyone who left the waiting room without ever answering.
    """
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
        participant_id: (answered_count, rounded_score(score), pending_count or 0)
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
    return participants, answers_by_student


def current_students(
    participants: list[QuizParticipant], session: Session
) -> dict[int, Student]:
    student_ids = [
        participant.student_id
        for participant in participants
        if participant.student_id is not None
    ]
    if not student_ids:
        return {}
    return {
        student.id: student
        for student in session.scalars(
            select(Student).where(Student.id.in_(student_ids))
        )
    }


def participant_has_finished(
    participant: QuizParticipant,
    answered_count: int,
    review_enabled: bool,
    total_questions: int,
) -> bool:
    if participant.submitted_at is not None:
        return True
    # Sessions launched before the final submission existed, and quizzes
    # without the review step, are done as soon as every answer is in.
    return (
        not review_enabled
        and participant.current_position is None
        and answered_count > 0
        and answered_count >= total_questions
    )


def live_participant_response(
    participant: QuizParticipant,
    quiz_session: QuizSession,
    counts: tuple[int, float, int],
    has_finished: bool,
    maximum_score: float,
    students_by_id: dict[int, Student],
) -> QuizParticipantResponse:
    answered_count, score, pending = counts
    finished_session = quiz_session.status == SessionStatus.FINISHED
    return QuizParticipantResponse(
        id=participant.id,
        student_identifier=participant.student_identifier,
        student_display_name=(
            students_by_id[participant.student_id].display_name
            if participant.student_id in students_by_id
            else participant.student_display_name
        ),
        answered_count=answered_count,
        has_finished=has_finished,
        score=score if finished_session else 0,
        maximum_score=maximum_score,
        pending_manual_grading_count=pending if finished_session else 0,
        violation_count=(
            0
            if participant.last_violation_type in RETIRED_VIOLATION_TYPES
            else participant.violation_count
        ),
        last_violation_type=(
            None
            if participant.last_violation_type in RETIRED_VIOLATION_TYPES
            else participant.last_violation_type
        ),
        last_violation_at=(
            None
            if participant.last_violation_type in RETIRED_VIOLATION_TYPES
            else participant.last_violation_at
        ),
        joined_at=participant.joined_at,
    )


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    participants, answers_by_student = session_participants(quiz_session, session)
    maximum_scores = participant_maximum_scores(quiz_session, participants, session)
    median_maximum_score = (
        rounded_score(median(maximum_scores.values())) if maximum_scores else 0
    )
    total_questions = session_question_count(quiz_session, session)
    review_enabled = answer_review_enabled(quiz_session, quiz)
    students_by_id = current_students(participants, session)
    participant_responses = []
    for participant in participants:
        counts = answers_by_student.get(participant.id, (0, 0, 0))
        participant_responses.append(
            live_participant_response(
                participant,
                quiz_session,
                counts,
                participant_has_finished(
                    participant, counts[0], review_enabled, total_questions
                ),
                maximum_scores.get(participant.id, 0.0),
                students_by_id,
            )
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
        participants=participant_responses,
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


def public_answer_mode(question: Question) -> str:
    """The answer mode a student may see.

    Hidden choice modes must have the same API and control shape. The server
    still validates and grades against the real stored mode.
    """
    if not question.answer_mode_disclosed and question.answer_mode in {
        AnswerMode.SINGLE,
        AnswerMode.MULTIPLE,
    }:
        return AnswerMode.MULTIPLE
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
        if question.answer_mode == AnswerMode.WRITTEN:
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
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_QUESTION_UNAVAILABLE,
            "La question actuelle n’est pas disponible",
        )
    choices = (
        []
        if question.answer_mode == AnswerMode.WRITTEN
        else choices_by_question.get(question.id, [])
    )
    choices.sort(
        key=lambda choice: sha256(
            (f"{quiz_session.id}:{participant.id}:{question.id}:{choice.id}").encode()
        ).digest()
    )
    tokens = ChoiceTokens(session, quiz_session, participant)
    code = session.get(QuestionCode, question.id)
    return StudentQuizQuestionResponse(
        id=question.id,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=public_answer_mode(question),
        answer_mode_disclosed=question.answer_mode_disclosed,
        response_language=question.response_language,
        allow_code_execution=question.allow_code_execution,
        has_image=question.image_sha256 is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=[
            StudentQuizChoiceResponse(
                id=tokens.token(choice.id),
                label=choice.label,
                position=position,
                has_image=choice.image_sha256 is not None,
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
    saved_choice_ids = saved_answer.get("selected_choice_ids")
    tokens = ChoiceTokens(session, quiz_session, participant)
    answered_count = len(answered_question_ids)
    review_enabled = answer_review_enabled(quiz_session, quiz)
    # A participant who answered everything but has not confirmed yet keeps
    # the session open for themselves: they may re-read, and correct when the
    # quiz allows going back, until they submit their paper.
    awaiting_final_submission = (
        review_enabled
        and quiz_session.status in (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
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
            and quiz_session.status == SessionStatus.IN_PROGRESS
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
        selected_choice_ids=(
            [
                tokens.token(choice_id)
                for choice_id in saved_choice_ids
                if type(choice_id) is int
            ]
            if isinstance(saved_choice_ids, list)
            else None
        ),
        written_answer=saved_answer.get("written_answer"),
        question=(
            student_question_response(
                question_id,
                quiz_session,
                participant,
                session,
            )
            if question_id is not None
            and quiz_session.status == SessionStatus.IN_PROGRESS
            else None
        ),
    )
    if quiz.mode == QuizMode.TRAINING and quiz_session.status == SessionStatus.FINISHED:
        score, maximum, pending = training_result(quiz_session, participant, session)
        state.potential_score = score
        state.potential_maximum_score = maximum
        state.pending_manual_review_count = pending
    return state


def active_session_responses(
    professor: User,
    session: DbSession,
) -> list[QuizSessionResponse]:
    obsolete_cancelled_ids = list(
        session.scalars(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                Quiz.owner_id == professor.id,
                QuizSession.status == SessionStatus.CANCELLED,
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
            Quiz.mode == QuizMode.EXAM,
            QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            # A make-up's children are supervised from the make-up session.
            QuizSession.makeup_session_id.is_(None),
        )
        .order_by(QuizSession.created_at.desc(), QuizSession.id.desc())
        .limit(20)
    )
    return [
        session_response(quiz_session, quiz, session) for quiz_session, quiz in rows
    ]


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
    child_sessions = list(
        session.scalars(
            select(QuizSession)
            .where(QuizSession.makeup_session_id == makeup.id)
            .order_by(QuizSession.id)
        )
    )
    quizzes_by_id = {quiz.id: quiz for quiz in quizzes}
    child_responses = [
        session_response(child, quizzes_by_id[child.quiz_id], session)
        for child in child_sessions
        if child.quiz_id in quizzes_by_id
    ]
    participants = [
        MakeupParticipantResponse(
            **participant.model_dump(),
            quiz_title=child.quiz_title,
            total_questions=child.total_questions,
        )
        for child in child_responses
        for participant in child.participants
    ]
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
        participant_count=len(participants),
        participants=participants,
        created_at=makeup.created_at,
    )


def makeup_session_responses(
    professor: User, session: Session
) -> list[MakeupSessionResponse]:
    """A teacher's makeup sessions, after dropping cancelled ones nobody used."""
    obsolete_cancelled_ids = list(
        session.scalars(
            select(MakeupSession.id).where(
                MakeupSession.owner_id == professor.id,
                MakeupSession.status == SessionStatus.CANCELLED,
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
                MakeupSession.status != SessionStatus.CANCELLED,
            )
            .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
        )
    )
    return [makeup_session_response(item, session) for item in makeups]
