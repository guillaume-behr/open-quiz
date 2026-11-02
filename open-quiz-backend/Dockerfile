# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml).
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini main.py ./
COPY scripts ./scripts

USER 10001:10001

EXPOSE 8000

# Uvicorn reads its worker count from WEB_CONCURRENCY. Live updates reach the
# sockets of every worker through PostgreSQL (app/live_relay.py).
ENV WEB_CONCURRENCY=1
CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=172.28.0.2,127.0.0.1", "--limit-concurrency", "1024", "--backlog", "2048", "--ws-max-size", "4096", "--ws-max-queue", "1", "--ws-per-message-deflate", "false", "--timeout-keep-alive", "5"]
