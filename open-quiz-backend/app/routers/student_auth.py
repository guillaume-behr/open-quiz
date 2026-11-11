from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update

from app.audit import audit_event
from app.auth_guards import (
    enforce_global_auth_limit,
    student_password_rate_subject,
    validate_origin,
)
from app.dependencies import (
    DbSession,
    current_student,
)
from app.enums import QuizMode
from app.errors import ApiError, ErrorCode
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
    DUMMY_PASSWORD_HASH,
    access_token_version,
    create_student_access_token,
    verify_password_and_update,
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
    account = session.scalar(
        select(StudentAccount).where(StudentAccount.identifier == payload.identifier)
    )
    # Resolving the account first keeps real students able to sign in while an
    # anonymous flood holds the instance-wide budget open.
    enforce_global_auth_limit(
        request,
        known_identity=account is not None and account.is_active,
    )
    subject = student_password_rate_subject(payload.identifier)
    limiter = request.app.state.login_rate_limiter
    retry_after = limiter.reserve(subject)
    if retry_after:
        raise ApiError(
            429,
            ErrorCode.AUTH_RATE_LIMITED,
            "Trop de tentatives de connexion",
            headers={"Retry-After": str(retry_after)},
        )
    encoded = account.password_hash if account else DUMMY_PASSWORD_HASH
    # Hashing can wait for a free slot: end the transaction first, so the
    # request does not hold a pooled connection meanwhile.
    session.commit()
    # Always run the password verification, even for unknown identifiers, so
    # the response time does not reveal whether the account exists.
    password_valid, upgraded_hash = verify_password_and_update(
        payload.password, encoded
    )
    if account is None or not account.is_active or not password_valid:
        audit_event("student_auth.login_failed")
        raise ApiError(
            401, ErrorCode.AUTH_INVALID_CREDENTIALS, "Identifiants invalides"
        )
    # Give back only this attempt: clearing the whole bucket would hand
    # whoever is guessing this identifier a fresh allowance at every sign-in.
    limiter.release(subject)
    if upgraded_hash is not None:
        # The token is bound to the hash, so it is issued from the new one.
        account.password_hash = upgraded_hash
        session.commit()
        audit_event("student_auth.password_hash_upgraded", account_id=account.id)
    token = create_student_access_token(
        account.id,
        request.app.state.settings.jwt_secret,
        access_token_version(
            account.password_hash,
            request.app.state.settings.jwt_secret,
            account.access_token_generation,
        ),
        request.app.state.settings.student_access_token_hours,
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
