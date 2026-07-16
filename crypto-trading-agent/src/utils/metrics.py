"""Prometheus metrics for the API — scraped from GET /metrics.

Deliberately small: request counts/latency by (method, path, status), rate-limit
rejections, and a live WS-connection gauge. Paths are normalized to the known route
set so junk URLs can't explode label cardinality. prometheus_client's default
registry also exports process metrics (CPU, RSS, fds) for free.
"""
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS = Counter(
    "cryptai_http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "cryptai_http_request_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
RATE_LIMITED = Counter(
    "cryptai_rate_limited_total",
    "Requests rejected by the rate limiter",
    ["method"],
)
WS_CONNECTIONS = Gauge(
    "cryptai_ws_connections",
    "Open WebSocket connections",
)

# Known route prefixes -> normalized label (avoids unbounded path cardinality).
_KNOWN_PATHS = (
    "/api/trades", "/api/setups", "/api/settings", "/api/exchange-keys",
    "/api/execute-setup", "/api/close-positions", "/api/ticker",
    "/health/live", "/health/ready", "/health", "/metrics", "/ws",
)


def normalize_path(path: str) -> str:
    for known in _KNOWN_PATHS:
        if path == known or path.startswith(known + "/"):
            return known
    return "other"


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
