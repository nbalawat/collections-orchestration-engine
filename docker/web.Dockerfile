# syntax=docker/dockerfile:1.7
# Builds the Vite frontend, then ships it inside a Caddy image that also
# reverse-proxies /api and /ws to the backend container.

FROM node:22-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /web

COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY web/ ./
RUN pnpm build


FROM caddy:2.8-alpine AS runtime

COPY --from=builder /web/dist /srv
COPY docker/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
