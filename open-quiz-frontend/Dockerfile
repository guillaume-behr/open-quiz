# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml). Node follows the
# major version CI builds with.
FROM node:24.22.2-trixie@sha256:8c761eca2bf7eec965f946cf47b8090143cb41f45f2f8699af0cc0298d2d2d19 AS build

WORKDIR /app

# Node 24 bundles Corepack, which installs the pnpm version that package.json
# pins, and checks it against the hash given there.
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM caddy:2.11.9@sha256:e40b94d0a43b5ff69cb20568d73f10c70703df7b0ffc2298eb3d723cdc9d0bd1

RUN setcap -r /usr/bin/caddy \
    && addgroup -S -g 10001 openquiz \
    && adduser -S -D -H -u 10001 -G openquiz openquiz

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

# `caddy fmt` fails on a layout Caddy would warn about at every start.
RUN caddy fmt /etc/caddy/Caddyfile > /dev/null \
    && caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    && mkdir -p /config /data \
    && chown -R openquiz:openquiz /config /data

# Numeric, as the backend image: resolvable without the image's passwd.
USER 10001:10001

EXPOSE 8080
