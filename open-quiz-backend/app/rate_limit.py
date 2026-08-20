from hashlib import sha256
from hmac import new as hmac_new
from time import time

from sqlalchemy import case, delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import LoginRateLimit


def _reserve_window(
    session: Session,
    *,
    limiter_key: str,
    namespace: str,
    limit: int,
    window_seconds: int,
) -> int:
    now = int(time())
    cutoff = now - window_seconds
    session.execute(
        delete(LoginRateLimit).where(
            LoginRateLimit.limiter_key.like(f"{namespace}:%"),
            LoginRateLimit.window_started_at <= cutoff,
        )
    )
    expired = LoginRateLimit.window_started_at <= cutoff
    statement = (
        insert(LoginRateLimit)
        .values(
            limiter_key=limiter_key,
            window_started_at=now,
            attempts=1,
        )
        .on_conflict_do_update(
            index_elements=[LoginRateLimit.limiter_key],
            set_={
                "window_started_at": case(
                    (expired, now),
                    else_=LoginRateLimit.window_started_at,
                ),
                "attempts": case(
                    (expired, 1),
                    else_=LoginRateLimit.attempts + 1,
                ),
            },
        )
        .returning(
            LoginRateLimit.attempts,
            LoginRateLimit.window_started_at,
        )
    )
    attempts, window_started_at = session.execute(statement).one()
    session.commit()
    if attempts <= limit:
        return 0
    return max(1, window_seconds - (now - window_started_at))


class LoginRateLimiter:
    """Database-backed authentication limiter shared by all API workers."""

    BUCKET_HEX_CHARACTERS = 4

    def __init__(
        self,
        account_limit: int,
        window_seconds: int,
        secret: str,
    ) -> None:
        self.account_limit = account_limit
        self.window_seconds = window_seconds
        self.secret = secret.encode()

    def reserve(
        self,
        session: Session,
        subject: str,
    ) -> int:
        """Atomically reserve an authentication attempt.

        A zero return value means the caller may continue. A positive value is
        the number of seconds to advertise in Retry-After.
        """
        retry_after = _reserve_window(
            session,
            limiter_key=self._account_key(subject),
            namespace="account",
            limit=self.account_limit,
            window_seconds=self.window_seconds,
        )
        if retry_after == 0:
            return 0
        self.release(session, subject)
        return retry_after

    def release(
        self,
        session: Session,
        subject: str,
    ) -> None:
        """Release the reservation for a successful authentication step."""
        session.execute(
            update(LoginRateLimit)
            .where(
                LoginRateLimit.limiter_key == self._account_key(subject),
                LoginRateLimit.attempts > 0,
            )
            .values(attempts=LoginRateLimit.attempts - 1)
        )
        session.commit()

    def clear_subject(
        self,
        session: Session,
        subject: str,
    ) -> None:
        session.execute(
            delete(LoginRateLimit).where(
                LoginRateLimit.limiter_key == self._account_key(subject)
            )
        )
        session.commit()

    def _account_key(self, subject: str) -> str:
        # Bound attacker-controlled identifiers to a fixed number of buckets.
        # Key the mapping so an attacker cannot deliberately construct an
        # identifier that shares a victim's small, bounded bucket.
        digest = hmac_new(self.secret, subject.encode(), sha256).hexdigest()[
            : LoginRateLimiter.BUCKET_HEX_CHARACTERS
        ]
        return f"account:{digest}"


class FixedWindowRateLimiter:
    """Database-backed limiter for public quiz endpoints."""

    def __init__(self, limit: int, window_seconds: int, namespace: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace

    def reserve(self, session: Session, subject: str) -> int:
        return _reserve_window(
            session,
            limiter_key=self._key(subject),
            namespace=self.namespace,
            limit=self.limit,
            window_seconds=self.window_seconds,
        )

    def _key(self, subject: str) -> str:
        digest = sha256(subject.encode()).hexdigest()
        return f"{self.namespace}:{digest}"
