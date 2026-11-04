"""The FastAPI application: its state, middleware, routes and lifespan."""

from asyncio import CancelledError, create_task
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.config import (
    VERSION,
    Settings,
    get_settings,
    warn_missing_public_information,
)
from app.database import build_session_factory, postgres_url
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
    student_sessions,
    students,
    training,
    users,
)
from app.security_state import synchronize_security_state


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
    add_middleware(app, settings, session_factory)
    include_routers(app)
    return app
