# CryptAI shared signal plane — the always-on Rust engine that publishes market:pulse:*.
#
# Deploys as its OWN service (a Render Background Worker with root directory
# `signal-engine`), separate from the Python backend blueprint — the same way the
# frontend deploys separately. It needs only REDIS_URL (the managed cryptai-redis) to
# publish pulses the daemon's PulseClient reads once SIGNAL_PLANE_ENABLED=true.
#
# No local Docker was available to build this image; the build STEP is verified
# (`cargo build --release --bin signal-engine` compiles clean). Adjust the base tag if
# the pinned toolchain image is unavailable — rust-toolchain.toml pins 1.97.1 regardless.

# ---- build ---------------------------------------------------------------------
FROM rust:1.97-slim-bookworm AS builder
WORKDIR /app

# native-tls (reqwest, tokio-tungstenite) needs OpenSSL headers at build time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends pkg-config libssl-dev \
 && rm -rf /var/lib/apt/lists/*

COPY rust-toolchain.toml Cargo.toml Cargo.lock ./
COPY src ./src
# Only the service binary — the oracle/backtest bins are dev tooling, not the runtime.
RUN cargo build --release --bin signal-engine

# ---- runtime -------------------------------------------------------------------
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libssl3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home appuser

COPY --from=builder /app/target/release/signal-engine /usr/local/bin/signal-engine

USER appuser
ENV RUST_LOG=info
# SYMBOLS must be a SUPERSET of the daemon's PLATFORM_SYMBOLS, or a session's universe
# includes a symbol the engine never scored (its pulse gate then no-ops for that symbol).
ENV SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
ENTRYPOINT ["signal-engine"]
