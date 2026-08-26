"""S1 intraday confirmation strategy — paper-only scaffolding, default-off.

Composes the s1_signals contract in the memo's ordering (environment → location →
confirmation → risk, docs/plan-2026-08/orderflow-memo.md): a confirmed 1h impulse
gives the swing, its 0.705–0.886 retracement gives the discount band, and an entry
exists only when a 1m touch of that band is followed by enough realized
participation AND an absorption-then-dominance-flip. Entering on the CONFIRMATION
rather than on the level touch is the entire point of S1 — the one element the
memo found absent from today's pipeline.

Design constraints, in order of importance:

- **Pure, no I/O.** The strategy is a function of the candles it is handed, so it
  is hermetically testable and structurally cannot violate the cost law by
  fetching anything itself. Whoever calls it owns the data and therefore the
  bandwidth accounting.
- **Never raises.** Short, missing, or malformed data answers "no entry" (None).
  A signal function has no business taking down a session worker, and on a paper
  A/B a skipped entry is always the safe failure.
- **Lazy contract import.** `src/strategy/s1_signals.py` is owned by a parallel
  workstream; it is resolved per-call via importlib so this module — and the API
  server that transitively imports the strategy package — stays importable before
  that file lands. Missing contract == "no entry", logged loudly once per call.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:  # types only — never a runtime dependency on the contract file
    from src.strategy.s1_signals import ConfirmedEntry, S1Params

#: A confirmed fractal swing needs left + right + 1 bars at latest_swing's default
#: width (3/3). Fewer 1h candles can never yield a swing, so evaluate() answers
#: no-entry without calling into the contract at all.
_MIN_1H_CANDLES = 7
#: Below this there is no room for touch → absorption → flip on the 1m series.
_MIN_1M_CANDLES = 5


def _signals():
    """The s1_signals contract module, or None while it has not landed yet.

    importlib.import_module (rather than a `from` import) so sys.modules is the
    single source of truth — tests can inject a fake contract deterministically.
    """
    try:
        return importlib.import_module("src.strategy.s1_signals")
    except ImportError:
        return None


class S1IntradayStrategy:
    """Stateless composer of the s1_signals stages. Safe to share across calls."""

    def evaluate(
        self,
        candles_1m: List[Dict[str, Any]],
        candles_1h: List[Dict[str, Any]],
        direction_bias: Optional[str],
        params: Optional["S1Params"] = None,
    ) -> Optional["ConfirmedEntry"]:
        """One S1 pass: swing → discount band → band touch → participation → confirmation.

        `direction_bias` ("long" | "short") comes from the caller's environment
        stage — S1 never invents a direction (regime→direction is empirically
        refuted; honesty law). Returns the contract's ConfirmedEntry, or None for
        "no trade", which is also the answer to every malformed input.
        """
        sig = _signals()
        if sig is None:
            # Loud, not fatal: a deployment that enabled S1 without the signal
            # module is misassembled, but the session worker must keep running.
            logger.warning("s1_signals contract module is unavailable; S1 evaluates to no-entry")
            return None

        if not isinstance(candles_1m, list) or not isinstance(candles_1h, list):
            return None
        if len(candles_1h) < _MIN_1H_CANDLES or len(candles_1m) < _MIN_1M_CANDLES:
            return None
        if not isinstance(direction_bias, str):
            return None
        direction = direction_bias.strip().lower()
        if direction not in ("long", "short"):
            return None

        try:
            p = params if params is not None else sig.S1Params()
            swing = sig.latest_swing(candles_1h)
            if swing is None:
                return None
            entry_edge, invalidation_edge = sig.discount_band(
                swing["low"], swing["high"], direction
            )
            touch_index = _band_touch_index(
                candles_1m, entry_edge, invalidation_edge, direction
            )
            if touch_index is None:
                return None
            if not sig.participation_ok(candles_1m, touch_index, p):
                return None
            return sig.confirm_entry(candles_1m, touch_index, direction, p)
        except Exception as e:
            # Malformed candles (missing keys, junk types) land here. "No entry"
            # is the safe answer, but the cause is logged so bad data upstream is
            # visible rather than silently swallowed forever.
            logger.warning(f"S1 evaluate degraded to no-entry on bad input: {e}")
            return None


def _band_touch_index(
    candles_1m: List[Dict[str, Any]],
    entry_edge: float,
    invalidation_edge: float,
    direction: str,
) -> Optional[int]:
    """Index of the most recent 1m candle that touched the discount band, or None.

    Scanned newest-first so an invalidating CLOSE beyond the band's far edge is
    seen before any older touch — once price has closed through 0.886 the setup
    is dead (memo: "close beyond 0.886 invalidates") and no earlier touch may be
    resurrected. For a long the band sits below price (touch = low reaches the
    entry edge, invalidation = close below the far edge); a short mirrors it.
    """
    entry_edge = float(entry_edge)
    invalidation_edge = float(invalidation_edge)
    for i in range(len(candles_1m) - 1, -1, -1):
        candle = candles_1m[i]
        low = float(candle["low"])
        high = float(candle["high"])
        close = float(candle["close"])
        if direction == "long":
            if close < invalidation_edge:
                return None
            if low <= entry_edge:
                return i
        else:
            if close > invalidation_edge:
                return None
            if high >= entry_edge:
                return i
    return None
