import json
import re
import unicodedata

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.grade_levels import ensure_grade_level
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
    StudentImportBatch,
    StudentResponse,
)

router = APIRouter(prefix="/api/classes", tags=["classes and students"])


def identifier_base(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name)
    ascii_name = normalized.encode("ascii", "ignore").decode().lower()
    parts = re.findall(r"[a-z0-9]+", ascii_name)
    return ".".join(parts)[:72] or "eleve"


def generated_student_identifier(
    class_id: int,
    display_name: str,
    session: DbSession,
    excluded_student_id: int | None = None,
) -> str:
    base = identifier_base(display_name)
    existing = set(
        session.scalars(
            select(Student.identifier).where(
                Student.class_id == class_id,
                *(
                    [Student.id != excluded_student_id]
                    if excluded_student_id is not None
                    else []
                ),
            )
        )
    )
    if base not in existing:
        return base
    suffix = 2
    while f"{base[: 80 - len(str(suffix))]}{suffix}" in existing:
        suffix += 1
    return f"{base[: 80 - len(str(suffix))]}{suffix}"


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
            detail="Élève introuvable",
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
    completed_quiz_count = session.scalar(
        select(func.count(QuizSession.id)).where(
            QuizSession.class_id == student_class.id,
            QuizSession.status == "finished",
        )
    )
    return StudentClassResponse(
        id=student_class.id,
        name=student_class.name,
        grade_level=student_class.grade_level,
        student_count=len(students),
        completed_quiz_count=completed_quiz_count or 0,
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
            select(QuizSession.id).where(
                QuizSession.class_id == class_id,
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


@router.get("/{class_id}/students/export")
def export_students(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    student_class = owned_class(class_id, professor, session)
    students = session.scalars(
        select(Student)
        .where(Student.class_id == class_id)
        .order_by(Student.display_name, Student.identifier, Student.id)
    )
    content = json.dumps(
        {
            "version": 1,
            "class": {
                "name": student_class.name,
                "grade_level": student_class.grade_level,
            },
            "students": [
                {
                    "identifier": student.identifier,
                    "display_name": student.display_name,
                }
                for student in students
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    return Response(
        content=f"{content}\n",
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="classe-{student_class.id}-eleves.json"'
            )
        },
    )


@router.post(
    "/{class_id}/students/import",
    response_model=StudentClassResponse,
)
def import_students(
    class_id: int,
    payload: StudentImportBatch,
    professor: ProfessorUser,
    session: DbSession,
) -> StudentClassResponse:
    student_class = owned_class(class_id, professor, session)
    imported_identifiers = [student.identifier for student in payload.students]
    if imported_identifiers and session.scalar(
        select(Student.id)
        .where(
            Student.class_id == class_id,
            Student.identifier.in_(imported_identifiers),
        )
        .limit(1)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un identifiant du fichier existe déjà dans cette classe",
        )
    session.add_all(
        Student(
            class_id=class_id,
            identifier=student.identifier,
            display_name=student.display_name,
        )
        for student in payload.students
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le fichier contient un identifiant déjà utilisé",
        ) from None
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
        identifier=payload.identifier
        or generated_student_identifier(class_id, payload.display_name, session),
        display_name=payload.display_name,
    )
    session.add(student)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet identifiant d’élève existe déjà dans la classe",
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
    student.identifier = payload.identifier or generated_student_identifier(
        student.class_id,
        payload.display_name,
        session,
        excluded_student_id=student.id,
    )
    student.display_name = payload.display_name
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet identifiant d’élève existe déjà dans la classe",
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
    student = owned_student(student_id, professor, session)
    if (
        session.scalar(
            select(QuizSession.id).where(
                QuizSession.class_id == student.class_id,
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet élève participe à une session de quiz active",
        )
    session.execute(
        update(QuizParticipant)
        .where(QuizParticipant.student_id == student_id)
        .values(student_id=None)
    )
    session.execute(delete(Student).where(Student.id == student_id))
    session.commit()
