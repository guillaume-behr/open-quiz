from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.grade_levels import ensure_grade_level
from app.models import (
    ClassTrainingQuestionBank,
    GradeLevel,
    MakeupSession,
    MakeupSessionSelection,
    QuestionBank,
    Quiz,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.routers.students import generated_student_password
from app.schemas import (
    ClassBatchImport,
    ClassBatchImportResponse,
    StudentClassCreate,
    StudentClassResponse,
    StudentResponse,
)
from app.security import encrypt_student_password, hash_password
from app.student_memberships import (
    delete_student_membership,
    delete_unfinished_training_sessions,
)

router = APIRouter(prefix="/api/classes", tags=["classes and students"])


@router.post("/import", response_model=ClassBatchImportResponse, status_code=201)
def import_classes(
    payload: ClassBatchImport,
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
) -> ClassBatchImportResponse:
    class_names = [item.name.casefold() for item in payload.classes]
    identifiers = [
        student.identifier for item in payload.classes for student in item.students
    ]
    if len(class_names) != len(set(class_names)) or len(identifiers) != len(
        set(identifiers)
    ):
        raise HTTPException(status_code=422, detail="Le fichier contient des doublons")
    existing_levels = set(
        session.scalars(
            select(GradeLevel.name).where(GradeLevel.owner_id == professor.id)
        )
    )
    invalid_levels = sorted(
        {item.grade_level for item in payload.classes} - existing_levels
    )
    if invalid_levels:
        raise HTTPException(
            status_code=422, detail=f"Niveau invalide : {', '.join(invalid_levels)}"
        )
    if (
        session.scalar(
            select(StudentClass.id)
            .where(
                StudentClass.owner_id == professor.id,
                func.lower(StudentClass.name).in_(class_names),
            )
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(status_code=409, detail="Une classe existe déjà")
    if (
        identifiers
        and session.scalar(
            select(StudentAccount.id)
            .where(StudentAccount.identifier.in_(identifiers))
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=409, detail="Un identifiant élève est déjà utilisé"
        )
    try:
        for item in payload.classes:
            student_class = StudentClass(
                owner_id=professor.id, name=item.name, grade_level=item.grade_level
            )
            session.add(student_class)
            session.flush()
            for imported in item.students:
                password = generated_student_password()
                account = StudentAccount(
                    owner_id=professor.id,
                    identifier=imported.identifier,
                    display_name=imported.display_name,
                    password_hash=hash_password(password),
                    encrypted_password=encrypt_student_password(
                        password,
                        request.app.state.settings.student_credential_encryption_key,
                    ),
                    is_active=True,
                )
                session.add(account)
                session.flush()
                session.add(
                    Student(
                        class_id=student_class.id,
                        account_id=account.id,
                        identifier=account.identifier,
                        display_name=account.display_name,
                    )
                )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Conflit avec les données existantes"
        ) from None
    return ClassBatchImportResponse(
        class_count=len(payload.classes), student_count=len(identifiers)
    )


def commit_unique_class(session: DbSession) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une classe porte déjà ce nom",
        ) from None


def class_has_active_exam_session(class_id: int, session: DbSession) -> bool:
    return (
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
    )


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
                StudentClass.name,
                StudentClass.grade_level,
                StudentClass.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    if not classes:
        return []

    class_ids = [student_class.id for student_class in classes]
    students_by_class: dict[int, list[Student]] = {
        class_id: [] for class_id in class_ids
    }
    for student in session.scalars(
        select(Student)
        .where(
            Student.class_id.in_(class_ids),
            Student.account_id.is_not(None),
        )
        .order_by(Student.display_name, Student.identifier, Student.id)
    ):
        students_by_class[student.class_id].append(student)

    completed_counts = {
        class_id: count
        for class_id, count in session.execute(
            select(QuizSession.class_id, func.count(QuizSession.id))
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id.in_(class_ids),
                QuizSession.status == "finished",
                Quiz.mode == "exam",
            )
            .group_by(QuizSession.class_id)
        )
        if class_id is not None
    }
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
            QuizSession.status == "finished",
            Quiz.mode == "exam",
        )
        .subquery()
    )
    latest_quizzes = {
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
        grade_level=payload.grade_level,
    )
    session.add(student_class)
    ensure_grade_level(professor.id, payload.grade_level, session)
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette classe est utilisée par une salle d’attente active",
        )
    if (
        session.scalar(
            select(MakeupSession.id).where(
                MakeupSession.class_id == class_id,
                MakeupSession.status.in_(["waiting", "in_progress", "paused"]),
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette classe est utilisée par un rattrapage actif",
        )
    student_ids = list(
        session.scalars(select(Student.id).where(Student.class_id == class_id))
    )
    delete_unfinished_training_sessions(student_ids, session)
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
        update(MakeupSession)
        .where(MakeupSession.class_id == class_id)
        .values(class_id=None)
    )
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.class_id == class_id
        )
    )
    session.execute(
        delete(MakeupSessionSelection).where(
            MakeupSessionSelection.student_id.in_(student_ids)
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
    if class_has_active_exam_session(class_id, session):
        raise HTTPException(status_code=409, detail="La classe a une session active")
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
    if student_class.grade_level != payload.grade_level:
        mismatched_bank_ids = (
            select(QuestionBank.id)
            .join(
                ClassTrainingQuestionBank,
                ClassTrainingQuestionBank.question_bank_id == QuestionBank.id,
            )
            .where(
                ClassTrainingQuestionBank.class_id == student_class.id,
                QuestionBank.grade_level != payload.grade_level,
            )
        )
        session.execute(
            delete(ClassTrainingQuestionBank).where(
                ClassTrainingQuestionBank.class_id == student_class.id,
                ClassTrainingQuestionBank.question_bank_id.in_(mismatched_bank_ids),
            )
        )
    student_class.name = payload.name
    student_class.grade_level = payload.grade_level
    ensure_grade_level(professor.id, payload.grade_level, session)
    commit_unique_class(session)
    session.refresh(student_class)
    return class_response(student_class, session)
