"""API rate limiting — in-process sliding window, per-IP / per-user.

Dependency-free (no Redis round-trip on the hot path): each API process keeps a
sliding-window counter per caller key. Callers are keyed by the authenticated user
(Authorization header hash) when present, else the client IP (X-Forwarded-For aware,
first hop — set by the reverse proxy in production).

Budgets are per-minute and env-tunable:
  RATE_LIMIT_PER_MINUTE          — general REST budget      (default 240/min)
  RATE_LIMIT_WRITE_PER_MINUTE    — POST/DELETE budget       (default 60/min)
  WS_CONNECTIONS_PER_CLIENT      — concurrent sockets/caller (default 8)

This intentionally protects against abusive clients and brute force, not distributed
DDoS (that's the CDN/proxy layer's job).
"""
import hashlib
import os
import time
from collections import deque
from typing import Deque, Dict, Tuple


class SlidingWindowLimiter:
    """Sliding 60s window per key. allow() is O(evictions) amortized."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._last_gc = 0.0

    def allow(self, key: str) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        q = self._hits.setdefault(key, deque())
        cutoff = now - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            retry = int(q[0] + self.window - now) + 1
            return False, max(retry, 1)
        q.append(now)
        self._gc(now)
        return True, 0

    def _gc(self, now: float) -> None:
        """Drop idle keys periodically so the map can't grow unbounded."""
        if now - self._last_gc < 300:
            return
        self._last_gc = now
        cutoff = now - self.window
        stale = [k for k, q in self._hits.items() if not q or q[-1] < cutoff]
        for k in stale:
            del self._hits[k]


def client_key(headers, client_host: str) -> str:
    """Caller identity for limiting: auth token hash if present, else client IP."""
    auth = headers.get("authorization")
    if auth:
        return "tok:" + hashlib.sha256(auth.encode()).hexdigest()[:24]
    fwd = headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (client_host or "unknown")
    return "ip:" + ip


read_limiter = SlidingWindowLimiter(int(os.getenv("RATE_LIMIT_PER_MINUTE", "240")))
write_limiter = SlidingWindowLimiter(int(os.getenv("RATE_LIMIT_WRITE_PER_MINUTE", "60")))
WS_CONNECTIONS_PER_CLIENT = int(os.getenv("WS_CONNECTIONS_PER_CLIENT", "8"))
