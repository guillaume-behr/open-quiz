from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models import TwoFactorCredential, User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def get_current_user(
    request: Request,
    credentials: BearerCredentials,
    session: DbSession,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        user_id = decode_access_token(
            credentials.credentials, request.app.state.settings.jwt_secret
        )
    except jwt.PyJWTError, ValueError, KeyError:
        raise unauthorized from None

    user = session.get(User, user_id)
    two_factor = session.get(TwoFactorCredential, user_id)
    if (
        user is None
        or not user.is_active
        or two_factor is None
        or not two_factor.confirmed
    ):
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
