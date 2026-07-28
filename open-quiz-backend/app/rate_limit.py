from hashlib import sha256
from time import time

from sqlalchemy import case, delete, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models import LoginRateLimit


class LoginRateLimiter:
    """Database-backed authentication limiter shared by all API workers."""

    def __init__(
        self,
        ip_limit: int,
        account_limit: int,
        window_seconds: int,
    ) -> None:
        self.ip_limit = ip_limit
        self.account_limit = account_limit
        self.window_seconds = window_seconds

    def reserve(
        self,
        session: Session,
        ip_address: str,
        username: str,
    ) -> int:
        """Atomically reserve an authentication attempt.

        A zero return value means the caller may continue. A positive value is
        the number of seconds to advertise in Retry-After.
        """
        now = int(time())
        cutoff = now - self.window_seconds
        limits = (
            (self._ip_key(ip_address), self.ip_limit),
            (self._account_key(username), self.account_limit),
        )
        retry_after = 0
        for limiter_key, limit in limits:
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
            if attempts > limit:
                retry_after = max(
                    retry_after,
                    max(1, self.window_seconds - (now - window_started_at)),
                )
        session.commit()

        if retry_after:
            self.release(session, ip_address, username)
        return retry_after

    def release(
        self,
        session: Session,
        ip_address: str,
        username: str,
    ) -> None:
        """Release the reservation for a successful authentication step."""
        session.execute(
            update(LoginRateLimit)
            .where(
                LoginRateLimit.limiter_key.in_(
                    (
                        self._ip_key(ip_address),
                        self._account_key(username),
                    )
                ),
                LoginRateLimit.attempts > 0,
            )
            .values(attempts=LoginRateLimit.attempts - 1)
        )
        session.commit()

    def clear_account(
        self,
        session: Session,
        username: str,
    ) -> None:
        session.execute(
            delete(LoginRateLimit).where(
                LoginRateLimit.limiter_key == self._account_key(username)
            )
        )
        session.commit()

    @staticmethod
    def _ip_key(ip_address: str) -> str:
        return f"ip:{ip_address}"

    @staticmethod
    def _account_key(username: str) -> str:
        digest = sha256(username.casefold().encode()).hexdigest()
        return f"account:{digest}"


class FixedWindowRateLimiter:
    """Database-backed limiter for public quiz endpoints."""

    def __init__(self, limit: int, window_seconds: int, namespace: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace

    def check(self, session: Session, subject: str) -> int:
        now = int(time())
        limiter = session.get(LoginRateLimit, self._key(subject))
        if limiter is None:
            return 0
        elapsed = now - limiter.window_started_at
        if elapsed >= self.window_seconds or limiter.attempts < self.limit:
            return 0
        return max(1, self.window_seconds - elapsed)

    def reserve(self, session: Session, subject: str) -> int:
        now = int(time())
        cutoff = now - self.window_seconds
        limiter_key = self._key(subject)
        session.execute(
            delete(LoginRateLimit).where(
                LoginRateLimit.limiter_key.like(f"{self.namespace}:%"),
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
        if attempts <= self.limit:
            return 0
        return max(1, self.window_seconds - (now - window_started_at))

    def _key(self, subject: str) -> str:
        digest = sha256(subject.encode()).hexdigest()
        return f"{self.namespace}:{digest}"
