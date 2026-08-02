from collections.abc import Iterator
from hmac import compare_digest
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models import TwoFactorCredential, User
from app.security import access_token_version, decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def client_ip(request: Request) -> str:
    """Best-effort client address, honoring the immediate trusted proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def authenticated_user_from_token(
    request: Request,
    token: str,
    session: Session,
) -> User | None:
    try:
        user_id, token_version = decode_access_token(
            token, request.app.state.settings.jwt_secret
        )
    except (jwt.PyJWTError, ValueError, KeyError):
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
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Jeton d’authentification invalide ou expiré",
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès administrateur requis",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def require_professor(user: CurrentUser) -> User:
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès enseignant requis",
        )
    return user


ProfessorUser = Annotated[User, Depends(require_professor)]
