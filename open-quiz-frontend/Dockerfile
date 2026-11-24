# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml). Node follows the
# major version CI builds with.
FROM node:24.22.3-trixie@sha256:6e5d4c38403930b420404f190be8563396dca2bd156a6cb4722707b0efcf6fc1 AS build

WORKDIR /app

# Node 24 bundles Corepack, which installs the pnpm version that package.json
# pins, and checks it against the hash given there.
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b

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
