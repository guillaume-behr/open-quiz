"""Request logs, without personal data.

Every request is logged as one JSON line (method, route template, status,
duration), with no address and no identifier: the route appears as its
template, never with a join code or an id.
"""

import json
import logging
import sys
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

access_logger = logging.getLogger("open_quiz.access")
access_logger.setLevel(logging.INFO)
access_handler = logging.StreamHandler(sys.stdout)
access_handler.setLevel(logging.INFO)
access_logger.addHandler(access_handler)
access_logger.propagate = False


def route_template(scope: Scope) -> str:
    """The matched route's path template, or a fixed label when none matched."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class AccessLogMiddleware:
    """Log every HTTP request as one JSON line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status = 500

        async def record_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, record_status)
        finally:
            access_logger.info(
                json.dumps(
                    {
                        "event": "http.request",
                        "method": scope["method"],
                        "route": route_template(scope),
                        "status": status,
                        "duration_ms": round((perf_counter() - started) * 1000, 1),
                    }
                )
            )
