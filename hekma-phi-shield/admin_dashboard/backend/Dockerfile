# Multi-Stage Dockerfile for the PII Admin Dashboard API (pds-agent)
# Build context MUST be the repo root (needs the shared `api/` package).

# Admin portal (React/Vite). dist/ is gitignored, so it must be built here or
# /admin answers 503.
FROM node:20-bookworm-slim AS frontend

WORKDIR /ui

COPY admin_dashboard/frontend/package.json admin_dashboard/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY admin_dashboard/frontend/ ./
# Pass environment key into build stage (defaults to live dev secret)
ARG VITE_ADMIN_KEY=hekma_admin_live_1e2f3a4b
ENV VITE_ADMIN_KEY=$VITE_ADMIN_KEY
# VITE_API_URL is intentionally unset: the portal is served from this host and
# calls /api/v1/* on the same origin.
RUN npm run build && test -f dist/index.html

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Reuse the main service's requirements so the shared api.* modules
# (storage, crypto, policy engine) resolve identically in both images.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production
ENV SERVICE_PORT=8083

RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app

# Shared api/ package (services, storage, models) + the admin dashboard app itself.
COPY --chown=appuser:appuser api/ /app/api/
COPY --chown=appuser:appuser admin_dashboard/backend/ /app/admin_dashboard/backend/
COPY --from=frontend --chown=appuser:appuser /ui/dist /app/admin_dashboard/frontend/dist

# Fail the build rather than shipping an image whose /admin portal would 503.
RUN test -f /app/admin_dashboard/frontend/dist/index.html || { \
      echo 'ERROR: admin_dashboard/frontend/dist/index.html missing; the frontend build stage did not produce the portal.' >&2; \
      exit 1; \
    }

USER root

EXPOSE 8083

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8083/health || exit 1

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "admin_dashboard.backend.main:app", "-b", "0.0.0.0:8083", "--timeout", "60", "--graceful-timeout", "30"]
