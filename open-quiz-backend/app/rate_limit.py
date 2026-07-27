from hashlib import sha256
from time import time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import LoginFailure


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

    def retry_after(
        self,
        session: Session,
        ip_address: str,
        username: str,
    ) -> int:
        now = int(time())
        cutoff = now - self.window_seconds
        session.execute(delete(LoginFailure).where(LoginFailure.occurred_at <= cutoff))
        session.commit()

        limits = (
            (self._ip_key(ip_address), self.ip_limit),
            (self._account_key(username), self.account_limit),
        )
        for limiter_key, limit in limits:
            count, oldest = session.execute(
                select(
                    func.count(LoginFailure.id),
                    func.min(LoginFailure.occurred_at),
                ).where(LoginFailure.limiter_key == limiter_key)
            ).one()
            if count >= limit and oldest is not None:
                return max(1, self.window_seconds - (now - oldest))
        return 0

    def record_failure(
        self,
        session: Session,
        ip_address: str,
        username: str,
    ) -> None:
        now = int(time())
        session.add_all(
            [
                LoginFailure(
                    limiter_key=self._ip_key(ip_address),
                    occurred_at=now,
                ),
                LoginFailure(
                    limiter_key=self._account_key(username),
                    occurred_at=now,
                ),
            ]
        )
        session.commit()

    def clear(
        self,
        session: Session,
        ip_address: str,
        username: str,
    ) -> None:
        session.execute(
            delete(LoginFailure).where(
                LoginFailure.limiter_key.in_(
                    (
                        self._ip_key(ip_address),
                        self._account_key(username),
                    )
                )
            )
        )

    @staticmethod
    def _ip_key(ip_address: str) -> str:
        return f"ip:{ip_address}"

    @staticmethod
    def _account_key(username: str) -> str:
        digest = sha256(username.casefold().encode()).hexdigest()
        return f"account:{digest}"
