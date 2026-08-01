#!/usr/bin/env python3
"""Evaluate the signal engine against real market data.

Runs the ACTUAL Rust engine (via the `backtest` binary) over historical klines, joins
forward returns, and reports the metrics a quant desk would ask for before trusting a
signal.

The framing that matters
------------------------
`tradability` is NOT a directional forecast. It says "deploy risk now", not "go long".
Scoring it against signed forward returns would produce a number near zero and mean
nothing. So it is evaluated as a FILTER:

  - conditional forward risk-adjusted return, bucketed by score
  - does trading only in high-score windows beat trading always?

The `regime` label is the directional component, and that IS evaluated with signed IC.

Every metric is reported against a shuffled-signal null. A metric without a null is not
evidence — with enough buckets and horizons, something always looks good.

Usage:
    python eval/evaluate.py                      # BTCUSDT + XAUTUSDT, 1h
    python eval/evaluate.py --symbols BTCUSDT --bars 4000
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

BINANCE = "https://api.binance.com/api/v3/klines"
BACKTEST_BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "backtest"

# Horizons in bars. With 1h bars these are 4h, 12h, 24h, 72h.
HORIZONS = [4, 12, 24, 72]
BUCKETS = 5
# Shuffles for the null distribution. Enough to place a metric at a percentile without
# making the run slow.
NULL_TRIALS = 200
RNG_SEED = 20260802


# ---------------------------------------------------------------- data

def fetch_klines(symbol: str, interval: str, total: int) -> list[dict]:
    """Page backwards through Binance klines. Oldest-first on return."""
    out: list[dict] = []
    end_time = None

    while len(out) < total:
        limit = min(1000, total - len(out))
        url = f"{BINANCE}?symbol={symbol}&interval={interval}&limit={limit}"
        if end_time is not None:
            url += f"&endTime={end_time}"

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                rows = json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"  ! fetch failed for {symbol}: {e}", file=sys.stderr)
            break

        if not rows:
            break

        batch = [
            {
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
                "close_time": int(r[6]),
            }
            for r in rows
        ]
        out = batch + out
        end_time = int(rows[0][0]) - 1
        if len(rows) < limit:
            break
        time.sleep(0.15)  # stay well inside the public rate limit

    return out


def run_engine(symbol: str, bars: list[dict], warmup: int) -> list[dict]:
    payload = {"symbol": symbol, "bars": bars, "warmup": warmup, "htf_factor": 4}
    proc = subprocess.run(
        [str(BACKTEST_BIN)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"backtest binary failed: {proc.stderr[:500]}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- statistics

def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def rank(a: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared — required for a correct Spearman."""
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    # average tied groups
    _, inverse, counts = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inverse, ranks)
    return (sums / counts)[inverse]


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation. The standard Information Coefficient in equity quant."""
    if len(a) < 3 or len(a) != len(b):
        return float("nan")
    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def ic_tstat(ic: float, n: int, overlap: int = 1) -> float:
    """t-statistic for an IC, corrected for overlapping observations.

    Computing an h-bar forward return at EVERY bar produces h-fold overlapping windows.
    Consecutive observations then share h-1 bars of the same future, so they are nowhere
    near independent, and the naive t-statistic is inflated by roughly sqrt(h). Using
    the effective sample size n/h is the conservative correction.

    This matters enormously: at h=24 the naive t is ~5x too large, which is the
    difference between "highly significant" and "indistinguishable from noise".
    """
    if not math.isfinite(ic) or abs(ic) >= 1.0:
        return float("nan")
    effective_n = max(3, int(n / max(1, overlap)))
    return ic * math.sqrt(effective_n - 2) / math.sqrt(1 - ic * ic)


def sharpe(returns: np.ndarray, periods_per_year: float) -> float:
    if len(returns) < 2:
        return float("nan")
    sd = returns.std(ddof=1)
    if sd <= 0:
        return float("nan")
    return float(returns.mean() / sd * math.sqrt(periods_per_year))


def probabilistic_sharpe(returns: np.ndarray, benchmark_sr: float, ppy: float) -> float:
    """Bailey & Lopez de Prado PSR: probability the true Sharpe exceeds `benchmark_sr`.

    Corrects for the non-normality that makes a naive Sharpe flattering — negative skew
    and fat tails are exactly what a trading return series has.
    """
    n = len(returns)
    if n < 8:
        return float("nan")
    sr = sharpe(returns, ppy)
    if not math.isfinite(sr):
        return float("nan")

    # De-annualise for the moment calculations.
    sr_per_period = sr / math.sqrt(ppy)
    bench_per_period = benchmark_sr / math.sqrt(ppy)

    mu, sd = returns.mean(), returns.std(ddof=1)
    if sd <= 0:
        return float("nan")
    z = (returns - mu) / sd
    skew = float((z**3).mean())
    kurt = float((z**4).mean())

    denom = 1.0 - skew * sr_per_period + (kurt - 1.0) / 4.0 * sr_per_period**2
    if denom <= 0:
        return float("nan")
    return normal_cdf((sr_per_period - bench_per_period) * math.sqrt(n - 1) / math.sqrt(denom))


def deflated_sharpe(returns: np.ndarray, n_trials: int, ppy: float) -> float:
    """Deflated Sharpe: PSR against the Sharpe you would expect from the BEST of
    `n_trials` random strategies.

    This is the multiple-testing correction. Tune six weights over four horizons and you
    have run dozens of trials; the best of them looks good by construction. DSR asks
    whether it looks good *enough*.
    """
    if n_trials < 1:
        return float("nan")
    # Expected maximum of n_trials standard normals (Bailey & Lopez de Prado approx).
    euler = 0.5772156649
    if n_trials == 1:
        expected_max = 0.0
    else:
        e1 = (1 - euler) * normal_ppf(1 - 1.0 / n_trials)
        e2 = euler * normal_ppf(1 - 1.0 / (n_trials * math.e))
        expected_max = e1 + e2

    sr_star_per_period = expected_max * returns.std(ddof=1) if len(returns) > 1 else 0.0
    # Convert the threshold into annualised units for the PSR call.
    sd = returns.std(ddof=1)
    benchmark = (expected_max * math.sqrt(ppy)) if sd > 0 else 0.0
    _ = sr_star_per_period
    return probabilistic_sharpe(returns, benchmark, ppy)


def normal_ppf(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(((equity - peak) / peak).min()) if len(equity) else float("nan")


# ---------------------------------------------------------------- evaluation

def evaluate(symbol: str, rows: list[dict], interval_hours: float) -> dict:
    ts = np.array([r["ts"] for r in rows], dtype=np.int64)
    price = np.array([r["price"] for r in rows], dtype=float)
    score = np.array([r["tradability"] for r in rows], dtype=float)
    regime = np.array([r["regime"] for r in rows])
    hurst = np.array([r["hurst"] if r["hurst"] is not None else np.nan for r in rows])
    vr = np.array([r["vr_ratio"] if r["vr_ratio"] is not None else np.nan for r in rows])
    vr_p = np.array([r["vr_p_value"] if r["vr_p_value"] is not None else np.nan for r in rows])
    yz = np.array([r["yz_sigma"] if r["yz_sigma"] is not None else np.nan for r in rows])

    ppy = 24.0 / interval_hours * 365.0
    rng = np.random.default_rng(RNG_SEED)
    report: dict = {
        "symbol": symbol,
        "observations": len(rows),
        "period": {
            "from": int(ts[0]) if len(ts) else None,
            "to": int(ts[-1]) if len(ts) else None,
        },
        "score_distribution": {
            "mean": float(score.mean()),
            "std": float(score.std()),
            "min": float(score.min()),
            "p25": float(np.percentile(score, 25)),
            "median": float(np.median(score)),
            "p75": float(np.percentile(score, 75)),
            "max": float(score.max()),
        },
        "regime_mix": {r: int((regime == r).sum()) for r in sorted(set(regime.tolist()))},
        "quant_estimators": {
            "hurst_median": _nanmedian(hurst),
            "variance_ratio_median": _nanmedian(vr),
            "pct_windows_rejecting_random_walk": _pct(vr_p < 0.05),
            "yang_zhang_sigma_median": _nanmedian(yz),
        },
        "horizons": {},
        "filter_test": {},
    }

    for h in HORIZONS:
        if len(price) <= h + 10:
            continue
        fwd = np.full(len(price), np.nan)
        fwd[:-h] = price[h:] / price[:-h] - 1.0
        valid = ~np.isnan(fwd)
        if valid.sum() < 50:
            continue

        s, f = score[valid], fwd[valid]
        abs_f = np.abs(f)

        # Tradability is non-directional: rank it against ABSOLUTE forward move, which
        # is what "is there an opportunity here" actually means.
        ic_abs = spearman(s, abs_f)
        # Reported for completeness; near zero is the CORRECT result for a
        # non-directional score, not a failure.
        ic_signed = spearman(s, f)

        # Directional component: does the regime label carry sign?
        direction = np.where(
            regime[valid] == "TrendingUp", 1.0,
            np.where(regime[valid] == "TrendingDown", -1.0, 0.0),
        )
        ic_regime = spearman(direction, f)

        # Null: shuffle the signal, keep the return series. Anything the metric
        # picks up from autocorrelation alone shows up here too.
        null_abs = np.array([spearman(rng.permutation(s), abs_f) for _ in range(NULL_TRIALS)])
        pctile = float((np.abs(null_abs) < abs(ic_abs)).mean() * 100) if math.isfinite(ic_abs) else float("nan")

        # Does the score add anything BEYOND volatility clustering? Realised volatility
        # is strongly autocorrelated, so any score containing a volatility term will
        # trivially "predict" |forward return|. Normalising the forward move by the
        # volatility already observable at decision time strips that out. What survives
        # is the part that is actually informative.
        vol_now = np.abs(yz[valid])
        with np.errstate(divide="ignore", invalid="ignore"):
            normalized = np.where(vol_now > 0, abs_f / vol_now, np.nan)
        ok = ~np.isnan(normalized)
        ic_excess = spearman(s[ok], normalized[ok]) if ok.sum() > 50 else float("nan")

        n_valid = int(valid.sum())
        report["horizons"][f"{h}bar"] = {
            "n": n_valid,
            "effective_n": int(n_valid / h),
            "ic_vs_abs_return": ic_abs,
            "ic_tstat": ic_tstat(ic_abs, n_valid, overlap=h),
            "ic_vs_vol_normalized_return": ic_excess,
            "ic_excess_tstat": ic_tstat(ic_excess, int(ok.sum()), overlap=h),
            "ic_vs_signed_return": ic_signed,
            "ic_regime_vs_signed_return": ic_regime,
            "ic_regime_tstat": ic_tstat(ic_regime, n_valid, overlap=h),
            "null_percentile": pctile,
            "buckets": _bucket_stats(s, f, ppy, h),
        }

    # --- the filter test: does gating on a high score beat always being on? ----
    #
    # NON-OVERLAPPING sampling, every h bars. Taking an h-bar forward return at every
    # bar and compounding it would count each holding period h times over, which
    # manufactures both the return and the drawdown. That error produces impossible
    # numbers (annualised Sharpe in the tens, -99% drawdowns) and it is the single most
    # common way a backtest reports a strategy that was never traded.
    h = 24
    if len(price) > h * 20:
        idx = np.arange(0, len(price) - h, h)
        f = price[idx + h] / price[idx] - 1.0
        s = score[idx]
        reg = regime[idx]
        direction = np.where(reg == "TrendingUp", 1.0, np.where(reg == "TrendingDown", -1.0, 0.0))

        # A deliberately naive directional rule, so the comparison isolates the FILTER's
        # contribution rather than a clever strategy's.
        always = direction * f
        threshold = float(np.percentile(s, 70))
        gated = np.where(s >= threshold, direction * f, 0.0)

        # One observation per h bars, so the annualisation factor scales down with it.
        ppy_h = ppy / h
        traded = gated != 0
        report["filter_test"] = {
            "horizon_bars": h,
            "sampling": "non-overlapping",
            "periods": int(len(idx)),
            "score_threshold_p70": threshold,
            "always_on": _strategy_stats(always, ppy_h),
            "gated_on_high_score": _strategy_stats(gated, ppy_h),
            "time_in_market_pct": _pct(traded),
            "deflated_sharpe_gated": deflated_sharpe(
                gated[traded], n_trials=len(HORIZONS) * BUCKETS, ppy=ppy_h
            )
            if traded.sum() > 10
            else float("nan"),
        }

    return report


def _bucket_stats(s: np.ndarray, f: np.ndarray, ppy: float, horizon: int) -> list[dict]:
    """Forward outcomes by score quintile. The core filter evidence: if the top bucket
    does not differ from the bottom, the score is decoration."""
    edges = np.percentile(s, np.linspace(0, 100, BUCKETS + 1))
    out = []
    for i in range(BUCKETS):
        lo, hi = edges[i], edges[i + 1]
        mask = (s >= lo) & (s <= hi) if i == BUCKETS - 1 else (s >= lo) & (s < hi)
        if mask.sum() < 10:
            continue
        sub = f[mask]
        out.append({
            "bucket": i + 1,
            "score_range": [float(lo), float(hi)],
            "n": int(mask.sum()),
            "mean_abs_return_pct": float(np.abs(sub).mean() * 100),
            "mean_return_pct": float(sub.mean() * 100),
            "volatility_pct": float(sub.std() * 100),
            "hit_rate_pct": float((sub > 0).mean() * 100),
        })
    return out


def _strategy_stats(returns: np.ndarray, ppy: float) -> dict:
    active = returns[returns != 0]
    equity = np.cumprod(1 + returns)
    return {
        "mean_return_pct": float(returns.mean() * 100),
        "sharpe": sharpe(returns, ppy),
        "sharpe_when_active": sharpe(active, ppy) if len(active) > 2 else float("nan"),
        "max_drawdown_pct": max_drawdown(equity) * 100,
        "psr_vs_zero": probabilistic_sharpe(returns, 0.0, ppy),
    }


def _nanmedian(a: np.ndarray) -> float:
    valid = a[~np.isnan(a)]
    return float(np.median(valid)) if len(valid) else float("nan")


def _pct(mask) -> float:
    arr = np.asarray(mask)
    valid = arr[~np.isnan(arr)] if arr.dtype.kind == "f" else arr
    return float(valid.mean() * 100) if len(valid) else float("nan")


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "XAUTUSDT"])
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--bars", type=int, default=8000)
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not BACKTEST_BIN.exists():
        print(f"backtest binary missing: {BACKTEST_BIN}", file=sys.stderr)
        print("build it: cargo build --release --bin backtest", file=sys.stderr)
        return 2

    interval_hours = {"1h": 1.0, "4h": 4.0, "15m": 0.25, "1d": 24.0}.get(args.interval, 1.0)

    reports = []
    for symbol in args.symbols:
        print(f"[{symbol}] fetching {args.bars} {args.interval} bars...", file=sys.stderr)
        bars = fetch_klines(symbol, args.interval, args.bars)
        if len(bars) < args.warmup + 200:
            print(f"  ! only {len(bars)} bars, skipping", file=sys.stderr)
            continue
        print(f"[{symbol}] {len(bars)} bars; running engine...", file=sys.stderr)
        rows = run_engine(symbol, bars, args.warmup)
        print(f"[{symbol}] {len(rows)} pulses; evaluating...", file=sys.stderr)
        reports.append(evaluate(symbol, rows, interval_hours))

    payload = {"generated_ms": int(time.time() * 1000), "reports": reports}
    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
