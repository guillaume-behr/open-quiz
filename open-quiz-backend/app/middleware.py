from collections.abc import Callable

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.dependencies import authenticated_user_from_token
from app.models import User

LARGE_QUESTION_BODY_BYTES = 64 * 1024 * 1024


class RequestBodyTooLarge(Exception):
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
        path = scope.get("path", "")
        return (
            scope.get("method") == "POST"
            and path.startswith("/api/question-banks")
            and path.endswith(("/questions", "/import", "/update"))
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
        detail: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=headers,
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        elevated = self._uses_elevated_limit(scope)
        if elevated:
            user = self._authenticated_user(scope)
            if user is None:
                await self._respond(
                    scope,
                    receive,
                    send,
                    401,
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
                    "Invalid Content-Length header",
                )
                return
            if declared_length < 0:
                await self._respond(
                    scope,
                    receive,
                    send,
                    400,
                    "Invalid Content-Length header",
                )
                return
            if declared_length > limit:
                await self._respond(
                    scope,
                    receive,
                    send,
                    413,
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
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._respond(
                scope,
                receive,
                send,
                413,
                "Request body is too large",
            )
