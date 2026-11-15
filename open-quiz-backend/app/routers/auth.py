"""Staff sign-in routes: password, two-factor code, refresh and logout."""

from time import time

from fastapi import APIRouter, Request, Response, status

from app.core.audit import audit_event
from app.core.auth_guards import validate_origin
from app.core.dependencies import DbSession
from app.core.security import hash_refresh_token
from app.models import RefreshSession, TwoFactorCredential
from app.schemas.accounts import (
    LoginRequest,
    LoginResponse,
    LoginSessionResponse,
    LogoutRequest,
    TokenResponse,
    TwoFactorVerifyRequest,
)
from app.services.credentials import revoke_refresh_sessions
from app.services.password_login import password_user, require_audience
from app.services.refresh_sessions import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    issue_session,
    presented_refresh_session,
    refreshable_user,
    retire_refresh_session,
    validate_refresh_proof,
)
from app.services.two_factor import (
    begin_two_factor_setup,
    browser_is_trusted,
    challenged_user,
    clear_two_factor_trust_cookie,
    consume_code_and_challenge,
    issue_two_factor_challenge,
    matched_totp_counter,
    reserve_two_factor_attempt,
    set_two_factor_trust_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse | LoginSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> LoginResponse | LoginSessionResponse:
    """Verify a password, then begin 2FA or, on a trusted browser, sign in."""
    validate_origin(request)
    user = password_user(payload, request, session)
    require_audience(user, payload.audience)
    two_factor = session.get(TwoFactorCredential, user.id)
    if two_factor is None or not two_factor.confirmed:
        return begin_two_factor_setup(user, two_factor, request, session)

    if browser_is_trusted(request, user, two_factor):
        audit_event("auth.two_factor_trusted_browser", user_id=user.id)
        tokens = issue_session(user, request, response, session)
        return LoginSessionResponse(**tokens.model_dump())

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
    now = int(time())
    user, two_factor, token_id_hash = challenged_user(
        payload.challenge_token, request, session, now
    )
    rate_subject = reserve_two_factor_attempt(request, user)
    matched_counter = matched_totp_counter(two_factor, user, payload.code, request)
    consume_code_and_challenge(user, matched_counter, token_id_hash, now, session)
    request.app.state.login_rate_limiter.clear_subject(rate_subject)
    audit_event("auth.two_factor_succeeded", user_id=user.id)
    tokens = issue_session(user, request, response, session)
    set_two_factor_trust_cookie(response, request, user, two_factor, payload.timezone)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    session: DbSession,
) -> TokenResponse:
    """Rotate a valid refresh session and return a new access token."""
    validate_origin(request)
    now = int(time())
    stored_session = presented_refresh_session(request, session, now)

    family = retire_refresh_session(stored_session, session, now)

    user = refreshable_user(stored_session, session, now)

    audit_event("auth.refresh_succeeded", user_id=user.id)
    return issue_session(
        user,
        request,
        response,
        session,
        family_id=family.family_id,
        expires_at=stored_session.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: DbSession,
    payload: LogoutRequest | None = None,
) -> None:
    """Revoke the current refresh session and clear its cookie.

    The two-factor trust cookie survives a plain logout; ``forget_browser``
    clears it too.

    Revoking the session needs the refresh proof, which only the tab that
    signed in holds. Without it (another tab, after the first one closed),
    the session is left to expire, but this browser still forgets it: the
    cookies are cleared all the same. validate_origin keeps other sites from
    clearing them.
    """
    validate_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token and not validate_refresh_proof(request, raw_token):
        audit_event("auth.logout_proof_rejected")
    elif raw_token:
        revoke_refresh_sessions(
            session,
            int(time()),
            RefreshSession.token_hash == hash_refresh_token(raw_token),
        )
        session.commit()
    clear_refresh_cookie(response, request)
    if payload is not None and payload.forget_browser:
        clear_two_factor_trust_cookie(response, request)
    audit_event("auth.logout")
