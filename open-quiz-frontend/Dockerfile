FROM node:26.5.1-alpine3.23@sha256:2a633e101381371ba148c7c212bf447c00cd267d814b708a9fe52c4984204729 AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm build


FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

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
