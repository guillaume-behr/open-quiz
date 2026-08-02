from asyncio import CancelledError, create_task, sleep, to_thread
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from time import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from sqlalchemy import delete, select, update

from app.audit import audit_event
from app.config import Settings, get_settings
from app.database import build_session_factory
from app.middleware import RequestBodyLimitMiddleware
from app.models import (
    AuthenticationChallenge,
    LoginRateLimit,
    ProblemReport,
    QuizSession,
    RefreshSession,
    RefreshSessionFamily,
    SecurityState,
    User,
)
from app.rate_limit import FixedWindowRateLimiter, LoginRateLimiter
from app.routers import (
    admin,
    auth,
    classes,
    grade_levels,
    health,
    problem_reports,
    question_banks,
    quizzes,
    student_auth,
    students,
    users,
)
from app.security import hash_password, verify_password

JWT_FINGERPRINT_KEY = "jwt_secret_fingerprint"
MANAGED_ADMIN_KEY = "managed_admin_user_id"
RETENTION_MAINTENANCE_INTERVAL_SECONDS = 3600


def synchronize_security_state(
    session_factory,
    settings: Settings,
) -> None:
    now = int(time())
    with session_factory() as session:
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
            admin_user = session.get(User, managed_user_id)
            if admin_user is None:
                raise RuntimeError("The managed administrator account is missing")
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
        session.commit()


def enforce_data_retention(session_factory, settings: Settings) -> None:
    now = int(time())
    quiz_cutoff = datetime.now(UTC) - timedelta(
        days=settings.quiz_result_retention_days
    )
    report_cutoff = datetime.now(UTC) - timedelta(
        days=settings.problem_report_retention_days
    )
    limiter_cutoff = now - max(
        settings.login_window_seconds,
        settings.quiz_rate_window_seconds,
        settings.problem_report_window_seconds,
    )
    with session_factory() as session:
        expired_quiz_session_ids = list(
            session.scalars(
                select(QuizSession.id).where(
                    QuizSession.status == "finished",
                    QuizSession.started_at.is_not(None),
                    QuizSession.started_at <= quiz_cutoff,
                )
            )
        )
        quizzes.delete_quiz_session_records(expired_quiz_session_ids, session)

        expired_refresh_session_ids = select(RefreshSession.id).where(
            RefreshSession.expires_at <= now
        )
        session.execute(
            delete(RefreshSessionFamily).where(
                RefreshSessionFamily.session_id.in_(expired_refresh_session_ids)
            )
        )
        expired_refresh_count = session.execute(
            delete(RefreshSession).where(RefreshSession.expires_at <= now)
        ).rowcount
        expired_challenge_count = session.execute(
            delete(AuthenticationChallenge).where(
                AuthenticationChallenge.expires_at <= now
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
        session.commit()

    if any(
        (
            expired_quiz_session_ids,
            expired_refresh_count,
            expired_challenge_count,
            expired_report_count,
        )
    ):
        audit_event(
            "security.data_retention_enforced",
            quiz_sessions=len(expired_quiz_session_ids),
            refresh_sessions=expired_refresh_count,
            authentication_challenges=expired_challenge_count,
            problem_reports=expired_report_count,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        synchronize_security_state(session_factory, settings)
        enforce_data_retention(session_factory, settings)

        async def maintain_data_retention() -> None:
            while True:
                await sleep(RETENTION_MAINTENANCE_INTERVAL_SECONDS)
                await to_thread(enforce_data_retention, session_factory, settings)

        maintenance_task = create_task(maintain_data_retention())
        try:
            yield
        finally:
            maintenance_task.cancel()
            with suppress(CancelledError):
                await maintenance_task

    production = settings.environment == "production"
    app = FastAPI(
        title="Open Quiz API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.login_rate_limiter = LoginRateLimiter(
        settings.login_attempts,
        settings.login_window_seconds,
        settings.jwt_secret,
    )
    app.state.auth_global_rate_limiter = FixedWindowRateLimiter(
        settings.global_login_attempts,
        settings.global_login_window_seconds,
        "auth",
    )
    app.state.quiz_join_rate_limiter = FixedWindowRateLimiter(
        settings.quiz_join_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-join",
    )
    app.state.quiz_participant_rate_limiter = FixedWindowRateLimiter(
        settings.quiz_participant_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-participant",
    )
    app.state.quiz_violation_rate_limiter = FixedWindowRateLimiter(
        settings.quiz_violation_attempts,
        settings.quiz_rate_window_seconds,
        "quiz-violation",
    )
    app.state.problem_report_rate_limiter = FixedWindowRateLimiter(
        settings.problem_report_attempts,
        settings.problem_report_window_seconds,
        "problem-report",
    )
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
        allow_methods=["GET", "POST", "DELETE"],
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

    app.include_router(health.router)
    app.include_router(problem_reports.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(classes.router)
    app.include_router(students.router)
    app.include_router(student_auth.router)
    app.include_router(grade_levels.router)
    app.include_router(quizzes.router)
    app.include_router(question_banks.router)
    return app


app = create_app()
