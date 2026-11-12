"""Response bodies describing quiz sessions to teachers and students."""

from collections.abc import Sequence
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
    question_maximum_scores,
    rounded_score,
    training_result,
)
from app.services.question_assignments import (
    accessible_question_positions,
    assigned_question_ids,
    current_question_id,
    load_session_question_assignments,
    session_question_ids,
)
from app.services.results import (
    AnswerStatistics,
    answer_statistics,
    students_and_classes,
)
from app.services.session_lifecycle import (
    answer_review_enabled,
    quiz_ends_at,
)
from app.session_status import ACTIVE_SESSION_STATUSES, took_part


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
            show_provisional_grades=quiz.show_provisional_grades,
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
        violation_count=participant.violation_count,
        last_violation_type=participant.last_violation_type,
        last_violation_at=participant.last_violation_at,
        joined_at=participant.joined_at,
    )


def session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    session: DbSession,
) -> QuizSessionResponse:
    return session_responses([(quiz_session, quiz)], session)[0]


def listed_participants(
    rows: Sequence[tuple[QuizSession, Quiz]],
    statistics: AnswerStatistics,
    session: Session,
) -> dict[int, list[QuizParticipant]]:
    """Who each session lists.

    A running session lists those present; a closed one also lists those who
    left, except anyone who left the waiting room without ever answering.
    """
    sessions_by_id = {quiz_session.id: quiz_session for quiz_session, _ in rows}
    listed: dict[int, list[QuizParticipant]] = {
        session_id: [] for session_id in sessions_by_id
    }
    for participant in session.scalars(
        select(QuizParticipant)
        .where(QuizParticipant.session_id.in_(sessions_by_id))
        .order_by(QuizParticipant.joined_at, QuizParticipant.id)
    ):
        quiz_session = sessions_by_id[participant.session_id]
        if quiz_session.status in ACTIVE_SESSION_STATUSES:
            if participant.left_at is not None:
                continue
        elif not took_part(
            participant,
            quiz_session,
            statistics.get((quiz_session.id, participant.id), (0, 0, 0))[0],
        ):
            continue
        listed[quiz_session.id].append(participant)
    return listed


def session_responses(
    rows: Sequence[tuple[QuizSession, Quiz]],
    session: Session,
) -> list[QuizSessionResponse]:
    """Teacher views of several sessions, with a fixed number of queries."""
    if not rows:
        return []
    session_ids = [quiz_session.id for quiz_session, _ in rows]
    statistics = answer_statistics(session_ids, session)
    participants_by_session = listed_participants(rows, statistics, session)
    common, by_student, by_identifier = load_session_question_assignments(
        session_ids, session
    )
    maximums = question_maximum_scores(
        list(
            {
                question_id
                for question_ids in (*common.values(), *by_identifier.values())
                for question_id in question_ids
            }
        ),
        session,
    )
    personalized_counts: dict[int, int] = {}
    for (session_id, _), question_ids in by_identifier.items():
        personalized_counts[session_id] = max(
            personalized_counts.get(session_id, 0), len(question_ids)
        )
    students_by_id, classes_by_id = students_and_classes(
        rows,
        [p for listed in participants_by_session.values() for p in listed],
        session,
    )

    responses = []
    for quiz_session, quiz in rows:
        participants = participants_by_session[quiz_session.id]
        maximum_scores = {
            participant.id: round(
                sum(
                    float(maximums.get(question_id) or 0)
                    for question_id in assigned_question_ids(
                        quiz_session.id,
                        participant.student_id,
                        participant.student_identifier,
                        common,
                        by_student,
                        by_identifier,
                    )
                ),
                2,
            )
            for participant in participants
        }
        total_questions = len(common[quiz_session.id]) or personalized_counts.get(
            quiz_session.id, 0
        )
        review_enabled = answer_review_enabled(quiz_session, quiz)
        participant_responses = []
        for participant in participants:
            counts = statistics.get((quiz_session.id, participant.id), (0, 0, 0))
            participant_responses.append(
                live_participant_response(
                    participant,
                    quiz_session,
                    counts,
                    participant_has_finished(
                        participant, counts[0], review_enabled, total_questions
                    ),
                    maximum_scores[participant.id],
                    students_by_id,
                )
            )
        student_class = (
            classes_by_id.get(quiz_session.class_id)
            if quiz_session.class_id is not None
            else None
        )
        responses.append(
            QuizSessionResponse(
                id=quiz_session.id,
                quiz_id=quiz.id,
                quiz_title=quiz_session.quiz_title or quiz.title,
                class_id=quiz_session.class_id,
                class_name=(
                    format_class_name(student_class.grade_level, student_class.name)
                    if student_class is not None
                    else quiz_session.class_name
                ),
                join_code=quiz_session.join_code,
                status=quiz_session.status,
                participant_count=len(participants),
                median_maximum_score=(
                    rounded_score(median(maximum_scores.values()))
                    if maximum_scores
                    else 0
                ),
                participants=participant_responses,
                total_questions=total_questions,
                created_at=quiz_session.created_at,
                started_at=quiz_session.started_at,
                ends_at=quiz_ends_at(quiz_session, quiz),
                grades_published_at=quiz_session.grades_published_at,
            )
        )
    return responses


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
    *,
    include_points: bool = False,
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
        total_points=(
            question_maximum_scores([question.id], session).get(question.id)
            if include_points
            else None
        ),
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
                include_points=quiz.mode == QuizMode.EXAM,
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
    return session_responses(
        [(quiz_session, quiz) for quiz_session, quiz in rows], session
    )


def makeup_session_response(
    makeup: MakeupSession, session: DbSession
) -> MakeupSessionResponse:
    return makeup_responses([makeup], session)[0]


def makeup_responses(
    makeups: Sequence[MakeupSession], session: Session
) -> list[MakeupSessionResponse]:
    """Make-up views with a fixed number of queries, whatever their children."""
    if not makeups:
        return []
    makeup_ids = [makeup.id for makeup in makeups]
    quizzes_by_makeup: dict[int, list[Quiz]] = {
        makeup_id: [] for makeup_id in makeup_ids
    }
    for makeup_id, quiz in session.execute(
        select(MakeupSessionQuiz.session_id, Quiz)
        .join(Quiz, Quiz.id == MakeupSessionQuiz.quiz_id)
        .where(MakeupSessionQuiz.session_id.in_(makeup_ids))
        .order_by(Quiz.title, Quiz.id)
    ):
        quizzes_by_makeup[makeup_id].append(quiz)
    children = list(
        session.scalars(
            select(QuizSession)
            .where(QuizSession.makeup_session_id.in_(makeup_ids))
            .order_by(QuizSession.id)
        )
    )
    child_rows = [
        (child, offered)
        for child in children
        for offered in quizzes_by_makeup[child.makeup_session_id or 0]
        if offered.id == child.quiz_id
    ]
    child_responses = session_responses(child_rows, session)
    children_by_makeup: dict[int, list[QuizSessionResponse]] = {
        makeup_id: [] for makeup_id in makeup_ids
    }
    for (child, _), response in zip(child_rows, child_responses, strict=True):
        children_by_makeup[child.makeup_session_id or 0].append(response)
    class_ids = {makeup.class_id for makeup in makeups if makeup.class_id is not None}
    classes_by_id = {
        student_class.id: student_class
        for student_class in session.scalars(
            select(StudentClass).where(StudentClass.id.in_(class_ids))
        )
    }

    responses = []
    for makeup in makeups:
        participants = [
            MakeupParticipantResponse(
                **participant.model_dump(),
                quiz_title=child.quiz_title,
                total_questions=child.total_questions,
            )
            for child in children_by_makeup[makeup.id]
            for participant in child.participants
        ]
        student_class = (
            classes_by_id.get(makeup.class_id) if makeup.class_id is not None else None
        )
        responses.append(
            MakeupSessionResponse(
                id=makeup.id,
                class_id=makeup.class_id,
                class_name=(
                    format_class_name(student_class.grade_level, student_class.name)
                    if student_class is not None
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
                    for quiz in quizzes_by_makeup[makeup.id]
                ],
                participant_count=len(participants),
                participants=participants,
                created_at=makeup.created_at,
            )
        )
    return responses


def active_makeup_session_responses(
    professor: User, session: Session
) -> list[MakeupSessionResponse]:
    """A teacher's make-ups still open, newest first: what the live feed shows.

    Finished ones only grow with time; they are listed, a page at a time, by
    GET /makeup/sessions.
    """
    makeups = session.scalars(
        select(MakeupSession)
        .where(
            MakeupSession.owner_id == professor.id,
            MakeupSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .order_by(MakeupSession.created_at.desc(), MakeupSession.id.desc())
    )
    return makeup_responses(list(makeups), session)
