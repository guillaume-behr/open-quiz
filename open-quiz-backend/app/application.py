"""The FastAPI application: its state, middleware, routes and lifespan."""

import logging
from asyncio import CancelledError, create_task
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.choice_tokens import CHOICE_HMAC_ENTRY
from app.config import (
    VERSION,
    Settings,
    get_settings,
    warn_missing_public_information,
)
from app.database import build_session_factory, postgres_url
from app.errors import server_busy_response
from app.live_quiz import LiveQuizHub
from app.live_relay import PostgresLiveRelay
from app.maintenance import (
    enforce_data_retention,
    expire_sessions_periodically,
    maintain_data_retention_periodically,
)
from app.middleware import add_middleware
from app.rate_limit import attach_rate_limiters
from app.routers import (
    admin,
    auth,
    class_imports,
    classes,
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
    student_join,
    student_progress,
    student_sessions,
    students,
    training,
    users,
)
from app.security import choice_token_key
from app.security_state import synchronize_security_state

logger = logging.getLogger("open_quiz")


async def answer_pool_timeout(_: Request, error: Exception) -> JSONResponse:
    """Every pooled connection stayed taken: answer 503 rather than 500."""
    logger.warning("Database pool exhausted: %s", error)
    return server_busy_response()


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
    # Before quizzes: /sessions/{session_id} would capture /sessions/results.
    app.include_router(results.router)
    app.include_router(quizzes.router)
    app.include_router(student_join.router)
    app.include_router(student_progress.router)
    app.include_router(student_sessions.router)
    app.include_router(makeup.router)
    app.include_router(training.router)
    app.include_router(live.router)
    app.include_router(question_banks.router)
    app.include_router(questions.router)
    app.include_router(question_bank_transfer.router)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = build_session_factory(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
    )
    session_factory.configure(
        info={CHOICE_HMAC_ENTRY: choice_token_key(settings.jwt_secret)}
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
            for name, task in (
                ("data retention", maintenance_task),
                ("session expiry", expiry_task),
            ):
                task.cancel()
                try:
                    await task
                except CancelledError:
                    pass
                except Exception:
                    # The loops survive their own errors; one that still
                    # ended a task must not abort the shutdown.
                    logger.exception("Background task %s failed", name)
            # Close pooled connections now rather than when the engines are
            # garbage collected, so apps created one after another (tests,
            # reloads) do not pile up idle connections on the server.
            session_factory.kw["bind"].dispose()
            app.state.rate_limiter_sessions.kw["bind"].dispose()

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
    add_middleware(app, settings, session_factory)
    app.add_exception_handler(PoolTimeoutError, answer_pool_timeout)
    include_routers(app)
    return app
