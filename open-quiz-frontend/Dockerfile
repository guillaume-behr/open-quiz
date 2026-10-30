# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml). Node follows the
# major version CI builds with.
FROM node:24.22.2-trixie@sha256:8c761eca2bf7eec965f946cf47b8090143cb41f45f2f8699af0cc0298d2d2d19 AS build

WORKDIR /app

RUN npm install -g corepack && corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm build


FROM caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e

ARG VITE_API_URL=""
ENV API_ORIGIN=${VITE_API_URL}

RUN setcap -r /usr/bin/caddy \
    && addgroup -S openquiz \
    && adduser -S -D -H -G openquiz openquiz

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    && mkdir -p /config /data \
    && chown -R openquiz:openquiz /config /data

USER openquiz

EXPOSE 8080
