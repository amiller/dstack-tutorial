# Reproducible build for TEE Oracle
# See README.md "Critical Thinking About TEE Apps" for why this matters

ARG SOURCE_DATE_EPOCH=0

# Pin base image by digest, not tag
FROM node:22-slim@sha256:773413f36941ce1e4baf74b4a6110c03dcc4f968daffc389d4caef3f01412d2a

ARG SOURCE_DATE_EPOCH
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV npm_config_cache=/tmp/npm-cache

WORKDIR /app

# Copy lockfile first for layer caching
COPY --chmod=644 package.json package-lock.json ./

# Install with ci (uses lockfile exactly) and clean all caches
# NODE_COMPILE_CACHE creates non-deterministic bytecode - must be disabled or cleaned
RUN npm ci --omit=dev --ignore-scripts && \
    rm -rf /tmp/npm-cache /tmp/node-compile-cache && \
    find /app -exec touch -d "@${SOURCE_DATE_EPOCH}" {} + 2>/dev/null || true

COPY --chmod=644 app.mjs ./
RUN touch -d "@${SOURCE_DATE_EPOCH}" /app/app.mjs

CMD ["node", "app.mjs"]
