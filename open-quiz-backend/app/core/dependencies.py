from collections.abc import Iterator
from hmac import compare_digest
from typing import Annotated

import jwt
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.core.errors import ApiError, ErrorCode
from app.core.security import (
    access_token_version,
    decode_access_token,
    decode_student_access_token,
)
from app.models import StudentAccount, TwoFactorCredential, User

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def authenticated_user_from_token(
    request: HTTPConnection,
    token: str,
    session: Session,
) -> User | None:
    try:
        user_id, token_version = decode_access_token(
            token, request.app.state.settings.jwt_secret
        )
    except jwt.PyJWTError, ValueError, KeyError:
        return None

    user = session.get(User, user_id)
    two_factor = session.get(TwoFactorCredential, user_id)
    if (
        user is None
        or not user.is_active
        or two_factor is None
        or not two_factor.confirmed
        or not compare_digest(
            token_version,
            access_token_version(
                user.password_hash,
                request.app.state.settings.jwt_secret,
                user.access_token_generation,
            ),
        )
    ):
        return None
    return user


def get_current_user(
    request: Request,
    credentials: BearerCredentials,
    session: DbSession,
) -> User:
    unauthorized = ApiError(
        status.HTTP_401_UNAUTHORIZED,
        ErrorCode.AUTH_TOKEN_INVALID,
        "Jeton d’authentification invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    user = authenticated_user_from_token(request, credentials.credentials, session)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_ADMIN_ACCOUNT_REQUIRED,
            "Accès administrateur requis",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def require_professor(user: CurrentUser) -> User:
    if user.is_admin:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_PROFESSOR_ACCOUNT_REQUIRED,
            "Accès enseignant requis",
        )
    return user


ProfessorUser = Annotated[User, Depends(require_professor)]


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
                account.password_hash,
                request.app.state.settings.jwt_secret,
                account.access_token_generation,
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
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.STUDENT_SESSION_INVALID,
            "Session élève invalide ou expirée",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return account
