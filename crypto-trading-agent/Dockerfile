# syntax=docker/dockerfile:1
#
# Backend image for the crypto-trading-agent (API + worker share this image).
#
# Build deps (gcc, build-essential) and the TA-Lib C library are required to
# compile the `ta-lib` Python wheel; we keep them in a single layer.
#
# Default CMD runs the FastAPI API via uvicorn. The worker (src/main.py) runs
# from the SAME image by overriding the command, e.g. in docker-compose:
#     command: python -m src.main
FROM python:3.12-slim AS base

# Don't write .pyc files, flush stdout/stderr immediately (good for container logs).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- System + build dependencies -------------------------------------------------
# build-essential / gcc:   compile native wheels (ta-lib, psycopg2 fallbacks)
# wget:                     fetch the TA-Lib C sources
# libpq-dev:                Postgres client headers
# curl:                     used by the container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        wget \
        curl \
        ca-certificates \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# --- TA-Lib C library ------------------------------------------------------------
# The `ta-lib==0.4.28` Python package is just bindings; it needs the C lib present.
RUN wget -q https://downloads.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz \
    && ldconfig

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
