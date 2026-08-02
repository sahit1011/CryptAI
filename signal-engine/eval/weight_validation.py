#!/usr/bin/env python3
"""Are IC-derived weights better than the hand-picked prior, OUT OF SAMPLE?

Factor analysis showed the shipped weights are close to backwards relative to measured
information content: liquidity_window carries the highest residual IC and the lowest
weight, trend_alignment the reverse. The obvious move is to re-weight by IC.

The obvious move is also exactly what the walk-forward already caught once. Weights fitted
on the same data that motivated them will always look better on it. So:

  - weights are derived ONLY from development symbols
  - they are scored ONLY on held-out symbols never used in the derivation
  - the shipped prior is the baseline on the same held-out data

The tradability score is a linear combination of published factors, so both weightings can
be recomputed in Python from one backtest run. No Rust changes, and no chance of the two
arms differing by anything except the weights.

Usage:  python eval/weight_validation.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import BACKTEST_BIN, fetch_klines, ic_tstat, spearman  # noqa: E402

DEV_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
HELDOUT_SYMBOLS = ["BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT"]

FACTORS = ["trend_alignment", "volatility_band", "efficiency_ratio", "liquidity_window"]

# What the engine ships today, renormalised over the four factors that vary in a kline
# backtest (positioning and book_quality are constant here, so they shift every score by
# the same amount and cannot affect a rank correlation).
SHIPPED = {
    "trend_alignment": 0.25,
    "volatility_band": 0.15,
    "efficiency_ratio": 0.25,
    "liquidity_window": 0.10,
}

BARS = 8000
WARMUP = 300
HORIZONS = [4, 12]


def run_engine(symbol: str, bars: list[dict]) -> list[dict]:
    payload = {"symbol": symbol, "bars": bars, "warmup": WARMUP, "htf_factor": 4}
    proc = subprocess.run(
        [str(BACKTEST_BIN)], input=json.dumps(payload),
        capture_output=True, text=True, timeout=1800, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"backtest failed for {symbol}: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


def load(symbols: list[str], horizon: int):
    """Factor matrix and |forward return| across the given symbols."""
    mats, fwds = [], []
    for symbol in symbols:
        bars = fetch_klines(symbol, "1h", BARS)
        if len(bars) < WARMUP + 500:
            print(f"  ! {symbol}: only {len(bars)} bars, skipping", file=sys.stderr)
            continue
        rows = run_engine(symbol, bars)
        price = np.array([r["price"] for r in rows], dtype=float)
        usable = len(price) - horizon
        if usable < 100:
            continue
        mats.append(np.array([[r[f] for f in FACTORS] for r in rows[:usable]], dtype=float))
        fwds.append(np.abs(price[horizon:] / price[:usable] - 1.0))
        print(f"  {symbol}: {usable} obs", file=sys.stderr)

    if not mats:
        return None, None
    return np.vstack(mats), np.concatenate(fwds)


def residual_ic_weights(matrix: np.ndarray, fwd: np.ndarray) -> dict:
    """Weights proportional to each factor's RESIDUAL IC.

    Residual rather than marginal: a factor carried by the others should not be paid
    twice. Negative-IC factors get zero rather than a negative weight — a factor that
    hurts should be removed and understood, not silently inverted.
    """
    weights = {}
    for j, f in enumerate(FACTORS):
        y = matrix[:, j]
        x = np.column_stack([np.ones(len(matrix)), np.delete(matrix, j, axis=1)])
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        ic = spearman(y - x @ beta, fwd)
        weights[f] = max(0.0, ic if np.isfinite(ic) else 0.0)

    total = sum(weights.values())
    if total <= 0:
        return dict(SHIPPED)
    return {k: v / total for k, v in weights.items()}


def score_with(matrix: np.ndarray, weights: dict) -> np.ndarray:
    w = np.array([weights[f] for f in FACTORS], dtype=float)
    total = w.sum()
    return matrix @ w / (total if total > 0 else 1.0)


def main() -> int:
    if not BACKTEST_BIN.exists():
        print("build first: cargo build --release --bin backtest", file=sys.stderr)
        return 2

    for horizon in HORIZONS:
        print(f"\n{'='*72}\nHORIZON {horizon} bars", file=sys.stderr)

        print(f"[dev] deriving weights from {DEV_SYMBOLS}", file=sys.stderr)
        dev_m, dev_f = load(DEV_SYMBOLS, horizon)
        if dev_m is None:
            continue
        derived = residual_ic_weights(dev_m, dev_f)

        print(f"[heldout] scoring on {HELDOUT_SYMBOLS}", file=sys.stderr)
        ho_m, ho_f = load(HELDOUT_SYMBOLS, horizon)
        if ho_m is None:
            continue

        print(f"\n{'='*72}")
        print(f"HORIZON {horizon} bars")
        print("\nDERIVED WEIGHTS (from development symbols only)")
        for f in FACTORS:
            print(f"  {f:<20} shipped {SHIPPED[f]:.3f}  ->  derived {derived[f]:.3f}")

        n = len(ho_m)
        ic_shipped = spearman(score_with(ho_m, SHIPPED), ho_f)
        ic_derived = spearman(score_with(ho_m, derived), ho_f)

        print(f"\nHELD-OUT PERFORMANCE ({n} observations, {len(HELDOUT_SYMBOLS)} symbols)")
        print(f"  shipped weights   IC {ic_shipped:+.4f}  (t {ic_tstat(ic_shipped, n, horizon):+.2f})")
        print(f"  derived weights   IC {ic_derived:+.4f}  (t {ic_tstat(ic_derived, n, horizon):+.2f})")
        delta = ic_derived - ic_shipped
        print(f"  improvement       {delta:+.4f}")

        # Per-symbol, so a single dominant symbol cannot carry the verdict.
        print("\n  per held-out symbol:")
        improved = 0
        offset = 0
        for symbol in HELDOUT_SYMBOLS:
            m, fw = load([symbol], horizon)
            if m is None:
                continue
            a = spearman(score_with(m, SHIPPED), fw)
            b = spearman(score_with(m, derived), fw)
            mark = "+" if b > a else " "
            improved += 1 if b > a else 0
            print(f"    {mark} {symbol:<10} {a:+.4f} -> {b:+.4f}  ({b-a:+.4f})")
            offset += len(m)
        print(f"\n  {improved}/{len(HELDOUT_SYMBOLS)} symbols improved")
        if delta <= 0:
            print("  VERDICT: no out-of-sample improvement — keep the shipped prior.")
        elif improved <= len(HELDOUT_SYMBOLS) // 2:
            print("  VERDICT: aggregate improved but a minority of symbols did — not robust.")
        else:
            print("  VERDICT: improved out of sample on a majority of symbols.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
