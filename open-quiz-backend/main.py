from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import build_session_factory
from app.models import User
from app.rate_limit import LoginRateLimiter
from app.routers import admin, auth, health, quizzes, users
from app.security import hash_password, verify_password


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        with session_factory() as session:
            admin_user = session.scalar(
                select(User).where(User.username == settings.admin_username)
            )
            if admin_user is None:
                session.add(
                    User(
                        username=settings.admin_username,
                        display_name="Administrator",
                        password_hash=hash_password(settings.admin_password),
                        is_admin=True,
                    )
                )
            else:
                admin_user.is_admin = True
                admin_user.is_active = True
                if not verify_password(
                    settings.admin_password, admin_user.password_hash
                ):
                    admin_user.password_hash = hash_password(settings.admin_password)
            session.commit()
        yield

    production = settings.environment == "production"
    app = FastAPI(
        title="Open Quiz API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.login_rate_limiter = LoginRateLimiter(
        settings.login_attempts, settings.login_window_seconds
    )
    if production:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
        )
        if request.url.path.startswith("/api/auth"):
            response.headers["Cache-Control"] = "no-store"
        if production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(admin.router)
    app.include_router(quizzes.router)
    return app


app = create_app()
