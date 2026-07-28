from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.models import (
    QuizParticipant,
    QuizSession,
    Student,
    StudentClass,
)
from app.schemas import (
    StudentClassCreate,
    StudentClassResponse,
    StudentCreate,
    StudentResponse,
)

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
            detail="Class not found",
        )
    return student_class


def owned_student(
    student_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Student:
    student = session.scalar(
        select(Student)
        .join(StudentClass, StudentClass.id == Student.class_id)
        .where(
            Student.id == student_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )
    return student


def class_response(
    student_class: StudentClass,
    session: DbSession,
) -> StudentClassResponse:
    students = list(
        session.scalars(
            select(Student)
            .where(Student.class_id == student_class.id)
            .order_by(Student.display_name, Student.identifier, Student.id)
        )
    )
    return StudentClassResponse(
        id=student_class.id,
        name=student_class.name,
        grade_level=student_class.grade_level,
        student_count=len(students),
        students=[
            StudentResponse(
                id=student.id,
                class_id=student.class_id,
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
) -> list[StudentClassResponse]:
    classes = list(
        session.scalars(
            select(StudentClass)
            .where(StudentClass.owner_id == professor.id)
            .order_by(
                StudentClass.grade_level,
                StudentClass.name,
                StudentClass.id,
            )
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
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name already exists",
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
    if session.scalar(
        select(QuizSession.id).where(
            QuizSession.class_id == class_id,
            QuizSession.status == "waiting",
        )
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This class is used by an active quiz waiting room",
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
    session.execute(delete(Student).where(Student.class_id == class_id))
    session.execute(delete(StudentClass).where(StudentClass.id == class_id))
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
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name already exists",
        ) from None
    session.refresh(student_class)
    return class_response(student_class, session)


@router.post(
    "/{class_id}/students",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_student(
    class_id: int,
    payload: StudentCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> Student:
    owned_class(class_id, professor, session)
    student = Student(
        class_id=class_id,
        identifier=payload.identifier,
        display_name=payload.display_name,
    )
    session.add(student)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student identifier already exists in the class",
        ) from None
    session.refresh(student)
    return student


@router.post(
    "/students/{student_id}/update",
    response_model=StudentResponse,
)
def update_student(
    student_id: int,
    payload: StudentCreate,
    professor: ProfessorUser,
    session: DbSession,
) -> Student:
    student = owned_student(student_id, professor, session)
    student.identifier = payload.identifier
    student.display_name = payload.display_name
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student identifier already exists in the class",
        ) from None
    session.refresh(student)
    return student


@router.delete(
    "/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_student(
    student_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    owned_student(student_id, professor, session)
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == student_id)
        .values(student_id=None)
    )
    session.execute(delete(Student).where(Student.id == student_id))
    session.commit()
