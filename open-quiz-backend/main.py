from contextlib import asynccontextmanager
from hashlib import sha256
from hmac import new as hmac_new
from time import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from app.audit import audit_event
from app.config import Settings, get_settings
from app.database import build_session_factory
from app.models import RefreshSession, RefreshSessionFamily, SecurityState, User
from app.rate_limit import LoginRateLimiter
from app.routers import admin, auth, health, question_banks, quizzes, users
from app.security import hash_password, verify_password

JWT_FINGERPRINT_KEY = "jwt_secret_fingerprint"
MANAGED_ADMIN_KEY = "managed_admin_user_id"


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
            session.add(
                SecurityState(key=JWT_FINGERPRINT_KEY, value=fingerprint)
            )
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = build_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        synchronize_security_state(session_factory, settings)
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
        settings.login_attempts,
        settings.login_account_attempts,
        settings.login_window_seconds,
    )
    if production:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_origin_regex=(
            r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"
            if settings.environment == "development"
            else None
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            response = None
            request_size_limit = settings.max_request_body_bytes
            if (
                request.method == "POST"
                and request.url.path.startswith("/api/question-banks")
                and (
                    request.url.path.endswith("/questions")
                    or request.url.path.endswith("/import")
                    or request.url.path.endswith("/update")
                )
            ):
                request_size_limit = max(request_size_limit, 64 * 1024 * 1024)
            content_length = request.headers.get("content-length")
            try:
                declared_length = int(content_length) if content_length else None
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
                declared_length = None
            if response is None and (
                declared_length is not None
                and declared_length > request_size_limit
            ):
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body is too large"},
                )
            elif response is None:
                chunks: list[bytes] = []
                received_bytes = 0
                async for chunk in request.stream():
                    received_bytes += len(chunk)
                    if received_bytes > request_size_limit:
                        response = JSONResponse(
                            status_code=413,
                            content={"detail": "Request body is too large"},
                        )
                        break
                    chunks.append(chunk)
                if response is None:
                    request._body = b"".join(chunks)
                    response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
        )
        if request.url.path.startswith("/api") and request.url.path != "/api/health":
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
    app.include_router(question_banks.router)
    return app


app = create_app()
