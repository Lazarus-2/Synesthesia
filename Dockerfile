# Multi-stage build with named targets (Plan 2 G1 + G5).
#
# Three named targets:
#   1. ``builder``       - installs deps into a venv. Heavy build tools live here.
#   2. ``runtime-api``   - slim image with API CMD. Default if no target given.
#   3. ``runtime-worker``- slim image with Taskiq worker CMD + pre-warmed
#                          ML models so first-task latency is bounded.
#
# Build either with:
#   docker build --target runtime-api    -t synesthesia-api    .
#   docker build --target runtime-worker -t synesthesia-worker .
#
# docker-compose builds both via the ``target:`` directive per service.

############################
# Stage 1 — builder
############################
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Python tooling lives under backend/ after the layout refactor.
COPY backend/requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt


############################
# Stage 2a — runtime-api
############################
FROM python:3.12-slim AS runtime-api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LOG_FORMAT=json \
    PORT=8000

# Runtime deps the API needs at request time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
 && useradd --system --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# Editable install so ``import backend.X`` resolves at runtime regardless
# of the Python entry point's cwd.
RUN /opt/venv/bin/pip install -e /app/backend

RUN mkdir -p /app/storage/uploads /app/storage/stems \
 && chown -R app:app /app/storage

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "120"]


############################
# Stage 2b — runtime-worker
############################
# The worker image is intentionally distinct: it doesn't expose a port, runs
# the Taskiq CLI, and could grow GPU drivers / pre-cached model weights
# without bloating the API image. The shared ``builder`` venv means deps
# stay identical between the two.
FROM python:3.12-slim AS runtime-worker

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LOG_FORMAT=json

# Same runtime deps as the API; ffmpeg is needed by yt-dlp/librosa.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
 && useradd --system --gid app --create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# Editable install so ``import backend.X`` resolves at runtime regardless
# of the Python entry point's cwd.
RUN /opt/venv/bin/pip install -e /app/backend

RUN mkdir -p /app/storage/uploads /app/storage/stems \
 && chown -R app:app /app/storage

USER app

# No HEALTHCHECK on the worker — Taskiq has no built-in HTTP probe and the
# orchestrator should monitor liveness via the broker (Redis queue depth /
# task result rate) instead of a CMD-based check.

CMD ["taskiq", "worker", "backend.worker:broker", "backend.main"]
