"""Background maintenance: data retention and the expiry of timed sessions.

Both run once at startup and then periodically for as long as the
application serves; a failed run is logged and retried at the next tick.
"""

import logging
from asyncio import sleep, to_thread
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.audit import audit_event
from app.config import Settings
from app.database import MAINTENANCE_LOCK_KEY, affected_rows
from app.live_quiz import LiveQuizHub
from app.live_updates import publish_session_change
from app.models import (
    AuthenticationChallenge,
    LoginRateLimit,
    ProblemReport,
    RefreshSession,
    RefreshSessionFamily,
)
from app.quiz_session_records import delete_quiz_session_records
from app.rate_limit import TWO_FACTOR_DAILY_WINDOW_SECONDS
from app.services.session_lifecycle import expire_due_quiz_sessions
from app.session_retention import (
    close_abandoned_sessions,
    expired_exam_result_ids,
    expired_training_session_ids,
)
from app.stored_images import delete_unreferenced_images

logger = logging.getLogger("open_quiz")
RETENTION_MAINTENANCE_INTERVAL_SECONDS = 3600
# How late a session may end after its deadline when nobody has it open.
SESSION_EXPIRY_INTERVAL_SECONDS = 2


def enforce_data_retention(
    session_factory: sessionmaker[Session],
    settings: Settings,
    now: datetime | None = None,
) -> None:
    """Delete or settle everything past its retention, as of one instant."""
    now = now or datetime.now(UTC)
    epoch = int(now.timestamp())
    quiz_cutoff = now - timedelta(days=settings.quiz_result_retention_days)
    training_cutoff = now - timedelta(days=settings.training_result_retention_days)
    abandoned_cutoff = now - timedelta(days=settings.abandoned_session_retention_days)
    report_cutoff = now - timedelta(days=settings.problem_report_retention_days)
    limiter_cutoff = epoch - max(
        settings.login_window_seconds,
        TWO_FACTOR_DAILY_WINDOW_SECONDS,
        settings.quiz_rate_window_seconds,
        settings.problem_report_window_seconds,
    )
    with session_factory() as session:
        # Every worker runs this at startup: one at a time.
        session.execute(select(func.pg_advisory_xact_lock(MAINTENANCE_LOCK_KEY)))
        closed_count, discarded_count = close_abandoned_sessions(
            abandoned_cutoff, session
        )
        expired_quiz_session_ids = expired_exam_result_ids(quiz_cutoff, session)
        delete_quiz_session_records(expired_quiz_session_ids, session)

        expired_training_ids = expired_training_session_ids(training_cutoff, session)
        delete_quiz_session_records(expired_training_ids, session)

        expired_refresh_session_ids = select(RefreshSession.id).where(
            RefreshSession.expires_at <= epoch
        )
        session.execute(
            delete(RefreshSessionFamily).where(
                RefreshSessionFamily.session_id.in_(expired_refresh_session_ids)
            )
        )
        expired_refresh_count = affected_rows(
            session.execute(
                delete(RefreshSession).where(RefreshSession.expires_at <= epoch)
            )
        )
        expired_challenge_count = affected_rows(
            session.execute(
                delete(AuthenticationChallenge).where(
                    AuthenticationChallenge.expires_at <= epoch
                )
            )
        )
        expired_report_count = affected_rows(
            session.execute(
                delete(ProblemReport).where(ProblemReport.created_at <= report_cutoff)
            )
        )
        session.execute(
            delete(LoginRateLimit).where(
                LoginRateLimit.window_started_at <= limiter_cutoff
            )
        )
        # Images of deleted or edited questions and choices.
        delete_unreferenced_images(session)
        session.commit()

    if any(
        (
            expired_quiz_session_ids,
            expired_training_ids,
            closed_count,
            discarded_count,
            expired_refresh_count,
            expired_challenge_count,
            expired_report_count,
        )
    ):
        audit_event(
            "security.data_retention_enforced",
            quiz_sessions=len(expired_quiz_session_ids),
            training_sessions=len(expired_training_ids),
            abandoned_sessions_closed=closed_count,
            abandoned_sessions_discarded=discarded_count,
            refresh_sessions=expired_refresh_count,
            authentication_challenges=expired_challenge_count,
            problem_reports=expired_report_count,
        )


def expire_due_sessions(
    session_factory: sessionmaker[Session], hub: LiveQuizHub
) -> int:
    """Finish the sessions whose time is up and notify their live views."""
    with session_factory() as session:
        finished = expire_due_quiz_sessions(session)
        for quiz_session in finished:
            publish_session_change(hub, quiz_session, session)
    return len(finished)


async def expire_sessions_periodically(session_factory, hub: LiveQuizHub) -> None:
    while True:
        await sleep(SESSION_EXPIRY_INTERVAL_SECONDS)
        try:
            await to_thread(expire_due_sessions, session_factory, hub)
        except SQLAlchemyError:
            # The database may be briefly unavailable: the next tick retries.
            logger.exception("Session expiry failed")


async def maintain_data_retention_periodically(
    session_factory, settings: Settings
) -> None:
    while True:
        await sleep(RETENTION_MAINTENANCE_INTERVAL_SECONDS)
        try:
            await to_thread(enforce_data_retention, session_factory, settings)
        except SQLAlchemyError:
            # A failed run must not end the loop, or retention would stop
            # silently until the next restart: the next run retries.
            logger.exception("Data retention maintenance failed")
