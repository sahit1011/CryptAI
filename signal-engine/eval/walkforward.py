#!/usr/bin/env python3
"""Out-of-sample validation of the variance-ratio regime fix.

WHAT IS ACTUALLY BEING TESTED
-----------------------------
On 2026-08-02 the regime classifier was changed after seeing BTC and XAUT data: the
variance ratio was given veto power over trend labels. In-sample the wrong-signed bias
vanished. That is exactly the situation where a result is most likely to be an artifact
of having looked at the data first.

The rule has ONE free parameter (`vr_mean_reversion_max = 0.95`; `vr_trend_min = 1.0` is
the theoretical random-walk value, not fitted). So there is nothing to "train" — a
classical train/test split would be theatre. Three tests that actually bear on
generalisation:

  A. TEMPORAL STABILITY - split each series into contiguous folds and compute the metric
     per fold. A fix driven by one unusual period shows up as one good fold and several
     neutral ones.

  B. PARAMETER SENSITIVITY - sweep the threshold. A real effect is a plateau; an overfit
     one is a spike at the chosen value.

  C. HELD-OUT INSTRUMENTS - run on symbols never examined while building the fix. This is
     the strongest evidence available, because those series had no opportunity to
     influence any choice.

The A/B is exact: baseline reproduces the pre-fix classifier by pushing both variance
ratio thresholds to -1e9, so the identical binary and identical bars produce the old
labels. No reimplementation of the old code to drift out of sync.

Every forward return is sampled NON-OVERLAPPING, and t-statistics use effective sample
size. Both were bugs in the first version of the sibling evaluate.py.

Usage:
    python eval/walkforward.py
"""
from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (  # noqa: E402
    BACKTEST_BIN,
    fetch_klines,
    ic_tstat,
    max_drawdown,
    sharpe,
    spearman,
)

# Used while building the fix — their results are IN-SAMPLE by construction.
DEVELOPMENT_SYMBOLS = ["BTCUSDT", "XAUTUSDT"]
# Never looked at. This is the out-of-sample evidence.
HELDOUT_SYMBOLS = ["ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT"]

# Reproduces the pre-fix classifier exactly.
BASELINE_OVERRIDES = {"vr_mean_reversion_max": -1e9, "vr_trend_min": -1e9}
# The shipped values.
TREATMENT_OVERRIDES = {"vr_mean_reversion_max": 0.95, "vr_trend_min": 1.0}

HORIZON = 24  # bars; where the in-sample effect was largest
FOLDS = 4
BARS = 8000
WARMUP = 300


def run_engine(symbol: str, bars: list[dict], overrides: dict) -> list[dict]:
    payload = {"symbol": symbol, "bars": bars, "warmup": WARMUP, "htf_factor": 4, **overrides}
    proc = subprocess.run(
        [str(BACKTEST_BIN)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"backtest failed for {symbol}: {proc.stderr[:400]}")
    return json.loads(proc.stdout)


def directional(regimes: np.ndarray) -> np.ndarray:
    return np.where(regimes == "TrendingUp", 1.0, np.where(regimes == "TrendingDown", -1.0, 0.0))


def metrics(rows: list[dict], horizon: int = HORIZON) -> dict:
    """Regime metrics on NON-OVERLAPPING forward windows."""
    if len(rows) < horizon * 8:
        return {}

    price = np.array([r["price"] for r in rows], dtype=float)
    regime = np.array([r["regime"] for r in rows])

    idx = np.arange(0, len(price) - horizon, horizon)
    fwd = price[idx + horizon] / price[idx] - 1.0
    d = directional(regime[idx])

    ic = spearman(d, fwd)
    pnl = d * fwd
    active = pnl[d != 0]

    # One observation per `horizon` bars, so annualise at that frequency.
    ppy = (24.0 * 365.0) / horizon

    return {
        "periods": int(len(idx)),
        "regime_ic": ic,
        "regime_ic_t": ic_tstat(ic, len(idx), overlap=1),
        "directional_sharpe": sharpe(pnl, ppy),
        "trades": int((d != 0).sum()),
        "mean_trade_pct": float(active.mean() * 100) if len(active) else float("nan"),
        "max_drawdown_pct": max_drawdown(np.cumprod(1 + pnl)) * 100,
        "trend_label_pct": float((d != 0).mean() * 100),
    }


def fold_metrics(rows: list[dict], folds: int = FOLDS) -> list[dict]:
    """Contiguous time folds.

    An embargo of one horizon is dropped at each boundary so a window straddling two
    folds cannot contribute its future to both.
    """
    n = len(rows)
    size = n // folds
    out = []
    for k in range(folds):
        start = k * size + (HORIZON if k > 0 else 0)
        end = (k + 1) * size if k < folds - 1 else n
        m = metrics(rows[start:end])
        if m:
            m["fold"] = k + 1
            out.append(m)
    return out


def evaluate_symbol(symbol: str, bars: list[dict]) -> dict:
    base_rows = run_engine(symbol, bars, BASELINE_OVERRIDES)
    treat_rows = run_engine(symbol, bars, TREATMENT_OVERRIDES)

    return {
        "symbol": symbol,
        "observations": len(treat_rows),
        "baseline": metrics(base_rows),
        "treatment": metrics(treat_rows),
        "baseline_folds": fold_metrics(base_rows),
        "treatment_folds": fold_metrics(treat_rows),
    }


def sensitivity(symbol: str, bars: list[dict]) -> list[dict]:
    """Sweep the one free parameter. A plateau is a real effect; a spike is a fit."""
    out = []
    for thr in [0.85, 0.90, 0.93, 0.95, 0.97, 1.00, 1.03]:
        rows = run_engine(
            symbol, bars, {"vr_mean_reversion_max": thr, "vr_trend_min": 1.0}
        )
        m = metrics(rows)
        if m:
            out.append({
                "vr_mean_reversion_max": thr,
                "regime_ic": m["regime_ic"],
                "directional_sharpe": m["directional_sharpe"],
                "trend_label_pct": m["trend_label_pct"],
                "trades": m["trades"],
            })
    return out


def main() -> int:
    if not BACKTEST_BIN.exists():
        print(f"missing {BACKTEST_BIN}; run cargo build --release --bin backtest", file=sys.stderr)
        return 2

    results = {"development": [], "heldout": [], "sensitivity": {}}
    cache: dict[str, list[dict]] = {}

    for group, symbols in (("development", DEVELOPMENT_SYMBOLS), ("heldout", HELDOUT_SYMBOLS)):
        for symbol in symbols:
            print(f"[{group}] {symbol}: fetching...", file=sys.stderr)
            bars = fetch_klines(symbol, "1h", BARS)
            if len(bars) < WARMUP + HORIZON * 20:
                print(f"  ! only {len(bars)} bars, skipping", file=sys.stderr)
                continue
            cache[symbol] = bars
            print(f"[{group}] {symbol}: {len(bars)} bars, running A/B...", file=sys.stderr)
            results[group].append(evaluate_symbol(symbol, bars))

    for symbol in DEVELOPMENT_SYMBOLS:
        if symbol in cache:
            print(f"[sensitivity] {symbol}...", file=sys.stderr)
            results["sensitivity"][symbol] = sensitivity(symbol, cache[symbol])

    # Aggregate the out-of-sample verdict: paired improvement across held-out symbols.
    deltas = [
        r["treatment"]["regime_ic"] - r["baseline"]["regime_ic"]
        for r in results["heldout"]
        if r["baseline"] and r["treatment"]
    ]
    if deltas:
        mean_d = statistics.mean(deltas)
        sd_d = statistics.stdev(deltas) if len(deltas) > 1 else float("nan")
        t = mean_d / (sd_d / math.sqrt(len(deltas))) if sd_d and sd_d > 0 else float("nan")
        results["heldout_summary"] = {
            "n_symbols": len(deltas),
            "mean_ic_improvement": mean_d,
            "sd": sd_d,
            "paired_t": t,
            "symbols_improved": sum(1 for d in deltas if d > 0),
        }

    out = Path(__file__).resolve().parent / "walkforward_results.json"
    out.write_text(json.dumps({"generated_ms": int(time.time() * 1000), **results}, indent=2, default=str))
    print(f"wrote {out}", file=sys.stderr)
    print(json.dumps(results.get("heldout_summary", {}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
