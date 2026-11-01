"""Class imports: create several classes and their students from one file.

The example shows the expected format; an import creates every class, its
student accounts and their memberships in one transaction, or nothing.
"""

import json

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, ProfessorUser
from app.errors import ErrorCode, api_error
from app.grade_levels import (
    grade_level_import_context,
)
from app.models import (
    GradeLevel,
    Student,
    StudentAccount,
    StudentClass,
)
from app.schemas import (
    ClassBatchImport,
    ClassBatchImportResponse,
)
from app.security import encrypt_student_password, hash_password
from app.student_accounts import generated_student_password

router = APIRouter(prefix="/api/classes", tags=["classes and students"])


@router.get("/example")
def download_class_import_example(
    professor: ProfessorUser,
    session: DbSession,
) -> Response:
    available_grade_levels, grade_level_comment = grade_level_import_context(
        professor.id, session
    )
    example = {
        "classes": [
            {
                "name": "TG1",
                "_comment_grade_level": grade_level_comment,
                "grade_level": available_grade_levels[0]
                if available_grade_levels
                else "Tle",
                "students": [
                    {"identifier": "martin.l", "display_name": "Lucas Martin"},
                    {"identifier": "dupont.e", "display_name": "Emma Dupont"},
                ],
            }
        ]
    }
    return Response(
        content=json.dumps(example, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="open-quiz-classes-example.json"'
            )
        },
    )


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
        raise HTTPException(
            status_code=422,
            detail=api_error(
                ErrorCode.CLASS_IMPORT_DUPLICATES, "Le fichier contient des doublons"
            ),
        )
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
            status_code=422,
            detail=api_error(
                ErrorCode.CLASS_IMPORT_GRADE_LEVEL_INVALID,
                f"Niveau invalide : {', '.join(invalid_levels)}",
            ),
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
        raise HTTPException(
            status_code=409,
            detail=api_error(ErrorCode.CLASS_NAME_TAKEN, "Une classe existe déjà"),
        )
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
            status_code=409,
            detail=api_error(
                ErrorCode.STUDENT_IDENTIFIER_TAKEN,
                "Un identifiant élève est déjà utilisé",
            ),
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
            status_code=409,
            detail=api_error(
                ErrorCode.CLASS_IMPORT_CONFLICT, "Conflit avec les données existantes"
            ),
        ) from None
    return ClassBatchImportResponse(
        class_count=len(payload.classes), student_count=len(identifiers)
    )
