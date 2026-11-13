from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import DbSession, ProfessorUser
from app.enums import QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.grade_levels import (
    create_grade_level,
    delete_grade_level,
    ensure_grade_level,
    grade_level_order,
    list_grade_levels,
)
from app.models import (
    ClassTrainingQuestionBank,
    GradeLevel,
    MakeupSession,
    QuestionBank,
    Quiz,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import (
    LIKE_ESCAPE_CHARACTER,
    Paging,
    contains_pattern,
)
from app.schemas import (
    GradeLevelCreate,
    GradeLevelResponse,
    StudentClassCreate,
    StudentClassResponse,
    StudentResponse,
)
from app.session_status import ACTIVE_SESSION_STATUSES
from app.student_accounts import (
    owned_class,
    owned_student_account,
)
from app.student_memberships import (
    delete_student_membership,
    delete_unfinished_training_sessions,
)
from app.unique_names import write_unique_name

router = APIRouter(prefix="/api/classes", tags=["classes and students"])


def commit_unique_class(session: DbSession) -> None:
    write_unique_name(
        session,
        session.commit,
        "uq_student_class_owner_name",
        ErrorCode.CLASS_NAME_TAKEN,
        "Une classe porte déjà ce nom",
    )


def class_has_active_exam_session(class_id: int, session: DbSession) -> bool:
    return (
        session.scalar(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id == class_id,
                Quiz.mode == QuizMode.EXAM,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
        is not None
    )


def class_response(
    student_class: StudentClass,
    session: DbSession,
) -> StudentClassResponse:
    students = list(
        session.scalars(
            select(Student)
            .where(
                Student.class_id == student_class.id,
            )
            .order_by(Student.display_name, Student.identifier, Student.id)
        )
    )
    completed_quiz_count = session.scalar(
        select(func.count(QuizSession.id))
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.class_id == student_class.id,
            QuizSession.status == SessionStatus.FINISHED,
            Quiz.mode == QuizMode.EXAM,
        )
    )
    latest_quiz = session.execute(
        select(
            QuizSession.quiz_title,
            Quiz.title,
            QuizSession.started_at,
            QuizSession.created_at,
        )
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.class_id == student_class.id,
            QuizSession.status == SessionStatus.FINISHED,
            Quiz.mode == QuizMode.EXAM,
        )
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.created_at.desc(),
            QuizSession.id.desc(),
        )
        .limit(1)
    ).first()
    return class_response_from_details(
        student_class,
        students,
        completed_quiz_count or 0,
        (
            (latest_quiz[0] or latest_quiz[1], latest_quiz[2] or latest_quiz[3])
            if latest_quiz
            else None
        ),
    )


def class_response_from_details(
    student_class: StudentClass,
    students: list[Student],
    completed_quiz_count: int,
    latest_quiz: tuple[str, datetime] | None,
) -> StudentClassResponse:
    return StudentClassResponse(
        id=student_class.id,
        name=student_class.name,
        grade_level=student_class.grade_level,
        student_count=len(students),
        completed_quiz_count=completed_quiz_count,
        latest_quiz_title=latest_quiz[0] if latest_quiz else None,
        latest_quiz_at=latest_quiz[1] if latest_quiz else None,
        students=[
            StudentResponse(
                id=student.id,
                class_id=student.class_id,
                account_id=student.account_id,
                identifier=student.identifier,
                display_name=student.display_name,
                created_at=student.created_at,
            )
            for student in students
        ],
        created_at=student_class.created_at,
    )


def class_students(class_ids: list[int], session: Session) -> dict[int, list[Student]]:
    """The students with an account in each class, in alphabetical order."""
    students_by_class: dict[int, list[Student]] = {
        class_id: [] for class_id in class_ids
    }
    for student in session.scalars(
        select(Student)
        .where(
            Student.class_id.in_(class_ids),
        )
        .order_by(Student.display_name, Student.identifier, Student.id)
    ):
        students_by_class[student.class_id].append(student)
    return students_by_class


def completed_exam_counts(class_ids: list[int], session: Session) -> dict[int, int]:
    return {
        class_id: count
        for class_id, count in session.execute(
            select(QuizSession.class_id, func.count(QuizSession.id))
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id.in_(class_ids),
                QuizSession.status == SessionStatus.FINISHED,
                Quiz.mode == QuizMode.EXAM,
            )
            .group_by(QuizSession.class_id)
        )
        if class_id is not None
    }


def latest_exams(
    class_ids: list[int], session: Session
) -> dict[int, tuple[str, datetime]]:
    """Title and date of each class's most recent finished exam."""
    latest_ranked = (
        select(
            QuizSession.class_id.label("class_id"),
            func.coalesce(QuizSession.quiz_title, Quiz.title).label("title"),
            func.coalesce(QuizSession.started_at, QuizSession.created_at).label(
                "occurred_at"
            ),
            func.row_number()
            .over(
                partition_by=QuizSession.class_id,
                order_by=(
                    QuizSession.started_at.desc(),
                    QuizSession.created_at.desc(),
                    QuizSession.id.desc(),
                ),
            )
            .label("position"),
        )
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.class_id.in_(class_ids),
            QuizSession.status == SessionStatus.FINISHED,
            Quiz.mode == QuizMode.EXAM,
        )
        .subquery()
    )
    return {
        class_id: (title, occurred_at)
        for class_id, title, occurred_at in session.execute(
            select(
                latest_ranked.c.class_id,
                latest_ranked.c.title,
                latest_ranked.c.occurred_at,
            ).where(latest_ranked.c.position == 1)
        )
        if class_id is not None
    }


@router.get("/grade-levels", response_model=list[GradeLevelResponse])
def get_grade_levels(
    professor: ProfessorUser,
    session: DbSession,
) -> list[GradeLevel]:
    return list_grade_levels(professor.id, session)


@router.post(
    "/grade-levels",
    response_model=GradeLevelResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_grade_level(
    payload: GradeLevelCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> GradeLevel:
    return create_grade_level(professor.id, payload.name, session)


@router.delete("/grade-levels/{grade_level_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_grade_level(
    grade_level_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    delete_grade_level(professor.id, grade_level_id, session)


@router.get("", response_model=list[StudentClassResponse])
def list_classes(
    professor: ProfessorUser,
    session: DbSession,
    paging: Paging,
    search: Annotated[str, Query(max_length=120)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
) -> list[StudentClassResponse]:
    filters = [StudentClass.owner_id == professor.id]
    if search:
        filters.append(
            StudentClass.name.ilike(
                contains_pattern(search), escape=LIKE_ESCAPE_CHARACTER
            )
        )
    if grade_level:
        filters.append(StudentClass.grade_level == grade_level)
    total = (
        session.scalar(select(func.count()).select_from(StudentClass).where(*filters))
        or 0
    )
    paging.set_total(total)
    classes = list(
        session.scalars(
            select(StudentClass)
            .where(*filters)
            .order_by(
                grade_level_order(StudentClass.grade_level),
                StudentClass.grade_level,
                StudentClass.name,
                StudentClass.id,
            )
            .offset(paging.offset)
            .limit(paging.page_size)
        )
    )
    if not classes:
        return []

    class_ids = [student_class.id for student_class in classes]
    students_by_class = class_students(class_ids, session)
    completed_counts = completed_exam_counts(class_ids, session)
    latest_quizzes = latest_exams(class_ids, session)
    return [
        class_response_from_details(
            student_class,
            students_by_class[student_class.id],
            completed_counts.get(student_class.id, 0),
            latest_quizzes.get(student_class.id),
        )
        for student_class in classes
    ]


@router.post(
    "",
    response_model=StudentClassResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_class(
    payload: StudentClassCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> StudentClassResponse:
    student_class = StudentClass(
        owner_id=professor.id,
        name=payload.name,
        grade_level=ensure_grade_level(professor.id, payload.grade_level, session),
    )
    session.add(student_class)
    commit_unique_class(session)
    session.refresh(student_class)
    return class_response(student_class, session)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    owned_class(class_id, professor, session)
    if class_has_active_exam_session(class_id, session):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.CLASS_USED_BY_WAITING_ROOM,
            "Cette classe est utilisée par une salle d’attente active",
        )
    if (
        session.scalar(
            select(MakeupSession.id).where(
                MakeupSession.class_id == class_id,
                MakeupSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
        )
        is not None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.CLASS_USED_BY_MAKEUP,
            "Cette classe est utilisée par un rattrapage actif",
        )
    student_ids = list(
        session.scalars(select(Student.id).where(Student.class_id == class_id))
    )
    delete_unfinished_training_sessions(student_ids, session)
    # Memberships and their make-up selections cascade; sessions, make-up
    # sessions and participants keep their history without the class.
    session.execute(delete(StudentClass).where(StudentClass.id == class_id))
    session.commit()


@router.post(
    "/{class_id}/accounts/{account_id}",
    response_model=StudentClassResponse,
)
def assign_student_account(
    class_id: int,
    account_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> StudentClassResponse:
    student_class = owned_class(class_id, professor, session)
    account = owned_student_account(account_id, professor.id, session)
    membership = session.scalar(select(Student).where(Student.account_id == account.id))
    if membership is not None:
        if membership.class_id == class_id:
            return class_response(student_class, session)
        active_class_id = session.scalar(
            select(QuizSession.class_id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id.in_([membership.class_id, class_id]),
                Quiz.mode == QuizMode.EXAM,
                QuizSession.status.in_(ACTIVE_SESSION_STATUSES),
            )
            .limit(1)
        )
        if active_class_id is not None:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                ErrorCode.STUDENT_TRANSFER_DURING_SESSION,
                "Un élève ne peut pas être transféré pendant une session active",
            )
        delete_unfinished_training_sessions([membership.id], session)
        membership.class_id = class_id
        membership.identifier = account.identifier
        membership.display_name = account.display_name
    else:
        session.add(
            Student(
                class_id=class_id,
                account_id=account.id,
                identifier=account.identifier,
                display_name=account.display_name,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.STUDENT_IDENTIFIER_TAKEN,
            "Cet identifiant existe déjà dans la classe",
        ) from None
    return class_response(student_class, session)


@router.delete(
    "/{class_id}/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_student_account(
    class_id: int,
    account_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    owned_class(class_id, professor, session)
    membership = session.scalar(
        select(Student)
        .join(StudentAccount, StudentAccount.id == Student.account_id)
        .where(
            Student.class_id == class_id,
            Student.account_id == account_id,
            StudentAccount.owner_id == professor.id,
        )
    )
    if membership is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.CLASS_ASSIGNMENT_NOT_FOUND,
            "Affectation introuvable",
        )
    if class_has_active_exam_session(class_id, session):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.CLASS_HAS_ACTIVE_SESSION,
            "La classe a une session active",
        )
    delete_student_membership(membership.id, session)
    session.commit()


@router.post(
    "/{class_id}/update",
    response_model=StudentClassResponse,
)
def update_class(
    class_id: int,
    payload: StudentClassCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> StudentClassResponse:
    student_class = owned_class(class_id, professor, session)
    grade_level = ensure_grade_level(professor.id, payload.grade_level, session)
    if student_class.grade_level != grade_level:
        mismatched_bank_ids = (
            select(QuestionBank.id)
            .join(
                ClassTrainingQuestionBank,
                ClassTrainingQuestionBank.question_bank_id == QuestionBank.id,
            )
            .where(
                ClassTrainingQuestionBank.class_id == student_class.id,
                QuestionBank.grade_level != grade_level,
            )
        )
        session.execute(
            delete(ClassTrainingQuestionBank).where(
                ClassTrainingQuestionBank.class_id == student_class.id,
                ClassTrainingQuestionBank.question_bank_id.in_(mismatched_bank_ids),
            )
        )
    student_class.name = payload.name
    student_class.grade_level = grade_level
    commit_unique_class(session)
    session.refresh(student_class)
    return class_response(student_class, session)
