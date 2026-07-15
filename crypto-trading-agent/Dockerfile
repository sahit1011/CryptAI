# syntax=docker/dockerfile:1
#
# Backend image for the crypto-trading-agent (API + daemon share this image).
#
# gcc/build-essential + libpq-dev cover native wheels (psycopg2, etc.). NOTE: the
# TA-Lib C library is intentionally NOT built — `ta-lib` was dropped from
# requirements (nothing imports `talib`; analysis uses pure-Python `pandas_ta`).
#
# Default CMD runs the FastAPI API via uvicorn. The multi-user daemon runs from the
# SAME image by overriding the command, e.g. in docker-compose:
#     command: python -m src.multi_user_daemon
FROM python:3.12-slim AS base

# Don't write .pyc files, flush stdout/stderr immediately (good for container logs).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- System + build dependencies -------------------------------------------------
# build-essential / gcc:   compile native wheels (psycopg2 fallbacks, etc.)
# libpq-dev:                Postgres client headers
# curl:                     used by the container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        curl \
        ca-certificates \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python dependencies ---------------------------------------------------------
# Copy requirements first so dependency layer is cached across source changes.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# --- Application source -----------------------------------------------------------
COPY . .

# --- Non-root user ----------------------------------------------------------------
# Create an unprivileged user and hand over ownership of the app dir.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Healthcheck hits the API's health endpoint. (Worker service overrides the
# command and can disable/override this healthcheck in compose.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: run the API. Bind 0.0.0.0 so the port is reachable from other
# containers / the host (auth is enforced in-app via API_AUTH_TOKEN).
# Worker entrypoint (override in compose): python -m src.main
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
