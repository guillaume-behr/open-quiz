"""Response bodies describing quiz and make-up sessions to teachers.

Each builder covers several sessions with a fixed number of queries, on the
statistics helpers of app/services/results.py.
"""

from collections.abc import Sequence
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import DbSession
from app.domain.class_names import format_class_name
from app.domain.session_status import ACTIVE_SESSION_STATUSES, took_part
from app.enums import QuizMode, SessionStatus
from app.models import (
    MakeupSession,
    MakeupSessionQuiz,
    Quiz,
    QuizParticipant,
    QuizSession,
    StudentClass,
    User,
)
from app.schemas.quizzes import (
    MakeupParticipantResponse,
    MakeupQuizOption,
    MakeupSessionResponse,
    QuizSessionResponse,
)
from app.services.grading import question_maximum_scores, rounded_score
from app.services.question_assignments import (
    assigned_question_ids,
    load_session_question_assignments,
)
from app.services.results import (
    AnswerStatistics,
    answer_statistics,
    participant_response,
    students_and_classes,
)
from app.services.session_lifecycle import answer_review_enabled, quiz_ends_at


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
        finished_session = quiz_session.status == SessionStatus.FINISHED
        participant_responses = []
        for participant in participants:
            counts = statistics.get((quiz_session.id, participant.id), (0, 0, 0))
            participant_responses.append(
                participant_response(
                    participant,
                    counts,
                    maximum_scores[participant.id],
                    students_by_id,
                    has_finished=participant_has_finished(
                        participant, counts[0], review_enabled, total_questions
                    ),
                    show_grades=finished_session,
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
