# The web image of deploy/compose.yaml: the standalone Next.js server.
# Build context: the repository root (the pnpm workspace and its lock file live there).
ARG NODE_IMAGE=node:24-alpine

FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json web/
RUN pnpm install --frozen-lockfile --filter @apparatica/web
COPY web web
RUN pnpm -C web build

FROM ${NODE_IMAGE}
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /src/web/.next/standalone ./
COPY --from=build --chown=node:node /src/web/.next/static ./web/.next/static
USER node
EXPOSE 3000
CMD ["node", "web/server.js"]
