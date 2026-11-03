"""Guards shared by sign-in routes: origin checks and attempt limits."""

from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from app.audit import audit_event
from app.errors import ErrorCode, api_error


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
            detail=api_error(
                ErrorCode.AUTH_ORIGIN_REJECTED, "Origine de la requête refusée"
            ),
        )


def password_rate_subject(username: str) -> str:
    return f"password:identity:{username}"


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
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=api_error(
            ErrorCode.AUTH_RATE_LIMITED, "Trop de tentatives de connexion"
        ),
        headers={"Retry-After": str(retry_after)},
    )


def two_factor_rate_subject(user_id: int) -> str:
    return f"two-factor:user:{user_id}"


def student_password_rate_subject(identifier: str) -> str:
    return f"student-password:identity:{identifier}"
