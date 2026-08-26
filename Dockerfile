# syntax=docker/dockerfile:1
#
# Combined production image: Python backend (API + embedded daemon) + the Rust signal
# engine binary, built from the REPO ROOT so both source trees are in context.
#
# Why one image instead of two services: Render's free tier allows only web services
# (no background workers) and meters ~750 instance-hours/month across ALL free services,
# so a second always-on service would both be disallowed and risk suspending the backend.
# The signal engine therefore rides along as a child process of the API — the same
# pattern the project already uses for the daemon via RUN_DAEMON_IN_API=true. It keeps
# internal (non-public) Redis access, which a separately-hosted engine would lose.
#
# crypto-trading-agent/Dockerfile is kept as-is for docker-compose and standalone builds.

# ---- stage 1: build the Rust signal engine ---------------------------------------
FROM rust:1.97-slim-bookworm AS signal-builder
WORKDIR /engine
# native-tls (reqwest / tokio-tungstenite) needs OpenSSL headers at build time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends pkg-config libssl-dev \
 && rm -rf /var/lib/apt/lists/*
COPY signal-engine/rust-toolchain.toml signal-engine/Cargo.toml signal-engine/Cargo.lock ./
COPY signal-engine/src ./src
# Only the service binary; oracle/backtest are dev tooling.
RUN cargo build --release --bin signal-engine

# ---- stage 2: the Python backend (unchanged behaviour) ---------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential/gcc: native wheels · libpq-dev: Postgres headers · curl: healthcheck
# libssl3: runtime for the Rust binary's native-tls
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        curl \
        ca-certificates \
        libpq-dev \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer first so it caches across source changes.
COPY crypto-trading-agent/requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Application source (the backend tree becomes /app, exactly as before).
COPY crypto-trading-agent/ .

# The signal engine binary, spawned by the API when RUN_SIGNAL_ENGINE_IN_API=true.
COPY --from=signal-builder /engine/target/release/signal-engine /usr/local/bin/signal-engine

RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
