# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml).
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# The dependencies are installed in a build stage: uv, a package manager, has
# no place in the image that runs in production.
FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999 AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The same base image and path as the build stage: the virtual environment's
# scripts point at /app/.venv/bin/python, itself a link to the base's Python.
COPY --from=build /app/.venv ./.venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini main.py ./
COPY scripts ./scripts

USER 10001:10001

EXPOSE 8000

# uvicorn trusts X-Forwarded-* headers from these addresses only: the
# frontend proxy of docker-compose.yml by default, which passes its own.
ENV FORWARDED_ALLOW_IPS=172.28.0.2,127.0.0.1
# Uvicorn reads its worker count from WEB_CONCURRENCY. Live updates reach the
# sockets of every worker through PostgreSQL (app/live_relay.py).
ENV WEB_CONCURRENCY=1
# --no-access-log: Uvicorn would log each client's address; app/access_log.py
# logs every request instead, without any.
CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log", "--limit-concurrency", "1024", "--backlog", "2048", "--ws-max-size", "4096", "--ws-max-queue", "1", "--ws-per-message-deflate", "false", "--timeout-keep-alive", "5"]
