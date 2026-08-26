"""Read market pulses published by the Rust signal engine.

This is the per-user plane's ONLY door into the shared plane. It enforces two of the
isolation invariants from docs/MULTI_TENANCY.md at the boundary, so no caller has to
remember them:

  - **Invariant 2, fail-closed staleness.** A pulse older than `max_age_ms` raises
    rather than being returned. The shared plane is a single point of failure for every
    tenant; trading on its stale output is worse than not trading.
  - **Schema compatibility.** An unrecognised major version raises rather than being
    best-effort parsed into a shape this code does not understand.

Reads only. Nothing here computes market facts — that would defeat the point of paying
for the analysis once.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

# Must match signal_engine::pulse::SCHEMA_VERSION.
SCHEMA_VERSION = 1

# Default staleness budget. Deliberately tight: a signal engine that has stopped
# publishing looks identical to a calm market unless something checks the clock.
DEFAULT_MAX_AGE_MS = 15_000

# The global pulse aggregates one engine tick across all symbols. Its staleness
# budget is looser than a trade gate's: it drives a status badge, and the engine
# publishes every ~5s, so a minute of silence is worth showing as "unknown"
# rather than flapping the badge on one slow tick.
GLOBAL_MAX_AGE_MS = 60_000

KEY_PREFIX = "market:pulse:"
GLOBAL_KEY = "market:pulse:global"


class PulseUnavailable(RuntimeError):
    """Base: no usable pulse. Callers should refuse to trade, not fall back."""


class PulseMissing(PulseUnavailable):
    """No pulse published for this symbol."""


class PulseStale(PulseUnavailable):
    """The pulse exists but its market data is too old to act on."""


class PulseIncompatible(PulseUnavailable):
    """The pulse was published under a schema version this code cannot read."""


@dataclass(frozen=True)
class Pulse:
    """One symbol's market pulse. Mirrors the Rust contract exactly.

    Note what is absent: no entry, stop, target, or direction. The shared plane emits
    facts and scores; the trade decision is synthesised per-user. If a field like that
    ever appears here, the shared/per-user boundary has been broken.
    """

    v: int
    symbol: str
    ts: int
    feed_ts: int
    regime: str
    tradability: int
    vetoes: List[str]
    factors: Dict[str, float]
    structure: Dict[str, Any]
    context: Dict[str, float]
    reference_price: float
    # Which venue's candles produced this pulse. Defaults to "binance" for pulses
    # published before the fallback existed (additive-optional field, so no schema
    # bump was needed). NEVER guess this per-symbol: it is a provenance label that
    # the calibration ledger stores and later draws conclusions from.
    venue: str = "binance"
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pulse":
        return cls(
            v=int(data["v"]),
            symbol=str(data["symbol"]),
            ts=int(data["ts"]),
            feed_ts=int(data["feed_ts"]),
            regime=str(data["regime"]),
            tradability=int(data["tradability"]),
            vetoes=list(data.get("vetoes") or []),
            factors=dict(data.get("factors") or {}),
            structure=dict(data.get("structure") or {}),
            context=dict(data.get("context") or {}),
            reference_price=float(data.get("reference_price") or 0.0),
            venue=str(data.get("venue") or "binance"),
            raw=data,
        )

    def feed_age_ms(self, now_ms: Optional[int] = None) -> int:
        """Age of the underlying market data. Never negative — our clock and the
        exchange's are different clocks, and a few ms of skew is routine."""
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return max(0, now - self.feed_ts)

    def is_stale(self, max_age_ms: int = DEFAULT_MAX_AGE_MS, now_ms: Optional[int] = None) -> bool:
        return self.feed_age_ms(now_ms) > max_age_ms

    @property
    def is_vetoed(self) -> bool:
        return bool(self.vetoes)

    @property
    def is_tradable(self) -> bool:
        """A veto always means zero, but check both rather than trusting one field."""
        return not self.is_vetoed and self.tradability > 0


class PulseClient:
    """Async reader for the shared signal plane.

    Takes an existing redis.asyncio client rather than building one, so it shares the
    engine's connection pool and its outage handling.
    """

    def __init__(self, redis_client, max_age_ms: int = DEFAULT_MAX_AGE_MS):
        self.redis = redis_client
        self.max_age_ms = max_age_ms

    @staticmethod
    def key_for(symbol: str) -> str:
        return f"{KEY_PREFIX}{symbol.upper()}"

    async def get(self, symbol: str, now_ms: Optional[int] = None) -> Pulse:
        """Fetch a fresh, compatible pulse or raise.

        Raising rather than returning None is deliberate: a caller that forgets to check
        a None gets an unhandled exception in development, whereas one that forgets to
        check a falsy return trades on nothing. Use `get_or_none` where absence is an
        expected, handled case.
        """
        key = self.key_for(symbol)
        try:
            raw = await self.redis.get(key)
        except Exception as e:
            raise PulseMissing(f"redis read failed for {key}: {e}") from e

        if not raw:
            raise PulseMissing(f"no pulse published at {key}")

        try:
            data = json.loads(raw)
            pulse = Pulse.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise PulseIncompatible(f"malformed pulse at {key}: {e}") from e

        if pulse.v != SCHEMA_VERSION:
            raise PulseIncompatible(
                f"pulse at {key} is schema v{pulse.v}, this client reads v{SCHEMA_VERSION}"
            )

        age = pulse.feed_age_ms(now_ms)
        if age > self.max_age_ms:
            raise PulseStale(
                f"pulse for {symbol} is {age}ms old (limit {self.max_age_ms}ms) — "
                f"refusing to act on stale market data"
            )

        return pulse

    async def get_or_none(self, symbol: str, now_ms: Optional[int] = None) -> Optional[Pulse]:
        """Same, but returns None instead of raising. Logs why, so a silently absent
        signal is still visible in the logs."""
        try:
            return await self.get(symbol, now_ms=now_ms)
        except PulseUnavailable as e:
            logger.debug(f"pulse unavailable for {symbol}: {e}")
            return None

    async def get_many(
        self, symbols: List[str], now_ms: Optional[int] = None
    ) -> Dict[str, Pulse]:
        """Fetch several symbols, skipping any that are missing, stale, or incompatible.

        Partial results are correct here: one dead symbol must not blind a session to
        every other one.
        """
        out: Dict[str, Pulse] = {}
        for symbol in symbols:
            pulse = await self.get_or_none(symbol, now_ms=now_ms)
            if pulse is not None:
                out[symbol.upper()] = pulse
        return out


@dataclass(frozen=True)
class GlobalPulse:
    """The whole plane's health in one object. Mirrors signal_engine::pulse::GlobalPulse.

    Note what is absent, deliberately: any forward statement. `tradability_max` and
    `tradability_median` describe THIS tick. "Conditions are active right now" is a
    measurement; "the next hour will be hot" is a forecast this system does not make.
    """

    v: int
    ts: int
    symbols_scored: int
    symbols_vetoed: int
    tradability_max: int
    tradability_median: int
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalPulse":
        return cls(
            v=int(data["v"]),
            ts=int(data["ts"]),
            symbols_scored=int(data.get("symbols_scored") or 0),
            symbols_vetoed=int(data.get("symbols_vetoed") or 0),
            tradability_max=int(data.get("tradability_max") or 0),
            tradability_median=int(data.get("tradability_median") or 0),
            raw=data,
        )

    def age_ms(self, now_ms: Optional[int] = None) -> int:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return max(0, now - self.ts)

    def is_stale(self, max_age_ms: int = GLOBAL_MAX_AGE_MS,
                 now_ms: Optional[int] = None) -> bool:
        return self.age_ms(now_ms) > max_age_ms


async def read_global(redis_client, now_ms: Optional[int] = None
                      ) -> Optional[GlobalPulse]:
    """The global pulse, or None when it is missing/unreadable/incompatible.

    Returns None rather than raising: unlike the per-symbol path (where a missing
    pulse must block a trade), this feeds a status badge. The CALLER decides how to
    render "unknown" — and must render it as unknown, never as calm.
    """
    try:
        raw = await redis_client.get(GLOBAL_KEY)
    except Exception as e:
        logger.warning(f"[pulse] global read failed: {e}")
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if int(data.get("v", 0)) != SCHEMA_VERSION:
            logger.warning(f"[pulse] global schema v{data.get('v')} != v{SCHEMA_VERSION}")
            return None
        return GlobalPulse.from_dict(data)
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"[pulse] global pulse unparseable: {e}")
        return None
