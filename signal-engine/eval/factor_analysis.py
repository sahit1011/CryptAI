#!/usr/bin/env python3
"""Measure how much independent information each factor actually carries.

The scoring module has claimed since it was written that "six indicators that all measure
trend are one signal, not six" — and then weighted six factors as if they were
independent. This measures whether that criticism applies to our own factor set before
any orthogonalisation is built, because a fix for a problem that is not there is just
more code to get wrong.

Reports:
  - the factor correlation matrix
  - variance inflation factors (VIF > 5 is the conventional multicollinearity threshold)
  - effective number of independent factors, from the eigenvalue spectrum
  - each factor's marginal IC, and its IC after residualising against the others

Usage:  python eval/factor_analysis.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import BACKTEST_BIN, fetch_klines, ic_tstat, spearman  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
BARS = 8000
WARMUP = 300
HORIZON = 4  # bars; where tradability showed real IC

# Held constant in a kline backtest (no funding/OI/book history), so they carry no
# variance here and are excluded rather than reported as spuriously independent.
FACTORS = ["trend_alignment", "volatility_band", "efficiency_ratio", "liquidity_window"]


def run_engine(symbol: str, bars: list[dict]) -> list[dict]:
    payload = {"symbol": symbol, "bars": bars, "warmup": WARMUP, "htf_factor": 4}
    proc = subprocess.run(
        [str(BACKTEST_BIN)], input=json.dumps(payload),
        capture_output=True, text=True, timeout=1800, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"backtest failed: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


def vif(matrix: np.ndarray) -> list[float]:
    """Variance inflation factor per column: 1/(1-R^2) regressing it on the others."""
    out = []
    n_cols = matrix.shape[1]
    for j in range(n_cols):
        y = matrix[:, j]
        x = np.delete(matrix, j, axis=1)
        x = np.column_stack([np.ones(len(x)), x])
        try:
            beta, *_ = np.linalg.lstsq(x, y, rcond=None)
            resid = y - x @ beta
            ss_tot = float(((y - y.mean()) ** 2).sum())
            r2 = 1.0 - float((resid**2).sum()) / ss_tot if ss_tot > 0 else 0.0
            out.append(1.0 / (1.0 - r2) if r2 < 0.999999 else float("inf"))
        except np.linalg.LinAlgError:
            out.append(float("nan"))
    return out


def residualize(matrix: np.ndarray, j: int) -> np.ndarray:
    """Column j with everything explainable by the other columns removed."""
    y = matrix[:, j]
    x = np.column_stack([np.ones(len(matrix)), np.delete(matrix, j, axis=1)])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return y - x @ beta


def main() -> int:
    if not BACKTEST_BIN.exists():
        print("build first: cargo build --release --bin backtest", file=sys.stderr)
        return 2

    rows_all: list[dict] = []
    for symbol in SYMBOLS:
        print(f"[{symbol}] fetching + scoring...", file=sys.stderr)
        bars = fetch_klines(symbol, "1h", BARS)
        if len(bars) < WARMUP + 500:
            print(f"  ! only {len(bars)} bars, skipping", file=sys.stderr)
            continue
        rows = run_engine(symbol, bars)
        # Forward return per row, from this symbol's own price series.
        price = np.array([r["price"] for r in rows], dtype=float)
        for i, r in enumerate(rows):
            if i + HORIZON < len(price):
                r["_fwd_abs"] = abs(price[i + HORIZON] / price[i] - 1.0)
                rows_all.append(r)

    if not rows_all:
        print("no data", file=sys.stderr)
        return 1

    matrix = np.array([[r[f] for f in FACTORS] for r in rows_all], dtype=float)
    fwd = np.array([r["_fwd_abs"] for r in rows_all], dtype=float)

    keep = ~np.isnan(matrix).any(axis=1) & ~np.isnan(fwd)
    matrix, fwd = matrix[keep], fwd[keep]
    n = len(matrix)

    print(f"\n{n} observations across {len(SYMBOLS)} symbols, horizon {HORIZON} bars\n")

    print("CORRELATION MATRIX")
    print("                    " + "".join(f"{f[:11]:>13}" for f in FACTORS))
    corr = np.corrcoef(matrix, rowvar=False)
    for i, f in enumerate(FACTORS):
        print(f"  {f:<18}" + "".join(f"{corr[i][j]:>13.3f}" for j in range(len(FACTORS))))

    print("\nVARIANCE INFLATION (>5 conventionally means redundant)")
    for f, v in zip(FACTORS, vif(matrix)):
        flag = "  <-- REDUNDANT" if v > 5 else ""
        print(f"  {f:<20} VIF {v:6.2f}{flag}")

    # Effective dimensionality: how many independent factors the set really contains.
    eig = np.linalg.eigvalsh(corr)
    eig = eig[eig > 1e-12]
    p = eig / eig.sum()
    effective = math.exp(-float((p * np.log(p)).sum()))
    print(f"\nEFFECTIVE INDEPENDENT FACTORS: {effective:.2f} of {len(FACTORS)}")
    print("  (entropy of the eigenvalue spectrum; equals the count only if orthogonal)")

    print("\nMARGINAL vs RESIDUAL IC (against |forward return|)")
    print("  residual IC = the factor's IC after removing what the others explain")
    for j, f in enumerate(FACTORS):
        raw_ic = spearman(matrix[:, j], fwd)
        res_ic = spearman(residualize(matrix, j), fwd)
        print(
            f"  {f:<20} marginal {raw_ic:+.4f} (t {ic_tstat(raw_ic, n, HORIZON):+5.2f})"
            f"   residual {res_ic:+.4f} (t {ic_tstat(res_ic, n, HORIZON):+5.2f})"
        )

    print(
        "\nA factor whose residual IC collapses toward zero is being carried by the "
        "others\nand should not hold independent weight."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
