import logging
import tomllib
from asyncio import CancelledError, create_task, sleep, to_thread
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from pathlib import Path
from time import time

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.access_log import AccessLogMiddleware
from app.audit import audit_event
from app.config import Settings, get_settings
from app.database import (
    MAINTENANCE_LOCK_KEY,
    build_rate_limiter_session_factory,
    build_session_factory,
    postgres_url,
)
from app.errors import ErrorCode, api_error
from app.live_quiz import LiveQuizHub
from app.live_relay import PostgresLiveRelay
from app.live_updates import publish_session_change
from app.middleware import RequestBodyLimitMiddleware
from app.models import (
    AuthenticationChallenge,
    LoginRateLimit,
    ProblemReport,
    RefreshSession,
    RefreshSessionFamily,
    SecurityState,
    User,
)
from app.quiz_session_records import delete_quiz_session_records
from app.rate_limit import (
    TWO_FACTOR_DAILY_NAMESPACE,
    TWO_FACTOR_DAILY_WINDOW_SECONDS,
    FixedWindowRateLimiter,
    LoginRateLimiter,
)
from app.routers import (
    admin,
    auth,
    class_imports,
    classes,
    grade_levels,
    health,
    live,
    makeup,
    problem_reports,
    question_bank_transfer,
    question_banks,
    questions,
    quizzes,
    results,
    student_auth,
    student_sessions,
    students,
    training,
    users,
)
from app.security import hash_password, verify_password
from app.services.question_draws import InsufficientQuestionsError
from app.services.session_lifecycle import expire_due_quiz_sessions
from app.session_retention import (
    close_abandoned_sessions,
    expired_exam_result_ids,
    expired_training_session_ids,
)
from app.stored_images import delete_unreferenced_images

logger = logging.getLogger("open_quiz")
JWT_FINGERPRINT_KEY = "jwt_secret_fingerprint"
MANAGED_ADMIN_KEY = "managed_admin_user_id"
RETENTION_MAINTENANCE_INTERVAL_SECONDS = 3600
# How late a session may end after its deadline when nobody has it open.
SESSION_EXPIRY_INTERVAL_SECONDS = 2

# The image installs dependencies without the project itself, so there is no
# package metadata to read: pyproject.toml, copied next to this file, is the
# single source of the backend version.
VERSION = tomllib.loads((Path(__file__).parent / "pyproject.toml").read_text())[
    "project"
]["version"]


def revoke_sessions_on_jwt_rotation(
    session: Session, settings: Settings, now: int
) -> None:
    """Revoke every long session once JWT_SECRET has changed."""
    fingerprint = hmac_new(
        settings.totp_encryption_key.encode(),
        settings.jwt_secret.encode(),
        sha256,
    ).hexdigest()
    fingerprint_state = session.get(SecurityState, JWT_FINGERPRINT_KEY)
    if fingerprint_state is None:
        unmapped_session = session.scalar(
            select(RefreshSession.id)
            .outerjoin(
                RefreshSessionFamily,
                RefreshSessionFamily.session_id == RefreshSession.id,
            )
            .where(
                RefreshSession.revoked_at.is_(None),
                RefreshSessionFamily.session_id.is_(None),
            )
            .limit(1)
        )
        if unmapped_session is not None:
            session.execute(
                update(RefreshSession)
                .where(RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            audit_event("security.legacy_sessions_revoked")
        session.add(SecurityState(key=JWT_FINGERPRINT_KEY, value=fingerprint))
    elif fingerprint_state.value != fingerprint:
        session.execute(
            update(RefreshSession)
            .where(RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        fingerprint_state.value = fingerprint
        audit_event("security.jwt_secret_rotated_sessions_revoked")


def managed_administrator(session: Session, settings: Settings, now: int) -> User:
    """The one administrator ADMIN_USERNAME and ADMIN_PASSWORD manage.

    At the first start it adopts or creates that account and disables any
    other administrator; afterwards it follows ADMIN_USERNAME renames.
    """
    managed_state = session.get(SecurityState, MANAGED_ADMIN_KEY)
    configured_user = session.scalar(
        select(User).where(User.username == settings.admin_username)
    )
    if managed_state is None:
        administrators = list(
            session.scalars(select(User).where(User.is_admin.is_(True)))
        )
        if configured_user is not None:
            admin_user = configured_user
        elif len(administrators) == 1:
            admin_user = administrators[0]
            admin_user.username = settings.admin_username
        elif administrators:
            raise RuntimeError(
                "Multiple unmanaged administrators exist; resolve them "
                "before starting the application"
            )
        else:
            admin_user = User(
                username=settings.admin_username,
                display_name="Administrator",
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
            )
            session.add(admin_user)
            session.flush()

        for stale_admin in administrators:
            if stale_admin.id != admin_user.id:
                stale_admin.is_admin = False
                stale_admin.is_active = False
                session.execute(
                    update(RefreshSession)
                    .where(
                        RefreshSession.user_id == stale_admin.id,
                        RefreshSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                audit_event(
                    "security.stale_administrator_disabled",
                    user_id=stale_admin.id,
                )
        session.add(
            SecurityState(
                key=MANAGED_ADMIN_KEY,
                value=str(admin_user.id),
            )
        )
    else:
        try:
            managed_user_id = int(managed_state.value)
        except ValueError as error:
            raise RuntimeError("Managed administrator state is invalid") from error
        managed_user = session.get(User, managed_user_id)
        if managed_user is None:
            raise RuntimeError("The managed administrator account is missing")
        admin_user = managed_user
        if configured_user is not None and configured_user.id != admin_user.id:
            raise RuntimeError(
                "ADMIN_USERNAME belongs to a different account; choose a "
                "unique username before starting the application"
            )
        if admin_user.username != settings.admin_username:
            previous_username = admin_user.username
            admin_user.username = settings.admin_username
            audit_event(
                "security.managed_administrator_renamed",
                user_id=admin_user.id,
                previous_username=previous_username,
            )
    return admin_user


def apply_administrator_settings(
    admin_user: User, session: Session, settings: Settings, now: int
) -> None:
    """Keep the managed account active, and on ADMIN_PASSWORD."""
    admin_user.is_admin = True
    admin_user.is_active = True
    if not verify_password(settings.admin_password, admin_user.password_hash):
        admin_user.password_hash = hash_password(settings.admin_password)
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == admin_user.id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        audit_event(
            "security.administrator_password_rotated_sessions_revoked",
            user_id=admin_user.id,
        )


def synchronize_security_state(
    session_factory,
    settings: Settings,
) -> None:
    now = int(time())
    with session_factory() as session:
        # Every worker runs this at startup: one at a time.
        session.execute(select(func.pg_advisory_xact_lock(MAINTENANCE_LOCK_KEY)))
        revoke_sessions_on_jwt_rotation(session, settings, now)
        admin_user = managed_administrator(session, settings, now)
        apply_administrator_settings(admin_user, session, settings, now)
        session.commit()


def enforce_data_retention(
    session_factory, settings: Settings, now: datetime | None = None
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
        expired_refresh_count = session.execute(
            delete(RefreshSession).where(RefreshSession.expires_at <= epoch)
        ).rowcount
        expired_challenge_count = session.execute(
            delete(AuthenticationChallenge).where(
                AuthenticationChallenge.expires_at <= epoch
            )
        ).rowcount
        expired_report_count = session.execute(
            delete(ProblemReport).where(ProblemReport.created_at <= report_cutoff)
        ).rowcount
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


PUBLIC_INFORMATION_VARIABLES = (
    ("LEGAL_HOST_NAME", "legal_host_name"),
    ("LEGAL_HOST_ADDRESS", "legal_host_address"),
    # The legal notice flags the host as incomplete without its phone number,
    # so the startup warning has to consider it required too.
    ("LEGAL_HOST_PHONE", "legal_host_phone"),
    ("PRIVACY_CONTROLLER_NAME", "privacy_controller_name"),
    ("PRIVACY_CONTROLLER_CONTACT", "privacy_controller_contact"),
    ("PRIVACY_LEGAL_BASIS", "privacy_legal_basis"),
    ("PRIVACY_RECIPIENTS", "privacy_recipients"),
    ("PRIVACY_TEACHER_DATA_RETENTION", "privacy_teacher_data_retention"),
    ("PRIVACY_STUDENT_DATA_RETENTION", "privacy_student_data_retention"),
    ("PRIVACY_SECURITY_LOG_RETENTION", "privacy_security_log_retention"),
)


def warn_missing_public_information(settings: Settings) -> list[str]:
    """Name the legal mentions a production instance still has to publish.

    An empty value never blocks the start: an instance may legitimately run
    before its operator has settled who the controller is. It must not do so
    silently, because the public pages then carry no identity to address a
    rights request to.
    """
    if settings.environment != "production":
        return []
    missing = [
        name
        for name, attribute in PUBLIC_INFORMATION_VARIABLES
        if not getattr(settings, attribute).strip()
    ]
    if missing:
        audit_event("security.public_information_incomplete", variables=missing)
    return missing


def expire_due_sessions(session_factory, hub: LiveQuizHub) -> int:
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


def attach_rate_limiters(app: FastAPI, settings: Settings) -> None:
    """Give the app its limiters, which count attempts in a pool of their own."""
    limiter_sessions = build_rate_limiter_session_factory(settings.database_url)
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
    app.state.problem_report_rate_limiter = FixedWindowRateLimiter(
        limiter_sessions,
        settings.problem_report_attempts,
        settings.problem_report_window_seconds,
        "problem-report",
    )


def add_security_middleware(
    app: FastAPI, settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    """Body limits, CORS, HTTPS and security headers, in this wrapping order."""
    production = settings.environment == "production"
    app.add_middleware(
        RequestBodyLimitMiddleware,
        default_limit=settings.max_request_body_bytes,
        session_factory=session_factory,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_origin_regex=(
            r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"
            if settings.environment == "development"
            else None
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Quiz-Token",
            "X-Refresh-Proof",
        ],
        expose_headers=["X-Page", "X-Page-Size", "X-Total-Count"],
    )
    if production:
        app.add_middleware(HTTPSRedirectMiddleware)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        if production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


def include_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(problem_reports.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(class_imports.router)
    app.include_router(classes.router)
    app.include_router(students.router)
    app.include_router(student_auth.router)
    app.include_router(grade_levels.router)
    # Before quizzes: /sessions/{session_id} would capture /sessions/results.
    app.include_router(results.router)
    app.include_router(quizzes.router)
    app.include_router(student_sessions.router)
    app.include_router(makeup.router)
    app.include_router(training.router)
    app.include_router(live.router)
    app.include_router(question_banks.router)
    app.include_router(questions.router)
    app.include_router(question_bank_transfer.router)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        synchronize_security_state(session_factory, settings)
        warn_missing_public_information(settings)
        enforce_data_retention(session_factory, settings)

        live_relay.start()
        maintenance_task = create_task(
            maintain_data_retention_periodically(session_factory, settings)
        )
        expiry_task = create_task(
            expire_sessions_periodically(session_factory, app.state.live_quiz_hub)
        )
        try:
            yield
        finally:
            live_relay.stop()
            for task in (maintenance_task, expiry_task):
                task.cancel()
                with suppress(CancelledError):
                    await task

    production = settings.environment == "production"
    app = FastAPI(
        title="Open Quiz API",
        version=VERSION,
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.live_quiz_hub = LiveQuizHub()
    # Carries live notifications to the other Uvicorn workers (WEB_CONCURRENCY).
    live_relay = PostgresLiveRelay(
        postgres_url(settings.database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False),
        app.state.live_quiz_hub.publish_local,
    )
    app.state.live_quiz_hub.attach_relay(live_relay.send)
    attach_rate_limiters(app, settings)
    add_security_middleware(app, settings, session_factory)

    @app.exception_handler(InsufficientQuestionsError)
    async def insufficient_questions(
        _request: Request, error: InsufficientQuestionsError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": api_error(ErrorCode.QUIZ_QUESTIONS_INSUFFICIENT, str(error))
            },
        )

    app.add_middleware(AccessLogMiddleware)

    include_routers(app)
    return app


app = create_app()
