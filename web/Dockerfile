# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Public defaults. Overridable via --build-arg for self-hosted environments
# (e.g. private Docker registry, China-only Alpine/npm mirrors).
#
# Examples:
#   docker build --build-arg BASE_REGISTRY=harbor.example.com/base ...
#   docker build --build-arg ALPINE_MIRROR=mirrors.aliyun.com ...
#   docker build --build-arg NPM_REGISTRY=https://registry.npmmirror.com ...
# ---------------------------------------------------------------------------
ARG BASE_REGISTRY=docker.io/library
ARG ALPINE_MIRROR=dl-cdn.alpinelinux.org
ARG NPM_REGISTRY=https://registry.npmjs.org/

FROM ${BASE_REGISTRY}/node:20-alpine AS deps
ARG ALPINE_MIRROR
ARG NPM_REGISTRY
WORKDIR /app

RUN sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache libc6-compat

# Harden npm against transient registry errors (ECONNRESET) in CI / Docker builds
ENV NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_MAXSOCKETS=5

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm config set registry "${NPM_REGISTRY}" \
    && npm ci

FROM ${BASE_REGISTRY}/node:20-alpine AS builder
ARG ALPINE_MIRROR
WORKDIR /app

RUN sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache libc6-compat

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV APP_ENV=production \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM ${BASE_REGISTRY}/node:20-alpine AS runner
ARG ALPINE_MIRROR
WORKDIR /app

ENV NODE_ENV=production \
    APP_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    TZ=UTC \
    PORT=3000

RUN sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache libc6-compat tzdata \
    && cp /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
