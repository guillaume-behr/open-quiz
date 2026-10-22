FROM node:latest AS build

WORKDIR /app

RUN npm install -g corepack && corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN pnpm build


FROM caddy:latest

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
