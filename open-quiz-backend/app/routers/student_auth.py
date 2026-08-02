from hmac import compare_digest

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.audit import audit_event
from app.dependencies import DbSession
from app.models import StudentAccount
from app.routers.auth import validate_origin
from app.routers.students import account_response
from app.schemas import (
    StudentAccountResponse,
    StudentLoginRequest,
    StudentLoginResponse,
)
from app.security import (
    DUMMY_PASSWORD_HASH,
    access_token_version,
    create_student_access_token,
    decode_student_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/student-auth", tags=["student authentication"])
student_bearer = HTTPBearer(auto_error=False)


def student_from_token(
    token: str, request: Request, session: DbSession
) -> StudentAccount | None:
    try:
        student_id, version = decode_student_access_token(
            token, request.app.state.settings.jwt_secret
        )
    except jwt.PyJWTError, ValueError, KeyError:
        return None
    account = session.get(StudentAccount, student_id)
    if (
        account is None
        or not account.is_active
        or not compare_digest(
            version,
            access_token_version(
                account.password_hash, request.app.state.settings.jwt_secret
            ),
        )
    ):
        return None
    return account


def current_student(
    request: Request,
    session: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(student_bearer),
) -> StudentAccount:
    account = (
        student_from_token(credentials.credentials, request, session)
        if credentials is not None
        else None
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session élève invalide ou expirée",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return account


@router.post("/login", response_model=StudentLoginResponse)
def login_student(
    payload: StudentLoginRequest,
    request: Request,
    session: DbSession,
) -> StudentLoginResponse:
    validate_origin(request)
    subject = f"student-password:identity:{payload.identifier}"
    limiter = request.app.state.login_rate_limiter
    retry_after = limiter.reserve(session, subject)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives de connexion",
            headers={"Retry-After": str(retry_after)},
        )
    account = session.scalar(
        select(StudentAccount).where(StudentAccount.identifier == payload.identifier)
    )
    encoded = account.password_hash if account else DUMMY_PASSWORD_HASH
    if (
        account is None
        or not account.is_active
        or not verify_password(payload.password, encoded)
    ):
        audit_event("student_auth.login_failed")
        raise HTTPException(
            status_code=401, detail="Identifiant ou mot de passe incorrect"
        )
    limiter.clear_subject(session, subject)
    token = create_student_access_token(
        account.id,
        request.app.state.settings.jwt_secret,
        access_token_version(
            account.password_hash, request.app.state.settings.jwt_secret
        ),
    )
    return StudentLoginResponse(
        access_token=token, student=account_response(account, session)
    )


@router.get("/me", response_model=StudentAccountResponse)
def student_me(
    request: Request,
    session: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(student_bearer),
) -> StudentAccountResponse:
    account = (
        student_from_token(credentials.credentials, request, session)
        if credentials is not None
        else None
    )
    if account is None:
        raise HTTPException(status_code=401, detail="Session élève invalide ou expirée")
    return account_response(account, session)
