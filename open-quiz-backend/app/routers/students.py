import re
import unicodedata
from secrets import choice
from string import digits
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.audit import audit_event
from app.dependencies import DbSession, ProfessorUser
from app.models import (
    MakeupSessionSelection,
    Quiz,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.schemas import (
    StudentAccountCreate,
    StudentAccountCreatedResponse,
    StudentAccountResponse,
    StudentAccountUpdate,
    StudentCredentialResponse,
)
from app.security import (
    decrypt_student_password,
    encrypt_student_password,
    hash_password,
)

router = APIRouter(prefix="/api/students", tags=["student accounts"])

READABLE_CONSONANTS = "BCDFGHJKMNPRSTVWXYZ"
READABLE_VOWELS = "AEU"


def generated_student_password() -> str:
    # Pronounceable letters plus digits: 19^4 * 3^4 * 10^2 (~30 bits) while
    # staying easy for young students to copy.
    letters = "".join(
        choice(READABLE_CONSONANTS if index % 2 == 0 else READABLE_VOWELS)
        for index in range(8)
    )
    return f"{letters}{choice(digits)}{choice(digits)}"


def identifier_part(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", ".", ascii_value.lower()).strip(".")


def generated_student_identifier(
    first_name: str, last_name: str, session: DbSession
) -> str:
    parts = [identifier_part(first_name), identifier_part(last_name)]
    base = ".".join(part for part in parts if part) or "eleve"
    base = base[:80].rstrip(".")
    identifier = base
    suffix = 2
    while (
        session.scalar(
            select(StudentAccount.id).where(StudentAccount.identifier == identifier)
        )
        is not None
    ):
        suffix_text = str(suffix)
        identifier = f"{base[: 79 - len(suffix_text)].rstrip('.')}.{suffix_text}"
        suffix += 1
    return identifier


def account_response(
    account: StudentAccount, session: DbSession
) -> StudentAccountResponse:
    membership = session.execute(
        select(Student.class_id, StudentClass.name)
        .join(StudentClass, StudentClass.id == Student.class_id)
        .where(Student.account_id == account.id)
    ).first()
    return account_response_from_membership(
        account,
        (membership[0], membership[1]) if membership else None,
    )


def account_response_from_membership(
    account: StudentAccount,
    membership: tuple[int, str] | None,
) -> StudentAccountResponse:
    return StudentAccountResponse(
        id=account.id,
        identifier=account.identifier,
        display_name=account.display_name,
        is_active=account.is_active,
        class_id=membership[0] if membership else None,
        class_name=membership[1] if membership else None,
        created_at=account.created_at,
    )


def owned_account(
    account_id: int, professor: ProfessorUser, session: DbSession
) -> StudentAccount:
    account = session.scalar(
        select(StudentAccount).where(
            StudentAccount.id == account_id,
            StudentAccount.owner_id == professor.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Compte élève introuvable")
    return account


def credential_response(
    account: StudentAccount, request: Request
) -> StudentCredentialResponse:
    password = (
        decrypt_student_password(
            account.encrypted_password,
            request.app.state.settings.student_credential_encryption_key,
        )
        if account.encrypted_password
        else None
    )
    return StudentCredentialResponse(
        identifier=account.identifier,
        display_name=account.display_name,
        password=password,
    )


@router.get("", response_model=list[StudentAccountResponse])
def list_student_accounts(
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str = Query("", max_length=120),
    class_id: Annotated[int | None, Query(ge=1)] = None,
    unassigned: bool = False,
    is_active: bool | None = None,
) -> list[StudentAccountResponse]:
    if class_id is not None and unassigned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Les filtres de classe sont incompatibles",
        )
    filters = [StudentAccount.owner_id == professor.id]
    if search:
        term = f"%{search}%"
        filters.append(
            StudentAccount.display_name.ilike(term)
            | StudentAccount.identifier.ilike(term)
        )
    if class_id is not None:
        student_class = session.scalar(
            select(StudentClass.id).where(
                StudentClass.id == class_id,
                StudentClass.owner_id == professor.id,
            )
        )
        if student_class is None:
            raise HTTPException(status_code=404, detail="Classe introuvable")
        filters.append(
            StudentAccount.id.in_(
                select(Student.account_id).where(
                    Student.class_id == class_id,
                    Student.account_id.is_not(None),
                )
            )
        )
    elif unassigned:
        filters.append(
            StudentAccount.id.not_in(
                select(Student.account_id).where(Student.account_id.is_not(None))
            )
        )
    if is_active is not None:
        filters.append(StudentAccount.is_active.is_(is_active))
    total = (
        session.scalar(select(func.count()).select_from(StudentAccount).where(*filters))
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    rows = session.execute(
        select(StudentAccount, Student.class_id, StudentClass.name)
        .outerjoin(Student, Student.account_id == StudentAccount.id)
        .outerjoin(StudentClass, StudentClass.id == Student.class_id)
        .where(*filters)
        .order_by(StudentAccount.display_name, StudentAccount.identifier)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [
        account_response_from_membership(
            account,
            (class_id, class_name)
            if class_id is not None and class_name is not None
            else None,
        )
        for account, class_id, class_name in rows
    ]


@router.get("/credentials", response_model=list[StudentCredentialResponse])
def list_student_credentials(
    professor: ProfessorUser,
    session: DbSession,
    request: Request,
    response: Response,
    class_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[StudentCredentialResponse]:
    query = select(StudentAccount).where(StudentAccount.owner_id == professor.id)
    if class_id is not None:
        owned_class = session.scalar(
            select(StudentClass.id).where(
                StudentClass.id == class_id,
                StudentClass.owner_id == professor.id,
            )
        )
        if owned_class is None:
            raise HTTPException(status_code=404, detail="Classe introuvable")
        query = query.join(Student, Student.account_id == StudentAccount.id).where(
            Student.class_id == class_id
        )
    accounts = session.scalars(
        query.order_by(StudentAccount.display_name, StudentAccount.identifier)
    ).all()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    audit_event(
        "students.credentials_viewed",
        professor_id=professor.id,
        account_count=len(accounts),
        class_id=class_id,
    )
    return [credential_response(account, request) for account in accounts]


@router.get("/credentials/export")
def export_student_credentials(
    professor: ProfessorUser,
    session: DbSession,
    request: Request,
) -> JSONResponse:
    accounts = session.scalars(
        select(StudentAccount)
        .where(StudentAccount.owner_id == professor.id)
        .order_by(StudentAccount.display_name, StudentAccount.identifier)
    ).all()
    content = {
        "students": [
            credential_response(account, request).model_dump() for account in accounts
        ]
    }
    audit_event(
        "students.credentials_exported",
        professor_id=professor.id,
        account_count=len(accounts),
    )
    return JSONResponse(
        content=content,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Disposition": 'attachment; filename="student-credentials.json"',
        },
    )


@router.post("", response_model=StudentAccountCreatedResponse, status_code=201)
def create_student_account(
    payload: StudentAccountCreate,
    professor: ProfessorUser,
    session: DbSession,
    request: Request,
) -> StudentAccountCreatedResponse:
    identifier = generated_student_identifier(
        payload.first_name, payload.last_name, session
    )
    password = generated_student_password()
    account = StudentAccount(
        owner_id=professor.id,
        identifier=identifier,
        display_name=f"{payload.first_name} {payload.last_name}",
        password_hash=hash_password(password),
        encrypted_password=encrypt_student_password(
            password,
            request.app.state.settings.student_credential_encryption_key,
        ),
    )
    session.add(account)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet identifiant élève est déjà utilisé",
        ) from None
    session.refresh(account)
    audit_event(
        "students.account_created",
        professor_id=professor.id,
        account_id=account.id,
    )
    response = account_response(account, session)
    return StudentAccountCreatedResponse(
        **response.model_dump(), generated_password=password
    )


@router.post("/{account_id}/update", response_model=StudentAccountResponse)
def update_student_account(
    account_id: int,
    payload: StudentAccountUpdate,
    professor: ProfessorUser,
    session: DbSession,
    request: Request,
) -> StudentAccountResponse:
    account = owned_account(account_id, professor, session)
    account.identifier = payload.identifier
    account.display_name = payload.display_name
    account.is_active = payload.is_active
    if payload.password is not None:
        account.password_hash = hash_password(payload.password)
        account.encrypted_password = encrypt_student_password(
            payload.password,
            request.app.state.settings.student_credential_encryption_key,
        )
    membership = session.scalar(select(Student).where(Student.account_id == account.id))
    if membership is not None:
        membership.identifier = account.identifier
        membership.display_name = account.display_name
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Cet identifiant élève est déjà utilisé"
        ) from None
    audit_event(
        "students.account_updated",
        professor_id=professor.id,
        account_id=account.id,
    )
    return account_response(account, session)


@router.delete("/{account_id}", status_code=204)
def delete_student_account(
    account_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> None:
    account = owned_account(account_id, professor, session)
    membership = session.scalar(select(Student).where(Student.account_id == account.id))
    if membership is not None:
        active = session.scalar(
            select(QuizSession.id)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.class_id == membership.class_id,
                Quiz.mode == "exam",
                QuizSession.status.in_(["waiting", "in_progress", "paused"]),
            )
        )
        if active is not None:
            raise HTTPException(
                status_code=409, detail="Ce compte participe à une session active"
            )
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.student_id == membership.id)
            .values(student_id=None)
        )
        session.execute(
            delete(MakeupSessionSelection).where(
                MakeupSessionSelection.student_id == membership.id
            )
        )
        session.execute(delete(Student).where(Student.id == membership.id))
    session.execute(delete(StudentAccount).where(StudentAccount.id == account.id))
    session.commit()
    audit_event(
        "students.account_deleted",
        professor_id=professor.id,
        account_id=account_id,
    )
