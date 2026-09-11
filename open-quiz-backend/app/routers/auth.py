from hmac import compare_digest
from time import time
from urllib.parse import urlparse

import jwt
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.audit import audit_event
from app.dependencies import DbSession
from app.models import (
    AuthenticationChallenge,
    RefreshSession,
    RefreshSessionFamily,
    TwoFactorCredential,
    User,
)
from app.schemas import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    TwoFactorVerifyRequest,
)
from app.security import (
    DUMMY_PASSWORD_HASH,
    access_token_version,
    create_access_token,
    create_refresh_token,
    create_two_factor_token,
    decode_two_factor_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    hash_refresh_token,
    provisioning_uri,
    refresh_request_proof,
    verify_password,
    verify_totp_code,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
REFRESH_COOKIE = "open_quiz_refresh"
REFRESH_PROOF_HEADER = "X-Refresh-Proof"


def auth_error(code: str) -> dict[str, str]:
    """Return a stable, language-neutral authentication error payload."""
    return {"code": code}


def validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    settings = request.app.state.settings
    expected = settings.frontend_origin.rstrip("/")
    is_allowed = origin is not None and origin.rstrip("/") == expected
    if origin is not None and settings.environment == "development":
        parsed_origin = urlparse(origin)
        is_local_development = (
            parsed_origin.scheme in {"http", "https"}
            and parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed_origin.path in {"", "/"}
            and not parsed_origin.username
            and not parsed_origin.password
            and not parsed_origin.query
            and not parsed_origin.fragment
        )
        is_allowed = is_allowed or is_local_development

    if not is_allowed:
        audit_event(
            "auth.origin_rejected",
            origin=origin or "<missing>",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_error("AUTH_ORIGIN_REJECTED"),
        )


def set_refresh_cookie(
    response: Response,
    token: str,
    request: Request,
    expires_at: int,
) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=max(0, expires_at - int(time())),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response, request: Request) -> None:
    settings = request.app.state.settings
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/auth",
        secure=settings.cookie_secure,
        samesite="strict",
    )


def password_rate_subject(username: str) -> str:
    return f"password:identity:{username}"


def enforce_global_auth_limit(
    request: Request,
    session: DbSession,
    *,
    known_identity: bool = False,
) -> None:
    """Bound total authentication hashing work instance-wide regardless of source.

    Unlike per-account buckets, this single budget cannot be evaded by
    rotating usernames, so it caps the CPU cost an attacker can force.

    Exhausting the budget must not take the instance offline. Without a floor,
    anyone able to send a few thousand requests a minute denies every teacher
    and student their login for the rest of the window, which during a lesson
    costs more than the hashing the budget exists to bound. So a request that
    names an account the instance already knows still proceeds: that account's
    own bucket caps how much hashing it can be made to cost, leaving total work
    bounded by the number of real accounts rather than by the request rate.

    The floor is a deliberate trade. While the budget is exhausted, the
    difference between 429 and 401 tells a caller that an identifier exists,
    which the constant-time password path otherwise hides. Opening that oracle
    costs a sustained flood that this function audits on every request, and the
    identifiers it discloses are already derived from names the attacker would
    have to know to ask the question.
    """
    retry_after = request.app.state.auth_global_rate_limiter.reserve(
        session, "instance"
    )
    if not retry_after:
        return
    if known_identity:
        audit_event("auth.global_budget_floor_used")
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=auth_error("AUTH_RATE_LIMITED"),
        headers={"Retry-After": str(retry_after)},
    )


def two_factor_rate_subject(user_id: int) -> str:
    return f"two-factor:user:{user_id}"


def validate_refresh_proof(request: Request, raw_token: str | None) -> bool:
    supplied_proof = request.headers.get(REFRESH_PROOF_HEADER)
    if raw_token is None or supplied_proof is None:
        return False
    expected_proof = refresh_request_proof(
        raw_token,
        request.app.state.settings.jwt_secret,
    )
    return compare_digest(supplied_proof, expected_proof)


def issue_session(
    user: User,
    request: Request,
    response: Response,
    session: Session,
    *,
    family_id: str | None = None,
    parent_session_id: int | None = None,
    expires_at: int | None = None,
) -> TokenResponse:
    settings = request.app.state.settings
    now = int(time())
    session_expires_at = (
        expires_at
        if expires_at is not None
        else now + settings.refresh_token_days * 86400
    )
    expired_session_ids = select(RefreshSession.id).where(
        RefreshSession.expires_at <= now
    )
    session.execute(
        delete(RefreshSessionFamily).where(
            RefreshSessionFamily.session_id.in_(expired_session_ids)
        )
    )
    session.execute(delete(RefreshSession).where(RefreshSession.expires_at <= now))
    older_session_ids = list(
        session.scalars(
            select(RefreshSession.id)
            .where(
                RefreshSession.user_id == user.id,
                RefreshSession.revoked_at.is_(None),
            )
            .order_by(RefreshSession.id.desc())
            .offset(9)
        )
    )
    if older_session_ids:
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.id.in_(older_session_ids))
            .values(revoked_at=now)
        )
    refresh_token = create_refresh_token()
    refresh_session = RefreshSession(
        token_hash=hash_refresh_token(refresh_token),
        user_id=user.id,
        expires_at=session_expires_at,
    )
    session.add(refresh_session)
    session.flush()
    session.add(
        RefreshSessionFamily(
            session_id=refresh_session.id,
            family_id=family_id or hash_refresh_token(create_refresh_token()),
            parent_session_id=parent_session_id,
        )
    )
    session.commit()
    set_refresh_cookie(response, refresh_token, request, session_expires_at)
    return TokenResponse(
        access_token=create_access_token(
            user.id,
            settings.jwt_secret,
            settings.access_token_minutes,
            access_token_version(
                user.password_hash,
                settings.jwt_secret,
                user.access_token_generation,
            ),
            session_expires_at=session_expires_at,
        ),
        refresh_proof=refresh_request_proof(refresh_token, settings.jwt_secret),
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
        request.app.state.settings.jwt_secret,
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


def revoke_refresh_family(
    session: Session,
    session_id: int,
    now: int,
) -> bool:
    family = session.get(RefreshSessionFamily, session_id)
    if family is None:
        return False
    family_session_ids = select(RefreshSessionFamily.session_id).where(
        RefreshSessionFamily.family_id == family.family_id
    )
    session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id.in_(family_session_ids),
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.commit()
    return True


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: DbSession,
) -> LoginResponse:
    """Verify a password and begin 2FA setup or verification."""
    validate_origin(request)
    user = session.scalar(select(User).where(User.username == payload.username))
    # Resolving the account before the budget check is what lets a real
    # teacher still sign in while an anonymous flood holds the budget open.
    enforce_global_auth_limit(
        request,
        session,
        known_identity=user is not None and user.is_active,
    )
    limiter = request.app.state.login_rate_limiter
    rate_subject = password_rate_subject(payload.username)
    retry_after = limiter.reserve(session, rate_subject)
    if retry_after:
        audit_event("auth.login_rate_limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error("AUTH_RATE_LIMITED"),
            headers={"Retry-After": str(retry_after)},
        )
    encoded_password = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, encoded_password)
    if user is None or not user.is_active or not password_valid:
        audit_event("auth.login_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_INVALID_CREDENTIALS"),
        )
    limiter.clear_subject(session, rate_subject)
    if payload.audience == "professor" and user.is_admin:
        audit_event(
            "auth.login_wrong_audience",
            user_id=user.id,
            audience=payload.audience,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_error("AUTH_PROFESSOR_ACCOUNT_REQUIRED"),
        )
    if payload.audience == "admin" and not user.is_admin:
        audit_event(
            "auth.login_wrong_audience",
            user_id=user.id,
            audience=payload.audience,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_error("AUTH_ADMIN_ACCOUNT_REQUIRED"),
        )
    settings = request.app.state.settings
    two_factor = session.get(TwoFactorCredential, user.id)
    if two_factor is None or not two_factor.confirmed:
        secret = generate_totp_secret()
        encrypted_secret = encrypt_totp_secret(
            secret,
            settings.totp_encryption_key,
        )
        if two_factor is None:
            two_factor = TwoFactorCredential(
                user_id=user.id,
                encrypted_secret=encrypted_secret,
            )
            session.add(two_factor)
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

    audit_event("auth.two_factor_challenge_started", user_id=user.id)
    challenge_token = issue_two_factor_challenge(
        user.id,
        "two_factor_verification",
        request,
        session,
    )
    session.commit()
    return LoginResponse(
        status="verification_required",
        challenge_token=challenge_token,
    )


@router.post("/2fa/verify", response_model=TokenResponse)
def verify_two_factor(
    payload: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> TokenResponse:
    """Complete 2FA setup or verify a login challenge."""
    validate_origin(request)
    settings = request.app.state.settings
    try:
        decoded = decode_two_factor_token(
            payload.challenge_token,
            settings.jwt_secret,
        )
    except jwt.PyJWTError, ValueError, KeyError:
        decoded = None

    now = int(time())
    challenge = (
        session.get(AuthenticationChallenge, decoded[2])
        if decoded is not None
        else None
    )
    # Holding a live challenge means the password step already succeeded, so
    # this caller earns the same budget floor as a known account.
    enforce_global_auth_limit(
        request,
        session,
        known_identity=(
            challenge is not None
            and challenge.used_at is None
            and challenge.expires_at > now
        ),
    )
    if decoded is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_2FA_CHALLENGE_INVALID"),
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_2FA_CHALLENGE_INVALID"),
        )

    limiter = request.app.state.login_rate_limiter
    rate_subject = two_factor_rate_subject(user.id)
    retry_after = limiter.reserve(session, rate_subject)
    if retry_after:
        audit_event("auth.two_factor_rate_limited", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error("AUTH_2FA_RATE_LIMITED"),
            headers={"Retry-After": str(retry_after)},
        )

    try:
        secret = decrypt_totp_secret(
            two_factor.encrypted_secret,
            settings.totp_encryption_key,
        )
    except InvalidToken:
        audit_event("auth.two_factor_secret_invalid", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=auth_error("AUTH_2FA_UNAVAILABLE"),
        ) from None

    matched_counter = verify_totp_code(
        secret,
        payload.code,
        two_factor.last_counter,
    )
    if matched_counter is None:
        audit_event("auth.two_factor_failed", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_2FA_CODE_INVALID"),
        )

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
    if counter_result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_2FA_CODE_USED"),
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
    if challenge_result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error("AUTH_2FA_CHALLENGE_INVALID"),
        )
    limiter.clear_subject(session, rate_subject)
    audit_event("auth.two_factor_succeeded", user_id=user.id)
    return issue_session(user, request, response, session)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: DbSession,
) -> TokenResponse:
    """Rotate a valid refresh session and return a new access token."""
    validate_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session de connexion invalide",
        )
    if not validate_refresh_proof(request, raw_token):
        audit_event("auth.refresh_proof_rejected")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Preuve de session invalide",
        )
    stored_session = session.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == hash_refresh_token(raw_token)
        )
    )
    now = int(time())
    if stored_session is None or stored_session.expires_at <= now:
        audit_event("auth.refresh_rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session de connexion invalide",
        )
    if stored_session.revoked_at is not None:
        family_revoked = revoke_refresh_family(session, stored_session.id, now)
        audit_event(
            "auth.refresh_reuse_detected",
            user_id=stored_session.user_id,
            family_revoked=family_revoked,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session de connexion invalide",
        )

    family = session.get(RefreshSessionFamily, stored_session.id)
    if family is None:
        family = RefreshSessionFamily(
            session_id=stored_session.id,
            family_id=hash_refresh_token(create_refresh_token()),
        )
        session.add(family)
        session.flush()
    result = session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == stored_session.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if result.rowcount != 1:
        session.rollback()
        family_revoked = revoke_refresh_family(session, stored_session.id, now)
        audit_event(
            "auth.refresh_reuse_detected",
            user_id=stored_session.user_id,
            family_revoked=family_revoked,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session de connexion invalide",
        )

    user = session.get(User, stored_session.user_id)
    two_factor = session.get(TwoFactorCredential, stored_session.user_id)
    if (
        user is None
        or not user.is_active
        or two_factor is None
        or not two_factor.confirmed
    ):
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == stored_session.user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session de connexion invalide",
        )

    audit_event("auth.refresh_succeeded", user_id=user.id)
    return issue_session(
        user,
        request,
        response,
        session,
        family_id=family.family_id,
        parent_session_id=stored_session.id,
        expires_at=stored_session.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: DbSession,
) -> None:
    """Revoke the current refresh session and clear its cookie."""
    validate_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        if not validate_refresh_proof(request, raw_token):
            audit_event("auth.logout_proof_rejected")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Preuve de session invalide",
            )
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash == hash_refresh_token(raw_token),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=int(time()))
        )
        session.commit()
    clear_refresh_cookie(response, request)
    audit_event("auth.logout")
