"""Quiz results: summaries of finished sessions and their CSV export.

finished_session_responses summarizes several finished sessions at once,
with a constant number of queries. The CSV export streams those summaries
with its own database session, since it outlives the request's, and guards
every free-text cell against spreadsheet formula injection.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from statistics import median

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.class_names import format_class_name
from app.enums import QuizMode, SessionStatus
from app.models import (
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    Student,
    StudentClass,
)
from app.schemas import (
    QuizParticipantResponse,
    QuizSessionResponse,
)
from app.services.grading import (
    question_maximum_scores,
    rounded_score,
)
from app.services.question_assignments import (
    assigned_question_ids,
    load_session_question_assignments,
)
from app.services.session_lifecycle import (
    quiz_ends_at,
)
from app.session_retention import retained_exam_result
from app.session_status import took_part

SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_cell(value: str) -> str:
    trimmed = value.lstrip()
    if value.startswith(("\t", "\r", "\n")) or trimmed.startswith(
        SPREADSHEET_FORMULA_PREFIXES
    ):
        return f"'{value}"
    return value


AnswerStatistics = dict[tuple[int, int], tuple[int, float, int]]


def answer_statistics(session_ids: list[int], session: Session) -> AnswerStatistics:
    """Answers given, score and answers awaiting grading, per participant."""
    return {
        (session_id, participant_id): (
            answered_count,
            rounded_score(score),
            pending_count or 0,
        )
        for session_id, participant_id, answered_count, score, pending_count in session.execute(
            select(
                QuizAnswer.session_id,
                QuizAnswer.participant_id,
                func.count(QuizAnswer.id),
                func.coalesce(func.sum(QuizAnswer.score), 0),
                func.sum(case((QuizAnswer.is_graded.is_(False), 1), else_=0)),
            )
            .where(QuizAnswer.session_id.in_(session_ids))
            .group_by(QuizAnswer.session_id, QuizAnswer.participant_id)
        )
    }


def counted_participants(
    rows: Sequence[tuple[QuizSession, Quiz]],
    participants: list[QuizParticipant],
    statistics: AnswerStatistics,
) -> dict[int, list[QuizParticipant]]:
    """Each session's participants, without those who left before it started.

    Someone who left the waiting room and never answered took no part in the
    exam, so the result does not list them.
    """
    participants_by_session: dict[int, list[QuizParticipant]] = defaultdict(list)
    sessions_by_id = {quiz_session.id: quiz_session for quiz_session, _ in rows}
    for participant in participants:
        qs = sessions_by_id.get(participant.session_id)
        answered_count = statistics.get(
            (participant.session_id, participant.id), (0, 0, 0)
        )[0]
        if qs is not None and not took_part(participant, qs, answered_count):
            continue
        participants_by_session[participant.session_id].append(participant)
    return participants_by_session


def students_and_classes(
    rows: Sequence[tuple[QuizSession, Quiz]],
    participants: list[QuizParticipant],
    session: Session,
) -> tuple[dict[int, Student], dict[int, StudentClass]]:
    """Current names of the students and classes, which may have changed."""
    student_ids = {
        participant.student_id
        for participant in participants
        if participant.student_id is not None
    }
    students_by_id = {
        student.id: student
        for student in session.scalars(
            select(Student).where(Student.id.in_(student_ids))
        )
    }
    class_ids = {
        quiz_session.class_id
        for quiz_session, _ in rows
        if quiz_session.class_id is not None
    }
    classes_by_id = {
        student_class.id: student_class
        for student_class in session.scalars(
            select(StudentClass).where(StudentClass.id.in_(class_ids))
        )
    }
    return students_by_id, classes_by_id


def participant_response(
    participant: QuizParticipant,
    counts: tuple[int, float, int],
    maximum_score: float,
    students_by_id: dict[int, Student],
    *,
    has_finished: bool = False,
    show_grades: bool = True,
) -> QuizParticipantResponse:
    """One participant's line in a teacher's view of a session.

    ``counts`` holds the answers given, the score and the answers awaiting
    grading. A running session hides the score and the grading backlog.
    """
    answered_count, score, pending = counts
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
        score=score if show_grades else 0,
        maximum_score=maximum_score,
        pending_manual_grading_count=pending if show_grades else 0,
        violation_count=participant.violation_count,
        last_violation_type=participant.last_violation_type,
        last_violation_at=participant.last_violation_at,
        joined_at=participant.joined_at,
    )


def finished_session_responses(
    rows: Sequence[tuple[QuizSession, Quiz]],
    session: Session,
) -> list[QuizSessionResponse]:
    """Build finished-session responses with a fixed number of queries."""
    if not rows:
        return []
    session_ids = [quiz_session.id for quiz_session, _ in rows]

    participants = list(
        session.scalars(
            select(QuizParticipant)
            .where(QuizParticipant.session_id.in_(session_ids))
            .order_by(
                QuizParticipant.session_id,
                QuizParticipant.joined_at,
                QuizParticipant.id,
            )
        )
    )
    statistics = answer_statistics(session_ids, session)

    participants_by_session = counted_participants(rows, participants, statistics)

    (
        common_by_session,
        personalized_by_student,
        personalized_by_identifier,
    ) = load_session_question_assignments(session_ids, session)
    personalized_counts: dict[int, int] = {}
    all_assigned_question_ids = {
        question_id
        for question_ids in (
            *common_by_session.values(),
            *personalized_by_identifier.values(),
        )
        for question_id in question_ids
    }
    for (session_id, _), question_ids in personalized_by_identifier.items():
        personalized_counts[session_id] = max(
            personalized_counts.get(session_id, 0), len(question_ids)
        )

    maximums = question_maximum_scores(list(all_assigned_question_ids), session)
    students_by_id, classes_by_id = students_and_classes(rows, participants, session)

    responses: list[QuizSessionResponse] = []
    for quiz_session, quiz in rows:
        session_participants = participants_by_session[quiz_session.id]
        participant_maximums: dict[int, float] = {}
        for participant in session_participants:
            question_ids = assigned_question_ids(
                quiz_session.id,
                participant.student_id,
                participant.student_identifier,
                common_by_session,
                personalized_by_student,
                personalized_by_identifier,
            )
            participant_maximums[participant.id] = round(
                sum(maximums.get(question_id, 0) for question_id in question_ids),
                2,
            )
        class_name = quiz_session.class_name
        if quiz_session.class_id in classes_by_id:
            student_class = classes_by_id[quiz_session.class_id]
            class_name = format_class_name(
                student_class.grade_level, student_class.name
            )
        responses.append(
            QuizSessionResponse(
                id=quiz_session.id,
                quiz_id=quiz.id,
                quiz_title=quiz_session.quiz_title or quiz.title,
                class_id=quiz_session.class_id,
                class_name=class_name,
                join_code=quiz_session.join_code,
                status=quiz_session.status,
                participant_count=len(session_participants),
                median_maximum_score=(
                    rounded_score(median(participant_maximums.values()))
                    if participant_maximums
                    else 0
                ),
                participants=[
                    participant_response(
                        participant,
                        statistics.get((quiz_session.id, participant.id), (0, 0, 0)),
                        participant_maximums[participant.id],
                        students_by_id,
                    )
                    for participant in session_participants
                ],
                total_questions=(
                    len(common_by_session[quiz_session.id])
                    or personalized_counts.get(quiz_session.id, 0)
                ),
                created_at=quiz_session.created_at,
                started_at=quiz_session.started_at,
                ends_at=quiz_ends_at(quiz_session, quiz),
                grades_published_at=quiz_session.grades_published_at,
            )
        )
    return responses


def stream_results_csv(
    session_factory: Callable[[], Session],
    owner_id: int,
    class_id: int,
    quiz_id: int | None,
    *,
    retained_after: datetime,
) -> Iterator[str]:
    """Stream a class's finished exam results as CSV, one participant per row.

    The response outlives the request's database session, so the rows are
    read through a session of their own, in batches of 50 sessions. Results
    started before ``retained_after`` are past retention and left out.
    """
    output = io.StringIO(newline="")
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
    yield "\ufeff" + output.getvalue()
    output.seek(0)
    output.truncate(0)

    with session_factory() as export_session:
        export_filters = [
            Quiz.owner_id == owner_id,
            Quiz.mode == QuizMode.EXAM,
            QuizSession.class_id == class_id,
            QuizSession.status == SessionStatus.FINISHED,
            retained_exam_result(retained_after),
        ]
        if quiz_id is not None:
            export_filters.append(QuizSession.quiz_id == quiz_id)
        ordered_session_ids = list(
            export_session.scalars(
                select(QuizSession.id)
                .join(Quiz, Quiz.id == QuizSession.quiz_id)
                .where(*export_filters)
                .order_by(
                    QuizSession.started_at.desc(),
                    QuizSession.created_at.desc(),
                    QuizSession.id.desc(),
                )
            )
        )
        for offset in range(0, len(ordered_session_ids), 50):
            batch_ids = ordered_session_ids[offset : offset + 50]
            batch_rows = list(
                export_session.execute(
                    select(QuizSession, Quiz)
                    .join(Quiz, Quiz.id == QuizSession.quiz_id)
                    .where(QuizSession.id.in_(batch_ids))
                )
            )
            rows_by_id = {row[0].id: row for row in batch_rows}
            ordered_rows = [rows_by_id[session_id] for session_id in batch_ids]
            for result in finished_session_responses(ordered_rows, export_session):
                result_date = result.started_at or result.created_at
                for participant in result.participants:
                    writer.writerow(
                        [
                            safe_spreadsheet_cell(result.class_name or ""),
                            safe_spreadsheet_cell(result.quiz_title),
                            result_date.isoformat(),
                            safe_spreadsheet_cell(participant.student_identifier),
                            safe_spreadsheet_cell(
                                participant.student_display_name or ""
                            ),
                            participant.answered_count,
                            result.total_questions,
                            participant.score,
                            participant.pending_manual_grading_count,
                            participant.violation_count,
                        ]
                    )
                if output.tell():
                    yield output.getvalue()
                    output.seek(0)
                    output.truncate(0)
