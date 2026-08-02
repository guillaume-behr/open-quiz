from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.grade_levels import ensure_grade_level
from app.models import (
    ClassTrainingQuestionBank,
    Quiz,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.schemas import StudentClassCreate, StudentClassResponse, StudentResponse

router = APIRouter(prefix="/api/classes", tags=["classes and students"])


def owned_class(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> StudentClass:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classe introuvable",
        )
    return student_class


def class_response(
    student_class: StudentClass,
    session: DbSession,
) -> StudentClassResponse:
    students = list(
        session.scalars(
            select(Student)
            .where(
                Student.class_id == student_class.id,
                Student.account_id.is_not(None),
            )
            .order_by(Student.display_name, Student.identifier, Student.id)
        )
    )
    completed_quiz_count = session.scalar(
        select(func.count(QuizSession.id))
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(
            QuizSession.class_id == student_class.id,
            QuizSession.status == "finished",
            Quiz.mode == "exam",
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
            QuizSession.status == "finished",
            Quiz.mode == "exam",
        )
        .order_by(
            QuizSession.started_at.desc(),
            QuizSession.created_at.desc(),
            QuizSession.id.desc(),
        )
        .limit(1)
    ).first()
    return StudentClassResponse(
        id=student_class.id,
        name=student_class.name,
        grade_level=student_class.grade_level,
        student_count=len(students),
        completed_quiz_count=completed_quiz_count or 0,
        latest_quiz_title=(latest_quiz[0] or latest_quiz[1]) if latest_quiz else None,
        latest_quiz_at=(latest_quiz[2] or latest_quiz[3]) if latest_quiz else None,
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


@router.get("", response_model=list[StudentClassResponse])
def list_classes(
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    search: Annotated[str, Query(max_length=120)] = "",
    grade_level: Annotated[str, Query(max_length=80)] = "",
) -> list[StudentClassResponse]:
    filters = [StudentClass.owner_id == professor.id]
    if search:
        filters.append(StudentClass.name.ilike(f"%{search}%"))
    if grade_level:
        filters.append(StudentClass.grade_level == grade_level)
    total = (
        session.scalar(select(func.count()).select_from(StudentClass).where(*filters))
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    classes = list(
        session.scalars(
            select(StudentClass)
            .where(*filters)
            .order_by(
                StudentClass.grade_level,
                StudentClass.name,
                StudentClass.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return [class_response(student_class, session) for student_class in classes]


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
        grade_level=payload.grade_level,
    )
    session.add(student_class)
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une classe porte déjà ce nom",
        ) from None
    session.refresh(student_class)
    return class_response(student_class, session)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    owned_class(class_id, professor, session)
    if (
        session.scalar(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id == class_id,
                Quiz.mode == "exam",
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette classe est utilisée par une salle d’attente active",
        )
    student_ids = select(Student.id).where(Student.class_id == class_id)
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id.in_(student_ids))
        .values(student_id=None)
    )
    session.execute(
        update(QuizSession)
        .where(QuizSession.class_id == class_id)
        .values(class_id=None)
    )
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.class_id == class_id
        )
    )
    session.execute(delete(Student).where(Student.class_id == class_id))
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
    account = session.scalar(
        select(StudentAccount).where(
            StudentAccount.id == account_id,
            StudentAccount.owner_id == professor.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Compte élève introuvable")
    membership = session.scalar(select(Student).where(Student.account_id == account.id))
    if membership is not None:
        if membership.class_id == class_id:
            return class_response(student_class, session)
        active_class_id = session.scalar(
            select(QuizSession.class_id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id.in_([membership.class_id, class_id]),
                Quiz.mode == "exam",
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
            .limit(1)
        )
        if active_class_id is not None:
            raise HTTPException(
                status_code=409,
                detail="Un élève ne peut pas être transféré pendant une session active",
            )
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
        raise HTTPException(
            status_code=409,
            detail="Cet identifiant existe déjà dans la classe",
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
        raise HTTPException(status_code=404, detail="Affectation introuvable")
    if (
        session.scalar(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id == class_id,
                Quiz.mode == "exam",
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
        )
        is not None
    ):
        raise HTTPException(status_code=409, detail="La classe a une session active")
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == membership.id)
        .values(student_id=None)
    )
    session.execute(delete(Student).where(Student.id == membership.id))
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
    student_class.name = payload.name
    student_class.grade_level = payload.grade_level
    ensure_grade_level(professor.id, payload.grade_level, session)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une classe porte déjà ce nom",
        ) from None
    session.refresh(student_class)
    return class_response(student_class, session)
