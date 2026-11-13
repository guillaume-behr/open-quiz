"""Revoking what an account signed in with: refresh sessions and 2FA enrollment.

Every place that ends sign-in sessions goes through revoke_refresh_sessions(),
and the administrator route and the recovery script reset an account through
reset_credentials(), so the two cannot drift apart.
"""

from time import time

from sqlalchemy import ColumnElement, delete, update
from sqlalchemy.orm import Session

from app.core.auth_guards import (
    password_rate_subject,
    trusted_password_rate_subject,
    two_factor_rate_subject,
)
from app.core.database import affected_rows
from app.core.rate_limit import CredentialRateLimiters
from app.models import (
    AuthenticationChallenge,
    RefreshSession,
    TwoFactorCredential,
    User,
)


def revoke_refresh_sessions(
    session: Session, now: int, *criteria: ColumnElement[bool]
) -> int:
    """Revoke the live refresh sessions matching criteria; count them."""
    result = session.execute(
        update(RefreshSession)
        .where(RefreshSession.revoked_at.is_(None), *criteria)
        .values(revoked_at=now)
    )
    return affected_rows(result)


def revoke_user_sessions(
    session: Session, user_id: int, now: int, *, challenges: bool = True
) -> None:
    """Revoke every refresh session of an account.

    With challenges, its pending two-factor challenges go too: a challenge
    stands for a password that was accepted, so whatever ends the account's
    sessions ends those as well.
    """
    revoke_refresh_sessions(session, now, RefreshSession.user_id == user_id)
    if challenges:
        session.execute(
            delete(AuthenticationChallenge).where(
                AuthenticationChallenge.user_id == user_id
            )
        )


def clear_credential_rate_limits(user: User, limiters: CredentialRateLimiters) -> None:
    """Empty the attempt buckets an attacker may have filled for this account."""
    limiters.login.clear_subject(password_rate_subject(user.username))
    limiters.login.clear_subject(trusted_password_rate_subject(user.id))
    limiters.login.clear_subject(two_factor_rate_subject(user.id))
    limiters.two_factor_daily.clear_subject(two_factor_rate_subject(user.id))


def reset_credentials(
    user: User,
    session: Session,
    limiters: CredentialRateLimiters,
    *,
    two_factor: bool,
) -> None:
    """Revoke the account's sessions, and its 2FA enrollment with two_factor.

    Commits, then clears the attempt buckets: a new enrollment is confirmed
    with a code, and buckets an attacker filled must not keep the rightful
    owner from signing in or enrolling again.
    """
    revoke_user_sessions(session, user.id, int(time()))
    if two_factor:
        session.execute(
            delete(TwoFactorCredential).where(TwoFactorCredential.user_id == user.id)
        )
    session.commit()
    clear_credential_rate_limits(user, limiters)


def reset_two_factor(
    user: User, session: Session, limiters: CredentialRateLimiters
) -> None:
    """Require a new 2FA enrollment and end every session of the account."""
    reset_credentials(user, session, limiters, two_factor=True)
