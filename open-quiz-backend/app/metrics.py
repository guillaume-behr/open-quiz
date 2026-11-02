"""Operational metrics and request logs, without personal data.

Metrics are served in the Prometheus format on /metrics when METRICS_ENABLED
is true. The path sits outside /api, which is all the frontend proxy forwards,
so only the internal network reaches it. Labels hold route templates, fixed
names and status codes: never a join code, a name or an address.

Every request is also logged as one JSON line (method, route template, status,
duration), again with no address and no identifier.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "open_quiz_http_requests",
    "HTTP requests answered, by method, route template and status.",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "open_quiz_http_request_duration_seconds",
    "Time to answer an HTTP request, by method and route template.",
    ["method", "route"],
)
WEBSOCKETS_ACTIVE = Gauge(
    "open_quiz_websockets_active",
    "Live WebSockets currently open, by feed.",
    ["feed"],
)
RATE_LIMIT_REJECTIONS = Counter(
    "open_quiz_rate_limit_rejections",
    "Requests a rate limiter refused, by limiter.",
    ["limiter"],
)
RETENTION_DURATION = Histogram(
    "open_quiz_retention_duration_seconds",
    "Duration of one data retention run.",
)
DATABASE_CONNECTIONS = Gauge(
    "open_quiz_database_connections",
    "Connections of this worker's database pool, by state.",
    ["state"],
)

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


class RequestMetricsMiddleware:
    """Count, time and log every HTTP request."""

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
            duration = perf_counter() - started
            method = scope["method"]
            route = route_template(scope)
            HTTP_REQUESTS.labels(method, route, str(status)).inc()
            HTTP_DURATION.labels(method, route).observe(duration)
            access_logger.info(
                json.dumps(
                    {
                        "event": "http.request",
                        "method": method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(duration * 1000, 1),
                    }
                )
            )


@contextmanager
def tracked_websocket(feed: str) -> Iterator[None]:
    WEBSOCKETS_ACTIVE.labels(feed).inc()
    try:
        yield
    finally:
        WEBSOCKETS_ACTIVE.labels(feed).dec()
