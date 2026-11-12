# Base images are pinned by version and digest so a rebuild is reproducible;
# Dependabot proposes the updates (.github/dependabot.yml). Node follows the
# major version CI builds with.
FROM node:24.22.2-trixie@sha256:5c6e2e57d7dd6652ce6f087ba0328312059d7c77f93baa8751865dbf103f1acb AS build

WORKDIR /app

# Node 24 bundles Corepack, which installs the pnpm version that package.json
# pins, and checks it against the hash given there.
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build


FROM caddy:2.11.8@sha256:4fcafa98afd1c2e642e353e3c5cf9ddbe892fcee14bc990e7ba2c5b78e51f9cf

RUN setcap -r /usr/bin/caddy \
    && addgroup -S openquiz \
    && adduser -S -D -H -G openquiz openquiz

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

# `caddy fmt` fails on a layout Caddy would warn about at every start.
RUN caddy fmt /etc/caddy/Caddyfile > /dev/null \
    && caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    && mkdir -p /config /data \
    && chown -R openquiz:openquiz /config /data

USER openquiz

EXPOSE 8080
