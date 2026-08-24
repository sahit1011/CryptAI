"""S1 entry-confirmation A/B — v2, PRE-REGISTERED follow-up to study_s1_ab.py.

v1's verdict (FINDINGS.md 2026-08-25): confirmation carries information (+0.13R) but
no arm clears zero at taker fees with no environment stage. v1's entry pre-registered
EXACTLY three changes for v2 — this script runs those three and NOTHING else:

  1. ENVIRONMENT GATES — three binary gates evaluated at the touch bar, past data only:
       G_vol      trailing 24h realized vol (std of 1m log-returns over the 1440 bars
                  before the touch) sits between the 25th and 75th percentile of the
                  same stat's trailing 30-day distribution (sampled hourly, 720 samples).
       G_part     the shipped participation_ok() at the touch bar (v1 only applied it
                  inside confirmation; here it gates the EVENT).
       G_session  touch bar's UTC time-of-day in [13:30, 16:30) — NY-open window.
  2. FEE MODEL — maker/taker by how each fill would actually execute:
       edge entries (control_all / control_confirmed / treatment_retest)  maker 2bps
       flip-close entries (treatment / treatment_wide)                    taker 5bps
       exits: stop taker 5bps · target maker 2bps · time-stop taker 5bps
  3. REPORT MATRIX — {baseline, G_vol, G_part, G_session, all three} × the same 5 arms.

No threshold sweeps. No new arms. Gates are applied as FILTERS over the fixed v1
event stream (same touches, same non-overlap, same pessimistic same-bar resolution),
so "survived the gate" is measured against the identical baseline v1 reported.
Event enumeration and bracket walking are imported from study_s1_ab so v2 cannot
silently diverge from v1; v2 re-prices each resolved bracket under the new fee model.

Run:  crypto-trading-agent/.venv/bin/python backtest-lab/study_s1_ab_v2.py
Outputs: results/s1_ab_v2_summary.md, results/s1_ab_v2_trades.csv
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent"))
sys.path.insert(0, os.path.dirname(__file__))

import study_s1_ab as v1  # noqa: E402  — the machinery under test, unchanged
from data_loader import load  # noqa: E402
from src.strategy.s1_signals import (  # noqa: E402
    S1Params,
    confirm_entry,
    discount_band,
    latest_swing,
    participation_ok,
)

SYMBOLS = v1.SYMBOLS
PARAMS: S1Params = v1.PARAMS
SWING_WINDOW_1H = v1.SWING_WINDOW_1H
WARMUP_1H = v1.WARMUP_1H
R_TARGETS = v1.R_TARGETS
PRE_TOUCH_BARS = v1.PRE_TOUCH_BARS
RETEST_WINDOW_BARS = v1.RETEST_WINDOW_BARS
RESULTS_DIR = v1.RESULTS_DIR

# --- pre-registered fee model (change 2) ---------------------------------------
MAKER_FEE = 0.0002
TAKER_FEE = 0.0005
ENTRY_FEE = {  # by arm — how the entry fill would actually execute
    "control_all": MAKER_FEE,        # resting limit at the band edge
    "control_confirmed": MAKER_FEE,  # same fill as control_all
    "treatment_retest": MAKER_FEE,   # resting limit back at the edge
    "treatment": TAKER_FEE,          # market/stop-in at the flip close
    "treatment_wide": TAKER_FEE,     # same flip-close fill
}
EXIT_FEE = {"stop": TAKER_FEE, "target": MAKER_FEE, "time": TAKER_FEE}

# --- pre-registered gate constants (change 1) -----------------------------------
RV_WINDOW_1M = 1440          # trailing 24h of 1m log-returns
RV_PCTL_SAMPLES_H = 720      # trailing 30 days of hourly samples of the rv stat
RV_PCTL_LO, RV_PCTL_HI = 0.25, 0.75
SESSION_LO_MIN, SESSION_HI_MIN = 13 * 60 + 30, 16 * 60 + 30  # [13:30, 16:30) UTC


def reprice(row: dict, m: dict, entry: float, stop: float, r_mult: float,
            direction: str, entry_fee_rate: float) -> dict:
    """Re-price a v1-resolved bracket under the maker/taker fee model.

    Exit timing/price are fee-independent, so the v1 walk is reused verbatim and only
    the fee legs change: entry at the arm's fill type, exit by how that exit executes.
    """
    risk = abs(entry - stop)
    sign = 1.0 if direction == "long" else -1.0
    reason = row["exit_reason"]
    if reason == "stop":
        exit_price = stop
    elif reason == "target":
        exit_price = entry + r_mult * risk if direction == "long" else entry - r_mult * risk
    else:  # time stop — exits at the close of the last bar of the window
        exit_price = float(m["close"][row["exit_index"]])
    gross = sign * (exit_price - entry)
    fees = entry_fee_rate * entry + EXIT_FEE[reason] * exit_price
    return {**row, "net_r": (gross - fees) / risk, "fee_r": fees / risk}


def resolve(m: dict, arm: str, entry_idx: int, entry: float, stop: float,
            r_mult: float, direction: str) -> dict | None:
    """v1 bracket walk (pessimistic same-bar) + v2 fee model."""
    row = v1.resolve_bracket(m, entry_idx, entry, stop, r_mult, direction)
    if row is None:
        return None
    return reprice(row, m, entry, stop, r_mult, direction, ENTRY_FEE[arm])


def realized_vol_gate_arrays(m: dict) -> tuple:
    """Precompute, once per symbol: rv(as-of) per 1m bar and the hourly-sampled
    trailing-30d P25/P75 of the same stat. All past-only by construction.

    rv[i] = std of the 1440 1m log-returns ending with the return INTO bar i+1,
    so the stat as-of touch bar g (using only closes <= bar g-1) is rv[g-2].
    """
    close = m["close"]
    r = np.diff(np.log(close))                      # r[i] = log(close[i+1]/close[i])
    rv = pd.Series(r).rolling(RV_WINDOW_1M).std().to_numpy()

    n = len(close)
    n_hours = n // 60
    hour_anchor = np.arange(n_hours) * 60 - 2       # rv index "as of" each hour start
    S = np.full(n_hours, np.nan)
    ok = hour_anchor >= 0
    S[ok] = rv[hour_anchor[ok]]
    s = pd.Series(S)
    # rolling(...).quantile at k covers S[k-719..k]; shift(1) -> S[k-720..k-1]:
    # the 720 hourly samples strictly BEFORE the touch's hour. NaN anywhere in the
    # window -> NaN out (min_periods = window), i.e. the gate fails closed.
    p25 = s.rolling(RV_PCTL_SAMPLES_H).quantile(RV_PCTL_LO).shift(1).to_numpy()
    p75 = s.rolling(RV_PCTL_SAMPLES_H).quantile(RV_PCTL_HI).shift(1).to_numpy()
    return rv, p25, p75


def g_vol_at(g: int, rv: np.ndarray, p25: np.ndarray, p75: np.ndarray) -> bool:
    if g < 2:
        return False
    k = g // 60
    if k >= len(p25):
        return False
    rv_g, lo, hi = rv[g - 2], p25[k], p75[k]
    if not (np.isfinite(rv_g) and np.isfinite(lo) and np.isfinite(hi)):
        return False  # <30d of history — an unmeasurable regime is not "normal"
    return bool(lo <= rv_g <= hi)


def g_session_at(open_time_ms: int) -> bool:
    minute_of_day = (open_time_ms // 60_000) % 1440
    return SESSION_LO_MIN <= minute_of_day < SESSION_HI_MIN


def run_symbol(symbol: str) -> list:
    """v1's event enumeration verbatim (same touches, same busy_until) + per-event
    gate flags + v2 fee pricing. Any structural edit here must be mirrored against
    v1.run_symbol — the loop is duplicated only because v1 hard-codes its fee model
    and records no gate state.
    """
    h, m = load(symbol, "1h"), load(symbol, "1m")
    h_open_time, m_open_time = h["open_time"], m["open_time"]
    rv, p25h, p75h = realized_vol_gate_arrays(m)

    trades = []
    armed = None
    busy_until = 0
    touches = confirmed = 0

    for hi in range(WARMUP_1H, len(h_open_time) - 1):
        window = v1.bars_as_dicts(h, hi - SWING_WINDOW_1H + 1, hi + 1)
        swing = latest_swing(window, PARAMS.swing_left, PARAMS.swing_right)
        if swing:
            base = hi - SWING_WINDOW_1H + 1
            key = (base + swing["high_index"], base + swing["low_index"])
            direction = "long" if swing["high_index"] > swing["low_index"] else "short"
            if key != (armed or {}).get("key"):
                try:
                    entry_edge, invalidation = discount_band(swing["low"], swing["high"], direction)
                except ValueError:
                    entry_edge = None
                close = float(h["close"][hi])
                fresh = entry_edge is not None and (
                    close > entry_edge if direction == "long" else close < entry_edge
                )
                armed = {"key": key, "direction": direction, "entry_edge": entry_edge,
                         "invalidation": invalidation, "consumed": not fresh}

        if not armed or armed["consumed"]:
            continue

        t0 = int(h_open_time[hi]) + 3_600_000
        g0 = int(np.searchsorted(m_open_time, t0))
        g1 = int(np.searchsorted(m_open_time, t0 + 3_600_000))
        d = armed["direction"]
        for g in range(max(g0, busy_until, PRE_TOUCH_BARS), g1):
            close_g = float(m["close"][g])
            if (d == "long" and close_g < armed["invalidation"]) or (
                d == "short" and close_g > armed["invalidation"]
            ):
                armed["consumed"] = True
                break
            hit = m["low"][g] <= armed["entry_edge"] if d == "long" else m["high"][g] >= armed["entry_edge"]
            if not hit:
                continue

            armed["consumed"] = True
            touches += 1
            edge, inval = armed["entry_edge"], armed["invalidation"]
            buffer = PARAMS.stop_buffer_frac * edge
            ctl_stop = inval - buffer if d == "long" else inval + buffer

            tape = v1.bars_as_dicts(
                m, g - PRE_TOUCH_BARS, min(len(m_open_time), g + PARAMS.confirm_window_bars + 5)
            )
            entry_ev = confirm_entry(tape, PRE_TOUCH_BARS, d, PARAMS, invalidation_price=inval)

            # --- the three pre-registered gates, at the touch bar, past data only ---
            gates = {
                "g_vol": g_vol_at(g, rv, p25h, p75h),
                "g_part": participation_ok(tape, PRE_TOUCH_BARS, PARAMS),
                "g_session": g_session_at(int(m_open_time[g])),
            }

            event_rows = []
            for r_mult in R_TARGETS:
                ctl = resolve(m, "control_all", g, edge, ctl_stop, r_mult, d)
                if ctl:
                    event_rows.append({"arm": "control_all", "r_mult": r_mult, **ctl})
                if entry_ev:
                    ge = g - PRE_TOUCH_BARS + entry_ev.entry_index
                    trt = resolve(m, "treatment", ge, entry_ev.entry_price, entry_ev.stop_price, r_mult, d)
                    if trt:
                        event_rows.append({"arm": "treatment", "r_mult": r_mult, **trt})
                    wide = resolve(m, "treatment_wide", ge, entry_ev.entry_price, ctl_stop, r_mult, d)
                    if wide:
                        event_rows.append({"arm": "treatment_wide", "r_mult": r_mult, **wide})
                    rt_end = min(len(m_open_time), ge + 1 + RETEST_WINDOW_BARS)
                    if rt_end > ge + 1:
                        seg = m["low"][ge + 1: rt_end] if d == "long" else m["high"][ge + 1: rt_end]
                        refill = seg <= edge if d == "long" else seg >= edge
                        if refill.any():
                            gf = ge + 1 + int(np.argmax(refill))
                            rt = resolve(m, "treatment_retest", gf, edge, ctl_stop, r_mult, d)
                            if rt:
                                event_rows.append({"arm": "treatment_retest", "r_mult": r_mult, **rt})
                    if ctl:
                        cc = reprice(
                            {k: ctl[k] for k in ("exit_index", "exit_reason", "bars_held")},
                            m, edge, ctl_stop, r_mult, d, ENTRY_FEE["control_confirmed"],
                        )
                        event_rows.append({"arm": "control_confirmed", "r_mult": r_mult, **cc})
            if entry_ev:
                confirmed += 1
            for row in event_rows:
                trades.append({"symbol": symbol, "direction": d, "touch_ts": int(m_open_time[g]),
                               "touch_index": g, **gates, **row})
            if event_rows:
                busy_until = max(r["exit_index"] for r in event_rows) + 1
            break

    print(f"{symbol}: touches={touches} confirmed={confirmed} "
          f"({100 * confirmed / max(1, touches):.1f}%) trade-rows={len(trades)}")
    return trades


# --- report matrix (change 3): exactly five configurations, no more ---------------
CONFIGS = [
    ("baseline", lambda t: True),
    ("G_vol only", lambda t: t["g_vol"]),
    ("G_part only", lambda t: t["g_part"]),
    ("G_session only", lambda t: t["g_session"]),
    ("all three", lambda t: t["g_vol"] and t["g_part"] and t["g_session"]),
]


def summarize(trades: list) -> str:
    if not trades:
        return "_no events survive this configuration_"
    return v1.summarize(trades)


def event_keys(trades: list) -> set:
    return {(t["symbol"], t["touch_ts"]) for t in trades}


def main() -> None:
    assert v1.SAME_BAR == "pessimistic", "v2 is pre-registered on pessimistic same-bar"
    os.makedirs(RESULTS_DIR, exist_ok=True)

    all_trades = []
    for sym in SYMBOLS:
        all_trades.extend(run_symbol(sym))

    with open(os.path.join(RESULTS_DIR, "s1_ab_v2_trades.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
        w.writeheader()
        w.writerows(all_trades)

    n_baseline_events = len(event_keys(all_trades))
    sections = []
    survival_lines = ["| config | events | survival vs baseline |", "|---|---|---|"]
    for name, pred in CONFIGS:
        sub = [t for t in all_trades if pred(t)]
        n_events = len(event_keys(sub))
        frac = n_events / n_baseline_events if n_baseline_events else 0.0
        survival_lines.append(f"| {name} | {n_events} | {100 * frac:.1f}% |")

        body = f"## {name}\n"
        if name != "baseline":
            body += f"Events surviving gate: **{n_events}/{n_baseline_events} ({100 * frac:.1f}%)**\n\n"
        body += summarize(sub)
        if name == "all three":  # pre-registered: full breakdown for the combined gate only
            per_symbol = "\n\n".join(
                f"### {sym}\n" + summarize([t for t in sub if t["symbol"] == sym])
                for sym in SYMBOLS
            )
            per_direction = "\n\n".join(
                f"### {d}\n" + summarize([t for t in sub if t["direction"] == d])
                for d in ("long", "short")
            )
            body += f"\n\n### By symbol\n\n{per_symbol}\n\n### By direction\n\n{per_direction}"
        sections.append(body)

    md = (
        "# S1 A/B v2 results (pre-registered: gates + maker/taker fees, no sweeps)\n\n"
        "Same v1 event stream (2024-08→2026-07, BTC/ETH/SOL, pessimistic same-bar, 8h "
        "time stop, zero slippage, one event at a time per symbol); gates filter that "
        "fixed stream, so gated configs inherit baseline's non-overlap.\n\n"
        f"**Fees:** maker {MAKER_FEE * 1e4:.0f}bps / taker {TAKER_FEE * 1e4:.0f}bps. "
        "Entries — edge fills (control_all, control_confirmed, treatment_retest) maker; "
        "flip-close fills (treatment, treatment_wide) taker. Exits — stop taker, target "
        "maker, time-stop taker.\n\n"
        "**Gates (binary, at the touch bar, past data only):** "
        f"`G_vol` = trailing 24h rv (std of 1m log-returns, {RV_WINDOW_1M} bars ending "
        "at the bar before the touch) within [P25, P75] of its trailing 30-day hourly-"
        f"sampled distribution ({RV_PCTL_SAMPLES_H} samples; fails closed on <30d "
        "history, so month 1 of each symbol never passes); "
        "`G_part` = shipped `participation_ok` at the touch; "
        "`G_session` = touch bar UTC time-of-day in [13:30, 16:30).\n\n"
        f"## Gate survival (of {n_baseline_events} baseline events)\n"
        + "\n".join(survival_lines) + "\n\n"
        + "\n\n".join(sections) + "\n"
    )
    with open(os.path.join(RESULTS_DIR, "s1_ab_v2_summary.md"), "w") as f:
        f.write(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
