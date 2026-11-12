from collections.abc import Callable
from hashlib import sha256
from hmac import new as hmac_new
from time import time

from fastapi import FastAPI
from sqlalchemy import case, delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import build_rate_limiter_session_factory
from app.models import LoginRateLimit

# The second, longer window on two-factor codes (see attach_rate_limiters).
TWO_FACTOR_DAILY_WINDOW_SECONDS = 86400
TWO_FACTOR_DAILY_NAMESPACE = "two-factor-daily"

# Limiters write in transactions of their own, through their own sessions:
# they must neither commit the work a route has pending nor lose a counted
# attempt when that route rolls back. attach_rate_limiters() gives them a small
# engine apart from the request pool, so a request holding a connection never
# waits on that same pool to count an attempt.
LimiterSessions = Callable[[], Session]


def _reserve_window(
    sessions: LimiterSessions,
    *,
    limiter_key: str,
    limit: int,
    window_seconds: int,
) -> int:
    now = int(time())
    cutoff = now - window_seconds
    # An expired row is reset by the upsert below; the hourly maintenance
    # deletes the ones nobody uses any more.
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
    with sessions() as session, session.begin():
        attempts, window_started_at = session.execute(statement).one()
    if attempts <= limit:
        return 0
    return max(1, window_seconds - (now - window_started_at))


class LoginRateLimiter:
    """Database-backed authentication limiter shared by all API workers."""

    # 16.7M buckets. The bound exists to stop attacker-chosen identifiers from
    # growing the table without limit, not to be small: at four characters two
    # unrelated accounts collided often enough that failed logins against one
    # locked the other out. The hourly maintenance deletes expired rows, so
    # the extra width costs far less than that collateral lockout.
    BUCKET_HEX_CHARACTERS = 6

    def __init__(
        self,
        sessions: LimiterSessions,
        account_limit: int,
        window_seconds: int,
        secret: str,
        namespace: str = "account",
    ) -> None:
        self.sessions = sessions
        self.account_limit = account_limit
        self.window_seconds = window_seconds
        self.secret = secret.encode()
        # Each window needs its own namespace: two windows sharing a key would
        # reset each other's counters.
        self.namespace = namespace

    def reserve(self, subject: str) -> int:
        """Atomically reserve an authentication attempt.

        A zero return value means the caller may continue. A positive value is
        the number of seconds to advertise in Retry-After.
        """
        retry_after = _reserve_window(
            self.sessions,
            limiter_key=self._account_key(subject),
            limit=self.account_limit,
            window_seconds=self.window_seconds,
        )
        if retry_after == 0:
            return 0
        self.release(subject)
        return retry_after

    def release(self, subject: str) -> None:
        """Release the reservation for a successful authentication step."""
        with self.sessions() as session, session.begin():
            session.execute(
                update(LoginRateLimit)
                .where(
                    LoginRateLimit.limiter_key == self._account_key(subject),
                    LoginRateLimit.attempts > 0,
                )
                .values(attempts=LoginRateLimit.attempts - 1)
            )

    def clear_subject(self, subject: str) -> None:
        with self.sessions() as session, session.begin():
            session.execute(
                delete(LoginRateLimit).where(
                    LoginRateLimit.limiter_key == self._account_key(subject)
                )
            )

    def _account_key(self, subject: str) -> str:
        # Bound attacker-controlled identifiers to a fixed number of buckets.
        # Key the mapping so an attacker cannot deliberately construct an
        # identifier that shares a victim's small, bounded bucket.
        digest = hmac_new(self.secret, subject.encode(), sha256).hexdigest()[
            : LoginRateLimiter.BUCKET_HEX_CHARACTERS
        ]
        return f"{self.namespace}:{digest}"


class FixedWindowRateLimiter:
    """Database-backed limiter for public quiz endpoints."""

    def __init__(
        self,
        sessions: LimiterSessions,
        limit: int,
        window_seconds: int,
        namespace: str,
    ) -> None:
        self.sessions = sessions
        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace

    def reserve(self, subject: str) -> int:
        return _reserve_window(
            self.sessions,
            limiter_key=self._key(subject),
            limit=self.limit,
            window_seconds=self.window_seconds,
        )

    def _key(self, subject: str) -> str:
        digest = sha256(subject.encode()).hexdigest()
        return f"{self.namespace}:{digest}"


def attach_rate_limiters(app: FastAPI, settings: Settings) -> None:
    """Give the app its limiters, which count attempts in a pool of their own."""
    limiter_sessions = build_rate_limiter_session_factory(settings.database_url)
    app.state.rate_limiter_sessions = limiter_sessions
    app.state.login_rate_limiter = LoginRateLimiter(
        limiter_sessions,
        settings.login_attempts,
        settings.login_window_seconds,
        settings.jwt_secret,
    )
    # Caps how many codes one account may try per day, so that someone who
    # holds the password cannot keep guessing at the short window's pace.
    app.state.two_factor_daily_rate_limiter = LoginRateLimiter(
        limiter_sessions,
        settings.two_factor_daily_attempts,
        TWO_FACTOR_DAILY_WINDOW_SECONDS,
        settings.jwt_secret,
        namespace=TWO_FACTOR_DAILY_NAMESPACE,
    )
    app.state.auth_global_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.global_login_attempts,
        settings.global_login_window_seconds,
        "auth",
    )
    app.state.quiz_join_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.quiz_join_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-join",
    )
    app.state.quiz_participant_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.quiz_participant_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-participant",
    )
    app.state.quiz_violation_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.quiz_violation_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-violation",
    )
    # A class import says whether each identifier exists on the instance:
    # this budget, per teacher, bounds how fast one account can probe them.
    app.state.class_import_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.class_import_attempts,
        settings.class_import_window_seconds,
        "class-import",
    )
    app.state.problem_report_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.problem_report_attempts,
        settings.problem_report_window_seconds,
        "problem-report",
    )
