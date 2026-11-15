"""Staff two-factor authentication: challenges, codes and trusted browsers."""

from datetime import UTC, datetime
from hmac import compare_digest
from time import time

import jwt
from cryptography.fernet import InvalidToken
from fastapi import Request, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.audit import audit_event
from app.core.auth_guards import enforce_global_auth_limit, two_factor_rate_subject
from app.core.config import app_settings
from app.core.database import affected_rows
from app.core.errors import ApiError, ErrorCode
from app.core.security import (
    create_two_factor_token,
    create_two_factor_trust_token,
    decode_two_factor_token,
    decode_two_factor_trust_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    end_of_trusted_day,
    generate_totp_secret,
    provisioning_uri,
    two_factor_trust_version,
    verify_totp_code,
)
from app.models import (
    AuthenticationChallenge,
    TwoFactorCredential,
    User,
)
from app.schemas.accounts import LoginResponse

# Remembers, until the end of the day, that this browser completed a
# two-factor login. Only the login endpoint ever needs to read it.
TWO_FACTOR_TRUST_COOKIE = "open_quiz_two_factor_trust"


TWO_FACTOR_TRUST_COOKIE_PATH = "/api/auth/login"


def current_two_factor_trust_version(
    user: User,
    two_factor: TwoFactorCredential,
    request: Request,
) -> str:
    return two_factor_trust_version(
        user.password_hash,
        two_factor.encrypted_secret,
        app_settings(request).jwt_secret,
        user.access_token_generation,
    )


def set_two_factor_trust_cookie(
    response: Response,
    request: Request,
    user: User,
    two_factor: TwoFactorCredential,
    timezone_name: str | None,
) -> None:
    """Let this browser skip the code for the rest of the user's day."""
    settings = app_settings(request)
    if not settings.two_factor_browser_trust:
        return
    now = datetime.now(UTC)
    expires_at = end_of_trusted_day(now, timezone_name)
    response.set_cookie(
        key=TWO_FACTOR_TRUST_COOKIE,
        value=create_two_factor_trust_token(
            user.id,
            settings.jwt_secret,
            current_two_factor_trust_version(user, two_factor, request),
            expires_at,
        ),
        max_age=max(1, int((expires_at - now).total_seconds())),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=TWO_FACTOR_TRUST_COOKIE_PATH,
    )


def clear_two_factor_trust_cookie(response: Response, request: Request) -> None:
    """Make this browser ask for a code again at its next sign-in."""
    response.delete_cookie(
        TWO_FACTOR_TRUST_COOKIE,
        path=TWO_FACTOR_TRUST_COOKIE_PATH,
        secure=app_settings(request).cookie_secure,
        samesite="strict",
    )


def browser_is_trusted(
    request: Request,
    user: User,
    two_factor: TwoFactorCredential,
) -> bool:
    """Whether this browser completed two-factor login for this user today.

    The cookie alone opens nothing: the caller has just checked the password.
    """
    settings = app_settings(request)
    token = request.cookies.get(TWO_FACTOR_TRUST_COOKIE)
    if not settings.two_factor_browser_trust or not token or not two_factor.confirmed:
        return False
    try:
        user_id, version = decode_two_factor_trust_token(token, settings.jwt_secret)
    except jwt.PyJWTError, ValueError, KeyError:
        return False
    return user_id == user.id and compare_digest(
        version, current_two_factor_trust_version(user, two_factor, request)
    )


def issue_two_factor_challenge(
    user_id: int,
    purpose: str,
    request: Request,
    session: Session,
) -> str:
    now = int(time())
    session.execute(
        update(AuthenticationChallenge)
        .where(
            AuthenticationChallenge.user_id == user_id,
            AuthenticationChallenge.used_at.is_(None),
        )
        .values(used_at=now)
    )
    session.execute(
        delete(AuthenticationChallenge).where(AuthenticationChallenge.expires_at <= now)
    )
    token, token_id_hash, expires_at = create_two_factor_token(
        user_id,
        app_settings(request).jwt_secret,
        purpose,
    )
    session.add(
        AuthenticationChallenge(
            token_id_hash=token_id_hash,
            user_id=user_id,
            purpose=purpose,
            expires_at=expires_at,
        )
    )
    return token


def begin_two_factor_setup(
    user: User,
    two_factor: TwoFactorCredential | None,
    request: Request,
    session: Session,
) -> LoginResponse:
    """Store a fresh authenticator secret and challenge its enrollment."""
    settings = app_settings(request)
    secret = generate_totp_secret()
    encrypted_secret = encrypt_totp_secret(
        secret,
        settings.totp_encryption_key,
    )
    if two_factor is None:
        # Two first logins at once (a double click, two devices) both get
        # here: the first one stores its secret, the other enrolls that same
        # secret instead of failing on the duplicate.
        session.execute(
            insert(TwoFactorCredential)
            .values(
                user_id=user.id,
                encrypted_secret=encrypted_secret,
                confirmed=False,
            )
            .on_conflict_do_nothing(index_elements=[TwoFactorCredential.user_id])
        )
        stored_secret = session.scalars(
            select(TwoFactorCredential.encrypted_secret).where(
                TwoFactorCredential.user_id == user.id
            )
        ).one()
        if stored_secret != encrypted_secret:
            secret = decrypt_totp_secret(stored_secret, settings.totp_encryption_key)
    else:
        two_factor.encrypted_secret = encrypted_secret
        two_factor.last_counter = None
    challenge_token = issue_two_factor_challenge(
        user.id,
        "two_factor_setup",
        request,
        session,
    )
    session.commit()
    audit_event("auth.two_factor_setup_started", user_id=user.id)
    return LoginResponse(
        status="setup_required",
        challenge_token=challenge_token,
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.username),
    )


def challenged_user(
    challenge_token: str, request: Request, session: Session, now: int
) -> tuple[User, TwoFactorCredential, str]:
    """The account a live two-factor challenge belongs to, and the challenge id."""
    settings = app_settings(request)
    try:
        decoded = decode_two_factor_token(
            challenge_token,
            settings.jwt_secret,
        )
    except jwt.PyJWTError, ValueError, KeyError:
        decoded = None

    challenge = (
        session.get(AuthenticationChallenge, decoded[2])
        if decoded is not None
        else None
    )
    # Holding a live challenge means the password step already succeeded, so
    # this caller earns the same budget floor as a known account.
    enforce_global_auth_limit(
        request,
        known_identity=(
            challenge is not None
            and challenge.used_at is None
            and challenge.expires_at > now
        ),
    )
    if decoded is None:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_2FA_CHALLENGE_INVALID,
            "Vérification en deux étapes expirée ou invalide",
        )
    user_id, purpose, token_id_hash = decoded

    user = session.get(User, user_id)
    two_factor = session.get(TwoFactorCredential, user_id)
    expected_purpose = (
        "two_factor_verification"
        if two_factor is not None and two_factor.confirmed
        else "two_factor_setup"
    )
    if (
        user is None
        or not user.is_active
        or two_factor is None
        or purpose != expected_purpose
        or challenge is None
        or challenge.user_id != user_id
        or challenge.purpose != purpose
        or challenge.used_at is not None
        or challenge.expires_at <= now
    ):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_2FA_CHALLENGE_INVALID,
            "Vérification en deux étapes expirée ou invalide",
        )
    return user, two_factor, token_id_hash


def reserve_two_factor_attempt(request: Request, user: User) -> str:
    """Count one code attempt in both windows, and return its rate subject."""
    limiter = request.app.state.login_rate_limiter
    rate_subject = two_factor_rate_subject(user.id)
    retry_after = limiter.reserve(rate_subject)
    if retry_after:
        audit_event("auth.two_factor_rate_limited", user_id=user.id)
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.AUTH_2FA_RATE_LIMITED,
            "Trop de codes de vérification essayés",
            headers={"Retry-After": str(retry_after)},
        )
    # The short window alone still lets someone who holds the password try
    # about a thousand codes a day; this caps the guesses per day. Success does
    # not reset it, so a legitimate login cannot refill an attacker's budget.
    daily_retry_after = request.app.state.two_factor_daily_rate_limiter.reserve(
        rate_subject
    )
    if daily_retry_after:
        audit_event("auth.two_factor_daily_limit_reached", user_id=user.id)
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.AUTH_2FA_RATE_LIMITED,
            "Trop de codes de vérification essayés",
            headers={"Retry-After": str(daily_retry_after)},
        )
    return rate_subject


def matched_totp_counter(
    two_factor: TwoFactorCredential, user: User, code: str, request: Request
) -> int:
    """The time step the submitted code matches, never one already used."""
    settings = app_settings(request)
    try:
        secret = decrypt_totp_secret(
            two_factor.encrypted_secret,
            settings.totp_encryption_key,
        )
    except InvalidToken:
        audit_event("auth.two_factor_secret_invalid", user_id=user.id)
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.AUTH_2FA_UNAVAILABLE,
            "Double authentification indisponible",
        ) from None

    matched_counter = verify_totp_code(
        secret,
        code,
        two_factor.last_counter,
    )
    if matched_counter is None:
        audit_event("auth.two_factor_failed", user_id=user.id)
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_2FA_CODE_INVALID,
            "Code de vérification invalide",
        )
    return matched_counter


def consume_code_and_challenge(
    user: User, matched_counter: int, token_id_hash: str, now: int, session: Session
) -> None:
    """Record the code and the challenge as used, so neither works twice."""
    counter_result = session.execute(
        update(TwoFactorCredential)
        .where(
            TwoFactorCredential.user_id == user.id,
            or_(
                TwoFactorCredential.last_counter.is_(None),
                TwoFactorCredential.last_counter < matched_counter,
            ),
        )
        .values(confirmed=True, last_counter=matched_counter)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(counter_result) != 1:
        session.rollback()
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_2FA_CODE_USED,
            "Code de vérification déjà utilisé",
        )
    challenge_result = session.execute(
        update(AuthenticationChallenge)
        .where(
            AuthenticationChallenge.token_id_hash == token_id_hash,
            AuthenticationChallenge.used_at.is_(None),
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    if affected_rows(challenge_result) != 1:
        session.rollback()
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_2FA_CHALLENGE_INVALID,
            "Vérification en deux étapes expirée ou invalide",
        )
