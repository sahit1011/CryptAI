"""S1 (intraday confirmation) signal primitives — pure functions, no I/O.

The strategy's shape (docs/plan-2026-08/orderflow-memo.md): environment → location →
CONFIRMATION → risk. These primitives implement the confirmation stage — the one part
of the Robbins Cup pipeline we lack — from data we already ingest: 1m klines carry
``taker_buy_volume``, so per-bar aggressor delta costs zero new bandwidth (cost law).

Everything here is deliberately pure and framework-free because it is imported by TWO
consumers: the live paper engine (src/strategy/s1_intraday.py) and the offline
backtest lab (backtest-lab/). The lab validates the exact code that ships — an edge
found offline in a reimplementation would be evidence about the reimplementation.

Honesty-law note: nothing in this module predicts. Absorption ("aggressive sellers hit
the level, price refuses to go lower — effort without result") and the dominance flip
are *descriptions of what already happened*; whether acting on them carries an edge is
exactly what the lab's A/B exists to measure. Ship nothing on conviction.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import List, Optional


@dataclass(frozen=True)
class S1Params:
    """Every threshold in one sweepable place. Defaults are PRIORS, not findings —
    the backtest lab sweeps them; treat any change here as a claim needing evidence."""

    swing_left: int = 3            # fractal confirmation bars left of a swing point
    swing_right: int = 3           # ...and right (a swing is only known this many bars later)
    confirm_window_bars: int = 30  # 1m bars after the band touch to find absorption+flip
    baseline_bars: int = 60        # trailing bars used to scale "heavy" delta/volume
    absorption_delta_frac: float = 0.6   # |aggressor delta| ≥ frac × baseline mean volume
    absorption_close_frac: float = 0.5   # close must land in the top frac of the bar's range
    flip_delta_frac: float = 0.3         # flip bar's with-trend delta ≥ frac × baseline mean vol
    participation_window: int = 5        # recent bars whose summed volume must clear the floor
    participation_floor: float = 1.0     # × the median same-width volume over the baseline
    stop_buffer_frac: float = 0.0005     # stop sits this fraction of price beyond the absorption low


@dataclass(frozen=True)
class ConfirmedEntry:
    """A confirmation event: where to enter, where the trade is wrong."""

    entry_index: int
    entry_price: float
    stop_price: float
    absorption_index: int
    direction: str  # "long" | "short"


def _f(candle: dict, key: str) -> Optional[float]:
    try:
        v = candle[key]
        return float(v) if v is not None else None
    except (KeyError, TypeError, ValueError):
        return None


def taker_delta(candle: dict) -> float:
    """Net aggressor volume for one bar: taker buys minus taker sells.

    taker_sell = volume - taker_buy, so delta = 2·taker_buy - volume. Positive means
    buyers crossed the spread harder than sellers. Returns 0.0 when the candle lacks
    the fields — a bar we cannot read must never fabricate aggression (honesty law).
    """
    vol, tb = _f(candle, "volume"), _f(candle, "taker_buy_volume")
    if vol is None or tb is None:
        return 0.0
    return 2.0 * tb - vol


def latest_swing(candles: List[dict], left: int = 3, right: int = 3) -> Optional[dict]:
    """Most recent CONFIRMED fractal swing high and low.

    Index i is a swing high when high[i] is the strict maximum of the window
    [i-left, i+right] (mirror for lows). Confirmation costs ``right`` bars of delay by
    construction — that is the no-lookahead guarantee: called with bars up to "now",
    it can only return swings that were already knowable at "now".

    Returns {"high", "high_index", "low", "low_index"} or None when either side has
    no confirmed swing in the data given.
    """
    n = len(candles)
    if n < left + right + 1:
        return None
    highs = [_f(c, "high") for c in candles]
    lows = [_f(c, "low") for c in candles]
    if any(h is None for h in highs) or any(lo is None for lo in lows):
        return None

    hi_idx = lo_idx = None
    for i in range(n - 1 - right, left - 1, -1):
        window_h = highs[i - left: i + right + 1]
        if hi_idx is None and highs[i] == max(window_h) and window_h.count(highs[i]) == 1:
            hi_idx = i
        window_l = lows[i - left: i + right + 1]
        if lo_idx is None and lows[i] == min(window_l) and window_l.count(lows[i]) == 1:
            lo_idx = i
        if hi_idx is not None and lo_idx is not None:
            break
    if hi_idx is None or lo_idx is None:
        return None
    return {"high": highs[hi_idx], "high_index": hi_idx, "low": lows[lo_idx], "low_index": lo_idx}


def discount_band(swing_low: float, swing_high: float, direction: str) -> tuple:
    """The deep-retracement entry band (0.705–0.886 of the impulse).

    Long: measured down from the swing high — (entry_edge, invalidation_edge) where
    entry_edge is the 0.705 level and invalidation_edge the 0.886. Price between them
    is "in discount"; a CLOSE beyond invalidation kills the setup (the caller checks —
    these functions describe geometry, they don't manage trades). Short is the mirror
    (premium band above). Raises ValueError on a degenerate or inverted impulse: a
    band from bad geometry would be a fabricated level.
    """
    if not (swing_high > swing_low):
        raise ValueError("impulse requires swing_high > swing_low")
    rng = swing_high - swing_low
    if direction == "long":
        return swing_high - 0.705 * rng, swing_high - 0.886 * rng
    if direction == "short":
        return swing_low + 0.705 * rng, swing_low + 0.886 * rng
    raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")


def _baseline_mean_volume(candles: List[dict], index: int, params: S1Params) -> float:
    start = max(0, index - params.baseline_bars)
    vols = [v for c in candles[start:index] if (v := _f(c, "volume")) is not None]
    return sum(vols) / len(vols) if vols else 0.0


def participation_ok(candles_1m: List[dict], index: int, params: S1Params) -> bool:
    """His hardest rule: no trade in a dead market.

    The recent ``participation_window`` bars' summed volume must be at least
    ``participation_floor`` × the median same-width sum across the trailing baseline.
    Fails CLOSED (False) on insufficient or unreadable data — an unmeasurable market
    is not a tradeable one.
    """
    w = params.participation_window
    if index + 1 < w:
        return False
    start = max(0, index + 1 - params.baseline_bars)
    vols = [_f(c, "volume") for c in candles_1m[start: index + 1]]
    if any(v is None for v in vols) or len(vols) < 2 * w:
        return False
    sums = [sum(vols[i: i + w]) for i in range(len(vols) - w + 1)]
    recent = sums[-1]
    base = median(sums[:-1])
    if base <= 0:
        return False
    return recent >= params.participation_floor * base


def confirm_entry(
    candles_1m: List[dict],
    touch_index: int,
    direction: str,
    params: S1Params,
    invalidation_price: Optional[float] = None,
) -> Optional[ConfirmedEntry]:
    """Absorption-then-dominance-flip scan after a band touch. None = never enter.

    Long grammar (short is the mirror):
      1. ABSORPTION — a bar with heavy sell aggression (delta ≤ -absorption_delta_frac
         × baseline mean volume) that still CLOSES in the top absorption_close_frac of
         its range: sellers spent volume and price refused to hold lower. The lowest
         low from the touch through this bar becomes the structural stop level.
      2. FLIP — a later bar whose delta is positive (≥ flip_delta_frac × baseline) AND
         whose close breaks above the absorption bar's high. Entry at that close —
         never at the level touch; the touch is where the CONTROL arm of the A/B
         enters, and the difference between the two is the whole experiment.

    Aborts (None) when: window exhausts, a bar CLOSES beyond invalidation_price, or
    participation fails at the would-be entry. All scanning uses bars ≤ the decision
    bar — no lookahead by construction.
    """
    if direction not in ("long", "short"):
        return None
    n = len(candles_1m)
    if not (0 <= touch_index < n):
        return None
    end = min(n, touch_index + 1 + params.confirm_window_bars)
    sign = 1.0 if direction == "long" else -1.0

    absorption_idx: Optional[int] = None
    extreme = None  # running stop-side extreme from the touch forward

    for i in range(touch_index, end):
        c = candles_1m[i]
        low, high, close = _f(c, "low"), _f(c, "high"), _f(c, "close")
        if low is None or high is None or close is None:
            return None

        edge = low if direction == "long" else high
        extreme = edge if extreme is None else (min(extreme, edge) if direction == "long" else max(extreme, edge))

        if invalidation_price is not None:
            if (direction == "long" and close < invalidation_price) or (
                direction == "short" and close > invalidation_price
            ):
                return None  # setup structurally dead — a fill here would fight the method

        scale = _baseline_mean_volume(candles_1m, i, params)
        if scale <= 0:
            continue
        delta = taker_delta(c)
        bar_range = high - low

        if absorption_idx is None:
            heavy_against = sign * delta <= -params.absorption_delta_frac * scale
            if heavy_against and bar_range > 0:
                pos = (close - low) / bar_range  # 1.0 = closed at the high
                held = pos >= params.absorption_close_frac if direction == "long" else (
                    1.0 - pos
                ) >= params.absorption_close_frac
                if held:
                    absorption_idx = i
            continue

        # flip search: strictly after the absorption bar
        with_trend = sign * delta >= params.flip_delta_frac * scale
        abs_bar = candles_1m[absorption_idx]
        broke = (
            close > _f(abs_bar, "high") if direction == "long" else close < _f(abs_bar, "low")
        )
        if with_trend and broke:
            if not participation_ok(candles_1m, i, params):
                return None  # confirmed shape in a dead market is still no trade
            buffer = params.stop_buffer_frac * close
            stop = extreme - buffer if direction == "long" else extreme + buffer
            return ConfirmedEntry(
                entry_index=i,
                entry_price=close,
                stop_price=stop,
                absorption_index=absorption_idx,
                direction=direction,
            )

    return None
