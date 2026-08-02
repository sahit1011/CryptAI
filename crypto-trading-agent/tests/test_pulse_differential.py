"""Differential tests: the Rust signal engine must agree with a numpy oracle.

This is the check that makes the Rust decision defensible. Rust is the implementation;
this file is an independent reference written against the same definitions. Neither is
trusted alone — a bug has to be made twice, in two languages, to slip through.

Both sides run on IDENTICAL inputs: the fixtures are generated here and handed to the
Rust binary as JSON, so there is no chance of the two disagreeing because they were fed
different numbers.

Skips cleanly when the binary is absent, same as the Redis-dependent tests. To run:

    cd signal-engine && cargo build --release --bin oracle
"""
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

ORACLE = (
    Path(__file__).resolve().parents[2] / "signal-engine" / "target" / "release" / "oracle"
)

EMA_PERIOD = 21
ATR_PERIOD = 14
ER_PERIOD = 20

# Relative tolerance. The two implementations do the same sequential arithmetic, but
# numpy uses pairwise summation for means, so agreement is near-exact rather than
# bit-identical. Anything looser than this would hide a real algorithmic divergence.
REL_TOL = 1e-9
ABS_TOL = 1e-12

pytestmark = pytest.mark.skipif(
    not ORACLE.exists(),
    reason=f"signal-engine oracle not built at {ORACLE} — "
    f"run `cd signal-engine && cargo build --release --bin oracle`",
)


# --------------------------------------------------------------------------
# Deterministic fixture generation. No RNG: an LCG with fixed constants so the
# series is identical on every machine and in every language.
# --------------------------------------------------------------------------

def _lcg(n: int, seed: int = 12345):
    """Reproducible pseudo-random sequence in [0, 1)."""
    out, x = [], seed
    for _ in range(n):
        x = (1103515245 * x + 12345) % (2**31)
        out.append(x / (2**31))
    return out


def _bars_from_closes(closes, spread=1.0):
    return [
        {
            "open": c,
            "high": c + spread / 2,
            "low": c - spread / 2,
            "close": c,
            "volume": 1.0,
            "close_time": i * 60_000,
        }
        for i, c in enumerate(closes)
    ]


def _line(a, b, n):
    step = (b - a) / (n - 1)
    return [a + step * i for i in range(n)]


def fixtures():
    """Each case stresses a different corner of the math."""
    trend_up = _line(100.0, 180.0, 300)
    trend_down = _line(180.0, 100.0, 300)
    chop = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(300)]
    noisy = [100.0 + (r - 0.5) * 20.0 for r in _lcg(300)]
    # A gapping series: TR must pick up the gap, not just the bar range.
    gappy = []
    price = 100.0
    for i in range(300):
        price += 5.0 if i % 20 == 0 else 0.2
        gappy.append(price)

    return [
        ("trend_up", trend_up, trend_down),
        ("trend_down", trend_down, trend_up),
        ("chop", chop, trend_up),
        ("noisy", noisy, trend_up),
        ("gappy", gappy, trend_up),
        ("flat", [100.0] * 300, trend_up),
    ]


# --------------------------------------------------------------------------
# The numpy oracle. Independent implementations of the same definitions.
# --------------------------------------------------------------------------

def ref_sma(closes, period):
    if period == 0 or len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def ref_ema(values, period):
    """Seeded with the SMA of the first `period` values, then standard recursion."""
    if period == 0 or len(values) < period:
        return None
    acc = float(np.mean(values[:period]))
    k = 2.0 / (period + 1.0)
    for v in values[period:]:
        acc = v * k + acc * (1.0 - k)
    return acc


def ref_atr(bars, period):
    """Wilder's smoothing over true ranges. Needs period + 1 bars."""
    if period == 0 or len(bars) <= period:
        return None
    trs = []
    for prev, cur in zip(bars, bars[1:]):
        pc = prev["close"]
        trs.append(
            max(
                cur["high"] - cur["low"],
                abs(cur["high"] - pc),
                abs(cur["low"] - pc),
            )
        )
    if len(trs) < period:
        return None
    acc = float(np.mean(trs[:period]))
    for tr in trs[period:]:
        acc = (acc * (period - 1) + tr) / period
    return acc


def ref_efficiency_ratio(closes, period):
    if period == 0 or len(closes) < period + 1:
        return None
    window = np.asarray(closes[-(period + 1):], dtype=float)
    net = abs(float(window[-1] - window[0]))
    path = float(np.abs(np.diff(window)).sum())
    if path <= np.finfo(float).eps:
        return 0.0
    return min(max(net / path, 0.0), 1.0)


def ref_percentile_rank(sample, value):
    arr = np.asarray(sample, dtype=float)
    if arr.size == 0 or math.isnan(value):
        return None
    return float(np.count_nonzero(arr < value) / arr.size)


def ref_returns(prices):
    out = []
    for prev, cur in zip(prices, prices[1:]):
        if prev > 0:
            out.append((cur - prev) / prev)
    return out


def ref_correlation(a, b):
    if len(a) < 2 or len(a) != len(b):
        return None
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    dx, dy = x - x.mean(), y - y.mean()
    denom = math.sqrt(float((dx * dx).sum()) * float((dy * dy).sum()))
    if denom <= np.finfo(float).eps:
        return None
    return min(max(float((dx * dy).sum() / denom), -1.0), 1.0)


# --------------------------------------------------------------------------

def run_oracle(name, bars, reference_closes):
    payload = {
        "name": name,
        "bars": bars,
        "ema_period": EMA_PERIOD,
        "atr_period": ATR_PERIOD,
        "er_period": ER_PERIOD,
        "reference_closes": reference_closes,
    }
    proc = subprocess.run(
        [str(ORACLE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"oracle failed: {proc.stderr}"
    return json.loads(proc.stdout)


def assert_agrees(field, rust_value, python_value):
    if python_value is None or rust_value is None:
        assert rust_value == python_value, (
            f"{field}: one side produced a value and the other did not "
            f"(rust={rust_value}, python={python_value})"
        )
        return
    assert math.isclose(rust_value, python_value, rel_tol=REL_TOL, abs_tol=ABS_TOL), (
        f"{field} diverged: rust={rust_value!r} python={python_value!r} "
        f"(delta={abs(rust_value - python_value):.3e})"
    )


@pytest.mark.parametrize("name,closes,reference", fixtures(), ids=lambda v: v if isinstance(v, str) else "")
def test_rust_matches_numpy_oracle(name, closes, reference):
    """Every indicator must agree with the independent numpy implementation."""
    bars = _bars_from_closes(closes)
    got = run_oracle(name, bars, reference)

    assert got["bar_count"] == len(bars)
    assert_agrees("sma", got["sma"], ref_sma(closes, EMA_PERIOD))
    assert_agrees("ema", got["ema"], ref_ema(closes, EMA_PERIOD))
    assert_agrees("atr", got["atr"], ref_atr(bars, ATR_PERIOD))
    assert_agrees(
        "efficiency_ratio",
        got["efficiency_ratio"],
        ref_efficiency_ratio(closes, ER_PERIOD),
    )
    assert_agrees(
        "percentile_of_last_close",
        got["percentile_of_last_close"],
        ref_percentile_rank(closes, closes[-1]),
    )

    sym_r, ref_r = ref_returns(closes), ref_returns(reference)
    n = min(len(sym_r), len(ref_r))
    expected_corr = ref_correlation(sym_r[-n:], ref_r[-n:]) if n >= 2 else None
    assert_agrees("correlation", got["correlation_with_reference"], expected_corr)

    assert got["returns_count"] == len(sym_r)
    assert_agrees("returns_sum", got["returns_sum"], float(np.sum(sym_r)))


def test_insufficient_history_agrees_on_none():
    """Both sides must refuse, not guess, when there is too little data.

    A silent fallback to a short-window value is the failure mode that matters here:
    it produces a confident number from three candles, and nothing downstream can tell
    it apart from a real one.
    """
    closes = _line(100.0, 105.0, 5)
    got = run_oracle("too_short", _bars_from_closes(closes), [])

    assert got["ema"] is None, "Rust computed an EMA from 5 bars at period 21"
    assert got["atr"] is None, "Rust computed an ATR from 5 bars at period 14"
    assert got["efficiency_ratio"] is None
    assert ref_ema(closes, EMA_PERIOD) is None
    assert ref_atr(_bars_from_closes(closes), ATR_PERIOD) is None


def test_flat_market_is_not_a_perfect_trend():
    """Zero path length is undefined, not efficient — both sides must say 0.0.

    Reporting 1.0 here would score a dead market as the cleanest possible trend, which
    is exactly the kind of plausible-looking wrong answer the differential setup exists
    to catch.
    """
    closes = [100.0] * 300
    got = run_oracle("flat", _bars_from_closes(closes, spread=0.0), [])
    assert got["efficiency_ratio"] == 0.0
    assert ref_efficiency_ratio(closes, ER_PERIOD) == 0.0
