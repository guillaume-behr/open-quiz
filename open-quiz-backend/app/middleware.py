from asyncio import to_thread
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.access_log import AccessLogMiddleware
from app.config import Settings
from app.dependencies import authenticated_user_from_token
from app.errors import ErrorCode, api_error
from app.models import User

# JSON imports base64-encode up to 64 MiB of decoded images. Reserve enough
# request space for that 4:3 expansion plus the surrounding question data.
LARGE_QUESTION_BODY_BYTES = 96 * 1024 * 1024


class RequestBodyTooLargeError(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Enforce body limits while streaming and gate elevated limits by auth."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int,
        session_factory: Callable,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.session_factory = session_factory

    @staticmethod
    def _uses_elevated_limit(scope: Scope) -> bool:
        if scope.get("method") != "POST":
            return False
        parts = scope.get("path", "").strip("/").split("/")
        if parts[:2] != ["api", "question-banks"]:
            return False
        return (
            parts == ["api", "question-banks", "import"]
            or (len(parts) == 4 and parts[2].isdigit() and parts[3] == "questions")
            or (
                len(parts) == 5
                and parts[2] == "questions"
                and parts[3].isdigit()
                and parts[4] == "update"
            )
        )

    def _authenticated_user(self, scope: Scope) -> User | None:
        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            return None
        request = Request(scope)
        with self.session_factory() as session:
            return authenticated_user_from_token(request, token, session)

    @staticmethod
    async def _respond(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": api_error(code, message)},
            headers=headers,
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        elevated = self._uses_elevated_limit(scope)
        if elevated:
            user = await to_thread(self._authenticated_user, scope)
            if user is None:
                await self._respond(
                    scope,
                    receive,
                    send,
                    401,
                    ErrorCode.AUTH_TOKEN_INVALID,
                    "Jeton d’authentification invalide ou expiré",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                return
            if user.is_admin:
                await self._respond(
                    scope,
                    receive,
                    send,
                    403,
                    ErrorCode.AUTH_PROFESSOR_ACCOUNT_REQUIRED,
                    "Accès enseignant requis",
                )
                return

        limit = (
            max(self.default_limit, LARGE_QUESTION_BODY_BYTES)
            if elevated
            else self.default_limit
        )
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await self._respond(
                    scope,
                    receive,
                    send,
                    400,
                    ErrorCode.REQUEST_CONTENT_LENGTH_INVALID,
                    "Invalid Content-Length header",
                )
                return
            if declared_length < 0:
                await self._respond(
                    scope,
                    receive,
                    send,
                    400,
                    ErrorCode.REQUEST_CONTENT_LENGTH_INVALID,
                    "Invalid Content-Length header",
                )
                return
            if declared_length > limit:
                await self._respond(
                    scope,
                    receive,
                    send,
                    413,
                    ErrorCode.REQUEST_BODY_TOO_LARGE,
                    "Request body is too large",
                )
                return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > limit:
                    raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._respond(
                scope,
                receive,
                send,
                413,
                ErrorCode.REQUEST_BODY_TOO_LARGE,
                "Request body is too large",
            )


def add_middleware(
    app: FastAPI, settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    """Body limits, CORS, HTTPS, trusted hosts, security headers and access log.

    Each middleware added wraps the previous ones, so the access log, added
    last, sees every response, including the rejections of the others.
    """
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
        # Outside the redirect, which builds its target from the Host header:
        # a name the instance does not go by is refused before it is echoed.
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
            www_redirect=False,
        )

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

    app.add_middleware(AccessLogMiddleware)
