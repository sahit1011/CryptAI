"""Global daily LLM request budget (R1.6) — requests are the currency, not dollars.

On all-:free OpenRouter routing every call is $0.00, so the dollar cost cap is
structurally inert; what actually kills a free deployment is the DAILY REQUEST CAP
(~50/day uncredited, ~1,000/day with the one-time $10 credit — verify live). Nothing
tracked it: a dead-primary rotation day multiplies every 40k-token prompt by the number
of attempts, and the first sign of exhaustion was sessions silently producing nothing.

Three pieces:
- `record_attempt()` — in-process, thread-safe, called at the EXACT point an HTTP
  request departs (the rotation loop and synthesis's client loop, both sync code run
  in executors — hence no Redis I/O here).
- `LlmRequestBudget` — a daemon task flushes the pending delta into a Redis daily
  counter (UTC key, 2-day TTL); readers get today's total.
- The capacity gate consults `exhausted()`: at ~80% of the live cap it refuses NEW
  scans (503, no row, no clock) and the tick loop's capacity path refunds running
  ones — with an ops log NAMING the cap, so exhaustion is a diagnosis, not a mystery.

Failure direction: Redis down/evicted degrades to undercounting and not blocking.
The budget is a protective rail — a rail's failure mode must never be a second outage
(the engine switch and model-key checks already fail closed on real outages).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

DEFAULT_DAILY_CAP = 800  # ~80% of the credited 1,000/day — verify the live cap (R1.6 DoD)

_lock = threading.Lock()
_pending = 0


def record_attempt(n: int = 1) -> None:
    """Count one outbound LLM request. Called from sync call sites; never does I/O."""
    global _pending
    with _lock:
        _pending += n


def drain_pending() -> int:
    """Take and reset the not-yet-flushed attempt count."""
    global _pending
    with _lock:
        taken, _pending = _pending, 0
    return taken


def day_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"llm:requests:{now.strftime('%Y-%m-%d')}"


def daily_cap() -> int:
    try:
        return int(os.getenv("LLM_DAILY_REQUEST_CAP", str(DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


class LlmRequestBudget:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def flush(self) -> int:
        """Move the in-process delta into today's Redis counter. Returns the delta."""
        delta = drain_pending()
        if not delta:
            return 0
        try:
            key = day_key()
            await self.redis.incrby(key, delta)
            await self.redis.expire(key, 2 * 24 * 3600)
        except Exception as e:
            # Undercount rather than lose the process to the rail. Put the delta back
            # so a transient Redis blip doesn't drop it entirely.
            record_attempt(delta)
            logger.warning(f"[llm-budget] flush failed ({e}); will retry")
            return 0
        return delta

    async def spent_today(self) -> int:
        try:
            raw = await self.redis.get(day_key())
            return int(raw) if raw else 0
        except Exception:
            return 0  # unknown = not blocking (see module docstring)

    async def exhausted(self) -> bool:
        spent = await self.spent_today()
        cap = daily_cap()
        if spent >= cap:
            logger.warning(
                f"[llm-budget] daily request cap reached ({spent}/{cap}, key {day_key()}) — "
                "new scans refuse and running scans refund until UTC midnight. Raise "
                "LLM_DAILY_REQUEST_CAP only after verifying the provider's real limit."
            )
            return True
        return False
