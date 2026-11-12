"""Guards shared by sign-in routes: origin checks and attempt limits."""

from urllib.parse import urlparse

from fastapi import Request, status
from sqlalchemy.orm import Session

from app.audit import audit_event
from app.errors import ApiError, ErrorCode
from app.security import DUMMY_PASSWORD_HASH, verify_password_and_update


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
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_ORIGIN_REJECTED,
            "Origine de la requête refusée",
        )


def password_rate_subject(username: str) -> str:
    return f"password:identity:{username}"


def trusted_password_rate_subject(user_id: int) -> str:
    """The attempt bucket of the browsers an account already trusts.

    The bucket of a username is filled by anyone who types that username, so
    ten wrong passwords every window would keep its owner out for as long as
    someone cares to send them. A browser holding the account's two-factor
    trust cookie proves it signed in there today: its attempts are counted
    apart, where a stranger's guesses cannot reach them.
    """
    return f"password:trusted:{user_id}"


def enforce_global_auth_limit(
    request: Request,
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
    retry_after = request.app.state.auth_global_rate_limiter.reserve("instance")
    if not retry_after:
        return
    if known_identity:
        audit_event("auth.global_budget_floor_used")
        return
    raise ApiError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        ErrorCode.AUTH_RATE_LIMITED,
        "Trop de tentatives de connexion",
        headers={"Retry-After": str(retry_after)},
    )


def two_factor_rate_subject(user_id: int) -> str:
    return f"two-factor:user:{user_id}"


def student_password_rate_subject(identifier: str) -> str:
    return f"student-password:identity:{identifier}"


def check_password[Account](
    password: str,
    subject: str,
    account: Account | None,
    encoded_hash: str | None,
    request: Request,
    session: Session,
    *,
    audit_prefix: str,
) -> tuple[Account, str | None]:
    """Check a sign-in password within the attempt limits.

    account is the active account the sign-in names, or None when there is
    none, and encoded_hash its password hash: without one a dummy hash is
    verified, so the response time does not reveal whether the account
    exists. The global budget, the
    account's bucket and the audit events (prefixed with audit_prefix) are
    the same for teachers and students. Returns the account and the upgraded
    hash to store, if the password was hashed with outdated parameters.
    """
    # Resolving the account before the budget check is what lets a real
    # teacher or student still sign in while an anonymous flood holds the
    # budget open.
    enforce_global_auth_limit(request, known_identity=account is not None)
    limiter = request.app.state.login_rate_limiter
    retry_after = limiter.reserve(subject)
    if retry_after:
        audit_event(f"{audit_prefix}.login_rate_limited")
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.AUTH_RATE_LIMITED,
            "Trop de tentatives de connexion",
            headers={"Retry-After": str(retry_after)},
        )
    # Hashing can wait for a free slot: end the transaction first, so the
    # request does not hold a pooled connection meanwhile.
    session.commit()
    password_valid, upgraded_hash = verify_password_and_update(
        password, encoded_hash or DUMMY_PASSWORD_HASH
    )
    if account is None or encoded_hash is None or not password_valid:
        audit_event(f"{audit_prefix}.login_failed")
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            "Identifiants invalides",
        )
    # Give back only this attempt: clearing the whole bucket would hand
    # whoever is guessing this password a fresh allowance at every sign-in.
    limiter.release(subject)
    return account, upgraded_hash
