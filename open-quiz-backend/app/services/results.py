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
from statistics import median

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.class_names import format_class_name
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
)
from app.services.question_assignments import (
    assigned_question_ids,
    load_session_question_assignments,
)
from app.services.session_lifecycle import (
    quiz_ends_at,
)

SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_cell(value: str) -> str:
    trimmed = value.lstrip()
    if value.startswith(("\t", "\r", "\n")) or trimmed.startswith(
        SPREADSHEET_FORMULA_PREFIXES
    ):
        return f"'{value}"
    return value


def finished_session_responses(
    rows: Sequence[tuple[QuizSession, Quiz]],
    session: Session,
) -> list[QuizSessionResponse]:
    """Build finished-session responses with a fixed number of queries."""
    if not rows:
        return []
    session_ids = [quiz_session.id for quiz_session, _ in rows]

    participants_by_session: dict[int, list[QuizParticipant]] = defaultdict(list)
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
    answer_statistics = {
        (session_id, participant_id): (
            answered_count,
            float(score),
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

    sessions_by_id = {quiz_session.id: quiz_session for quiz_session, _ in rows}
    for participant in participants:
        qs = sessions_by_id.get(participant.session_id)
        answered_count = answer_statistics.get(
            (participant.session_id, participant.id), (0, 0, 0)
        )[0]
        if (
            participant.left_at is not None
            and qs is not None
            and (qs.started_at is None or participant.left_at <= qs.started_at)
            and answered_count == 0
        ):
            continue
        participants_by_session[participant.session_id].append(participant)

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
                    float(median(participant_maximums.values()))
                    if participant_maximums
                    else 0
                ),
                participants=[
                    QuizParticipantResponse(
                        id=participant.id,
                        student_identifier=participant.student_identifier,
                        student_display_name=(
                            students_by_id[participant.student_id].display_name
                            if participant.student_id in students_by_id
                            else participant.student_display_name
                        ),
                        answered_count=answer_statistics.get(
                            (quiz_session.id, participant.id), (0, 0, 0)
                        )[0],
                        score=answer_statistics.get(
                            (quiz_session.id, participant.id), (0, 0, 0)
                        )[1],
                        maximum_score=participant_maximums[participant.id],
                        pending_manual_grading_count=answer_statistics.get(
                            (quiz_session.id, participant.id), (0, 0, 0)
                        )[2],
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
) -> Iterator[str]:
    """Stream a class's finished exam results as CSV, one participant per row.

    The response outlives the request's database session, so the rows are
    read through a session of their own, in batches of 50 sessions.
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
            Quiz.mode == "exam",
            QuizSession.class_id == class_id,
            QuizSession.status == "finished",
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
