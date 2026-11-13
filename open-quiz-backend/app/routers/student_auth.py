from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update

from app.audit import audit_event
from app.auth_guards import (
    check_password,
    student_password_rate_subject,
    validate_origin,
)
from app.config import app_settings
from app.dependencies import (
    DbSession,
    current_student,
)
from app.enums import QuizMode
from app.models import (
    Quiz,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
)
from app.schemas import (
    StudentAccountResponse,
    StudentLoginRequest,
    StudentLoginResponse,
)
from app.security import (
    access_token_version,
    create_student_access_token,
)
from app.student_accounts import student_account_response

router = APIRouter(prefix="/api/student-auth", tags=["student authentication"])


@router.post("/login", response_model=StudentLoginResponse)
def login_student(
    payload: StudentLoginRequest,
    request: Request,
    session: DbSession,
) -> StudentLoginResponse:
    validate_origin(request)
    named_account = session.scalar(
        select(StudentAccount).where(StudentAccount.identifier == payload.identifier)
    )
    active_account = (
        named_account if named_account is not None and named_account.is_active else None
    )
    account, upgraded_hash = check_password(
        payload.password,
        student_password_rate_subject(payload.identifier),
        active_account,
        active_account.password_hash if active_account else None,
        request,
        session,
        audit_prefix="student_auth",
    )
    if upgraded_hash is not None:
        # The token is bound to the hash, so it is issued from the new one.
        account.password_hash = upgraded_hash
        session.commit()
        audit_event("student_auth.password_hash_upgraded", account_id=account.id)
    token = create_student_access_token(
        account.id,
        app_settings(request).jwt_secret,
        access_token_version(
            account.password_hash,
            app_settings(request).jwt_secret,
            account.access_token_generation,
        ),
        app_settings(request).student_access_token_hours,
    )
    return StudentLoginResponse(
        access_token=token, student=student_account_response(account, session)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_student(
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> Response:
    """Revoke every access token of this student account.

    Student tokens are stateless, so a shared classroom computer would keep a
    usable token until it expires. Bumping the generation revokes the account's
    tokens on every device, which is the safe side for a shared computer.

    Training participation tokens are revoked too, so whoever uses the
    computer next cannot go on training as this student. Exam participations
    keep theirs: a student who signs out mid-exam signs in again and resumes.
    """
    account.access_token_generation += 1
    training_session_ids = (
        select(QuizSession.id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(Quiz.mode == QuizMode.TRAINING)
    )
    session.execute(
        update(QuizParticipant)
        .where(
            QuizParticipant.student_id.in_(
                select(Student.id).where(Student.account_id == account.id)
            ),
            QuizParticipant.session_id.in_(training_session_ids),
        )
        .values(access_token_hash=None)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    audit_event("student_auth.logout", account_id=account.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=StudentAccountResponse)
def student_me(
    account: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> StudentAccountResponse:
    return student_account_response(account, session)
