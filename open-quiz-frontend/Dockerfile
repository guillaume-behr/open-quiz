FROM node:26.5.0-alpine3.23@sha256:0473b6671ff22c8eeb570c0e1e51408595d3171e73f8002c269b763f0a943149 AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

RUN setcap -r /usr/bin/caddy \
    && addgroup -S openquiz \
    && adduser -S -D -H -G openquiz openquiz

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

USER openquiz

EXPOSE 8080
