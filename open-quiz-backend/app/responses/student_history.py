"""The results of a student's finished exams, as their history lists them."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.class_names import format_class_name
from app.domain.session_status import took_part
from app.enums import AnswerMode, QuizMode, SessionStatus
from app.models import (
    Question,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    Student,
    StudentClass,
)
from app.records.questions import load_question_records
from app.responses.answer_reviews import answer_review
from app.schemas.student_quizzes import StudentQuizHistoryAnswer, StudentQuizHistoryItem
from app.services.grading import question_maximum_scores, selected_choice_ids
from app.services.question_assignments import (
    assigned_question_ids,
    load_session_question_assignments,
)


@dataclass(frozen=True)
class HistoryRecords:
    """Everything a student's exam history reads, loaded once for all exams."""

    question_ids_by_participant: dict[int, list[int]]
    questions_by_id: dict[int, Question]
    choices_by_question: dict[int, list[QuestionChoice]]
    answers_by_participant_question: dict[tuple[int, int], QuizAnswer]
    question_points: dict[int, float]
    classes_by_id: dict[int, StudentClass]
    codes_by_question: dict[int, QuestionCode]
    provisional_grades_by_quiz: dict[int, bool]


def student_exam_participations(
    account_id: int, session: Session
) -> list[tuple[QuizSession, QuizParticipant]]:
    """A student account's finished exams they took part in, most recent first."""
    membership_ids = list(
        session.scalars(select(Student.id).where(Student.account_id == account_id))
    )
    if not membership_ids:
        return []
    rows = [
        (quiz_session, participant)
        for quiz_session, participant in session.execute(
            select(QuizSession, QuizParticipant)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizParticipant.student_id.in_(membership_ids),
                QuizSession.status == SessionStatus.FINISHED,
                QuizSession.started_at.is_not(None),
                Quiz.mode == QuizMode.EXAM,
            )
            .order_by(QuizSession.started_at.desc(), QuizSession.id.desc())
        )
    ]
    answered_counts: dict[int, int] = dict(
        session.execute(
            select(QuizAnswer.participant_id, func.count(QuizAnswer.id))
            .where(
                QuizAnswer.participant_id.in_(
                    [participant.id for _, participant in rows]
                )
            )
            .group_by(QuizAnswer.participant_id)
        ).all()
    )
    return [
        (quiz_session, participant)
        for quiz_session, participant in rows
        if took_part(participant, quiz_session, answered_counts.get(participant.id, 0))
    ]


def history_records(
    rows: list[tuple[QuizSession, QuizParticipant]], session: Session
) -> HistoryRecords:
    session_ids = [quiz_session.id for quiz_session, _ in rows]
    participant_ids = [participant.id for _, participant in rows]
    (
        common_by_session,
        personalized_by_student,
        personalized_by_identifier,
    ) = load_session_question_assignments(session_ids, session)
    question_ids_by_participant: dict[int, list[int]] = {}
    all_question_ids: set[int] = set()
    for quiz_session, participant in rows:
        question_ids = assigned_question_ids(
            quiz_session.id,
            participant.student_id,
            participant.student_identifier,
            common_by_session,
            personalized_by_student,
            personalized_by_identifier,
        )
        question_ids_by_participant[participant.id] = question_ids
        all_question_ids.update(question_ids)
    questions_by_id, choices_by_question = load_question_records(
        all_question_ids, session
    )
    class_ids = {
        quiz_session.class_id
        for quiz_session, _ in rows
        if quiz_session.class_id is not None
    }
    return HistoryRecords(
        provisional_grades_by_quiz=dict(
            session.execute(
                select(Quiz.id, Quiz.show_provisional_grades).where(
                    Quiz.id.in_({quiz_session.quiz_id for quiz_session, _ in rows})
                )
            ).all()
        ),
        question_ids_by_participant=question_ids_by_participant,
        questions_by_id=questions_by_id,
        choices_by_question=choices_by_question,
        answers_by_participant_question={
            (answer.participant_id, answer.question_id): answer
            for answer in session.scalars(
                select(QuizAnswer).where(QuizAnswer.participant_id.in_(participant_ids))
            )
        },
        question_points=question_maximum_scores(list(all_question_ids), session),
        classes_by_id={
            student_class.id: student_class
            for student_class in session.scalars(
                select(StudentClass).where(StudentClass.id.in_(class_ids))
            )
        },
        codes_by_question={
            code.question_id: code
            for code in session.scalars(
                select(QuestionCode).where(
                    QuestionCode.question_id.in_(all_question_ids)
                )
            )
        },
    )


def history_answer(
    question: Question,
    position: int,
    answer: QuizAnswer | None,
    records: HistoryRecords,
    *,
    correction_available: bool,
) -> StudentQuizHistoryAnswer:
    """How a student answered one question of a finished exam.

    Without the correction (grades unpublished, and the quiz shows no
    provisional grades), only the student's own answer.
    """
    question_choices = records.choices_by_question[question.id]
    q_code = records.codes_by_question.get(question.id)
    review = None
    if answer is not None:
        review = answer_review(
            answer,
            question,
            position,
            question_choices,
            records.question_points.get(question.id, 0),
            q_code,
        )
        submitted_answers = review.submitted_answers
        score = review.score
        max_score = review.max_score
        if question.answer_mode == AnswerMode.WRITTEN:
            is_correct = (
                (answer.score >= review.max_score)
                if answer.is_graded and review.max_score > 0
                else None
            )
        else:
            correct_ids = {
                choice.id for choice in question_choices if choice.is_correct
            }
            is_correct = selected_choice_ids(answer) == correct_ids
    else:
        submitted_answers = []
        score = 0.0
        max_score = float(records.question_points.get(question.id, 0))
        is_correct = False
    return StudentQuizHistoryAnswer(
        question_id=question.id,
        position=position + 1,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        code_content=q_code.content if q_code else None,
        code_language=q_code.language if q_code else None,
        response_language=question.response_language,
        submitted_answers=submitted_answers,
        expected_answers=(
            [choice.label for choice in question_choices if choice.is_correct]
            if correction_available
            else []
        ),
        score=score if correction_available else None,
        max_score=max_score,
        is_correct=is_correct if correction_available else None,
        feedback=review.feedback if review and correction_available else None,
    )


def history_item(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    records: HistoryRecords,
) -> StudentQuizHistoryItem:
    published = quiz_session.grades_published_at is not None
    # Before publication, the correction shows only as provisional, and only
    # when the quiz offers it; a session keeps the choice it was launched with.
    correction_available = published or (
        quiz_session.show_provisional_grades
        if quiz_session.show_provisional_grades is not None
        else records.provisional_grades_by_quiz.get(quiz_session.quiz_id, True)
    )
    question_ids = records.question_ids_by_participant[participant.id]
    answers_by_question = {
        question_id: records.answers_by_participant_question.get(
            (participant.id, question_id)
        )
        for question_id in question_ids
    }
    answers = [
        history_answer(
            question,
            position,
            answers_by_question.get(question.id),
            records,
            correction_available=correction_available,
        )
        for position, question_id in enumerate(question_ids)
        if (question := records.questions_by_id.get(question_id)) is not None
    ]
    return StudentQuizHistoryItem(
        session_id=quiz_session.id,
        quiz_title=quiz_session.quiz_title or "Quiz",
        class_name=(
            format_class_name(
                records.classes_by_id[quiz_session.class_id].grade_level,
                records.classes_by_id[quiz_session.class_id].name,
            )
            if quiz_session.class_id in records.classes_by_id
            else quiz_session.class_name
        ),
        started_at=quiz_session.started_at,
        grades_published=published,
        correction_available=correction_available,
        score=(
            round(
                sum(
                    answer.score
                    for answer in answers_by_question.values()
                    if answer is not None
                ),
                2,
            )
            if correction_available
            else None
        ),
        maximum_score=(
            round(
                sum(
                    records.question_points.get(question_id, 0)
                    for question_id in question_ids
                ),
                2,
            )
            if correction_available
            else None
        ),
        answers=answers,
    )


def student_quiz_history(
    account_id: int, session: Session
) -> list[StudentQuizHistoryItem]:
    """The finished exams a student account took part in, most recent first."""
    rows = student_exam_participations(account_id, session)
    if not rows:
        return []
    records = history_records(rows, session)
    return [
        history_item(quiz_session, participant, records)
        for quiz_session, participant in rows
    ]
