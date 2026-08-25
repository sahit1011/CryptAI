"""Measure the intraday liquidity/volatility profile — the honest basis for a
"hot window" badge.

The honesty law forbids forward "hottest hour" claims until logged data earns them.
This does not predict anything: it measures, over 24 months of BTC/ETH/SOL 1m bars,
how each UTC hour has actually ranked by realized volume and realized range, and
emits that as a calibrated table with its sample size and date range attached. The
product may then say "this hour has historically been the Nth most active of 24" —
a backward-looking, checkable statement — and never "the next hour will be hot".

Per-symbol z-scores are averaged so one high-priced symbol cannot dominate, and the
per-year split is emitted so a reader can see whether the shape is stable or drifting
(a profile that reshuffles year to year does not deserve a badge at all).

Output: results/hour_profile.json + hour_profile.md, and the committed artifact
../crypto-trading-agent/src/signals/hour_profile.json consumed by the API.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from data_loader import load  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
ARTIFACT = os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent",
                        "src", "signals", "hour_profile.json")


def hour_stats(m: dict) -> dict:
    """Per-UTC-hour mean volume and mean bar range (as a fraction of price)."""
    ts = m["open_time"]
    hours = ((ts // 3_600_000) % 24).astype(np.int64)
    years = np.array([1970 + int(t // 31_556_952_000) for t in ts])  # coarse, for split only
    vol = m["volume"]
    rng = np.divide(m["high"] - m["low"], m["close"],
                    out=np.zeros_like(m["close"]), where=m["close"] > 0)

    out = {"n_bars": int(len(ts)), "by_hour": {}, "by_year_hour": defaultdict(dict)}
    for h in range(24):
        sel = hours == h
        out["by_hour"][h] = {
            "mean_volume": float(vol[sel].mean()),
            "mean_range": float(rng[sel].mean()),
            "n": int(sel.sum()),
        }
        for y in sorted(set(years.tolist())):
            sel_y = sel & (years == y)
            if sel_y.sum() > 1000:
                out["by_year_hour"][y][h] = float(vol[sel_y].mean())
    return out


def zscore(values: dict) -> dict:
    arr = np.array([values[h] for h in range(24)], dtype=float)
    sd = arr.std()
    if sd == 0:
        return {h: 0.0 for h in range(24)}
    return {h: float((arr[h] - arr.mean()) / sd) for h in range(24)}


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    per_symbol, spans = {}, []
    for sym in SYMBOLS:
        m = load(sym, "1m")
        per_symbol[sym] = hour_stats(m)
        spans.append((int(m["open_time"][0]), int(m["open_time"][-1])))
        print(f"{sym}: {per_symbol[sym]['n_bars']:,} 1m bars")

    # Average the per-symbol z-scores so a high-notional symbol cannot dominate.
    vol_z = {h: float(np.mean([zscore({k: v["mean_volume"] for k, v in
                                       per_symbol[s]["by_hour"].items()})[h]
                               for s in SYMBOLS])) for h in range(24)}
    rng_z = {h: float(np.mean([zscore({k: v["mean_range"] for k, v in
                                       per_symbol[s]["by_hour"].items()})[h]
                               for s in SYMBOLS])) for h in range(24)}
    combined = {h: (vol_z[h] + rng_z[h]) / 2 for h in range(24)}
    order = sorted(range(24), key=lambda h: -combined[h])
    rank = {h: order.index(h) + 1 for h in range(24)}  # 1 = most active

    # Stability: does each year agree on the top-6 hours? A badge is only honest
    # if the shape persists.
    top6 = set(order[:6])
    per_year_top6 = {}
    for sym in SYMBOLS:
        for y, hours in per_symbol[sym]["by_year_hour"].items():
            if len(hours) < 24:
                continue
            year_order = sorted(hours, key=lambda h: -hours[h])[:6]
            per_year_top6.setdefault(str(y), []).append(len(top6 & set(year_order)))
    stability = {y: round(float(np.mean(v)), 2) for y, v in sorted(per_year_top6.items())}

    artifact = {
        "schema": 1,
        "measured_from_ms": min(s[0] for s in spans),
        "measured_to_ms": max(s[1] for s in spans),
        "symbols": SYMBOLS,
        "total_1m_bars": sum(per_symbol[s]["n_bars"] for s in SYMBOLS),
        "metric": "mean of per-symbol z-scores of (mean 1m volume, mean 1m range/price)",
        "hours_utc": {str(h): {"score": round(combined[h], 4), "rank": rank[h]}
                      for h in range(24)},
        "top6_hours_utc": sorted(order[:6]),
        "top6_agreement_per_year": stability,
        "caveat": ("Backward-looking measurement, not a forecast. Ranks say how active "
                   "each UTC hour HAS been across these symbols over this window; they "
                   "say nothing about the next hour."),
    }
    with open(os.path.join(RESULTS_DIR, "hour_profile.json"), "w") as f:
        json.dump(artifact, f, indent=2)
    with open(ARTIFACT, "w") as f:
        json.dump(artifact, f, indent=2)

    lines = ["| UTC hour | IST | score | rank |", "|---|---|---|---|"]
    for h in range(24):
        ist = f"{(h + 5) % 24:02d}:30"
        lines.append(f"| {h:02d}:00 | {ist} | {combined[h]:+.3f} | {rank[h]} |")
    md = ("# Intraday activity profile (measured, not predicted)\n\n"
          f"{artifact['total_1m_bars']:,} 1m bars, {', '.join(SYMBOLS)}.\n\n"
          f"Top-6 UTC hours: {artifact['top6_hours_utc']}\n\n"
          f"Per-year agreement with those 6 (out of 6): {stability}\n\n"
          + "\n".join(lines) + f"\n\n{artifact['caveat']}\n")
    with open(os.path.join(RESULTS_DIR, "hour_profile.md"), "w") as f:
        f.write(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
