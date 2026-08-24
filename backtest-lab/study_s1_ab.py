"""S1 entry-confirmation A/B — does absorption-then-flip beat entering at the touch?

Three arms per band-touch event (see README.md):
  control_all        enter at the band edge on every touch (the product today)
  control_confirmed  the same touch-entry, restricted to touches that later confirmed
  treatment          enter at the flip close, stop behind the absorption low

The location machinery (1h fractal swing -> 0.705-0.886 retracement band) and the
confirmation grammar are imported from the BACKEND source — the lab validates the
code that ships. Bracket resolution is deliberately pessimistic: a 1m bar that spans
both stop and target counts as a stop.

Run:  crypto-trading-agent/.venv/bin/python backtest-lab/study_s1_ab.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent"))
sys.path.insert(0, os.path.dirname(__file__))

from data_loader import load  # noqa: E402
from src.strategy.s1_signals import (  # noqa: E402
    S1Params,
    confirm_entry,
    discount_band,
    latest_swing,
)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
PARAMS = S1Params()
SWING_WINDOW_1H = 200      # trailing 1h bars fed to latest_swing
WARMUP_1H = SWING_WINDOW_1H + 10
R_TARGETS = (1.5, 2.0)
TIME_STOP_BARS = 480       # 8h on 1m bars — S1 is intraday by definition
TAKER_FEE = 0.0005         # per side
PRE_TOUCH_BARS = 80        # context handed to confirm_entry (>= baseline_bars)
RETEST_WINDOW_BARS = 60    # how long the post-confirmation limit rests at the edge
# Same-bar ambiguity: "pessimistic" counts a bar spanning both stop and target as a
# stop; "optimistic" as a target. Truth is between the two runs' results.
SAME_BAR = os.getenv("SAME_BAR", "pessimistic")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def bars_as_dicts(m: dict, start: int, end: int) -> list:
    keys = ("open", "high", "low", "close", "volume", "taker_buy_volume")
    cols = {k: m[k][start:end] for k in keys}
    return [{k: float(cols[k][i]) for k in keys} for i in range(end - start)]


def resolve_bracket(m: dict, entry_idx: int, entry: float, stop: float, r_mult: float,
                    direction: str) -> dict | None:
    """Walk 1m bars after entry until stop/target/time-stop. Pessimistic on same-bar."""
    n = len(m["open_time"])
    if entry_idx + 1 >= n:
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    target = entry + r_mult * risk if direction == "long" else entry - r_mult * risk
    end = min(n, entry_idx + 1 + TIME_STOP_BARS)
    lows, highs = m["low"][entry_idx + 1: end], m["high"][entry_idx + 1: end]

    if direction == "long":
        stop_hits, tp_hits = lows <= stop, highs >= target
    else:
        stop_hits, tp_hits = highs >= stop, lows <= target
    s = int(np.argmax(stop_hits)) if stop_hits.any() else None
    t = int(np.argmax(tp_hits)) if tp_hits.any() else None

    if s is None and t is None:
        exit_idx, exit_price, reason = end - 1, float(m["close"][end - 1]), "time"
    else:
        stop_wins = t is None or (s is not None and (s < t or (s == t and SAME_BAR == "pessimistic")))
        if stop_wins:
            exit_idx, exit_price, reason = entry_idx + 1 + s, stop, "stop"
        else:
            exit_idx, exit_price, reason = entry_idx + 1 + t, target, "target"

    sign = 1.0 if direction == "long" else -1.0
    gross = sign * (exit_price - entry)
    fees = TAKER_FEE * (entry + exit_price)
    return {
        "exit_index": exit_idx, "exit_reason": reason,
        "net_r": (gross - fees) / risk, "fee_r": fees / risk,
        "bars_held": exit_idx - entry_idx,
    }


def run_symbol(symbol: str) -> list:
    h, m = load(symbol, "1h"), load(symbol, "1m")
    h_open_time, m_open_time = h["open_time"], m["open_time"]
    trades = []
    armed = None          # {"key", "direction", "entry_edge", "invalidation", "consumed"}
    busy_until = 0        # 1m index before which no new event may start (non-overlap)
    touches = confirmed = 0

    for hi in range(WARMUP_1H, len(h_open_time) - 1):
        window = bars_as_dicts(h, hi - SWING_WINDOW_1H + 1, hi + 1)
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
                # arm only while price is still on the right side of the band
                fresh = entry_edge is not None and (
                    close > entry_edge if direction == "long" else close < entry_edge
                )
                armed = {"key": key, "direction": direction, "entry_edge": entry_edge,
                         "invalidation": invalidation, "consumed": not fresh}

        if not armed or armed["consumed"]:
            continue

        # scan the NEXT hour's 1m bars for a touch of the armed band
        t0 = int(h_open_time[hi]) + 3_600_000
        g0 = int(np.searchsorted(m_open_time, t0))
        g1 = int(np.searchsorted(m_open_time, t0 + 3_600_000))
        d = armed["direction"]
        for g in range(max(g0, busy_until, PRE_TOUCH_BARS), g1):
            close_g = float(m["close"][g])
            if (d == "long" and close_g < armed["invalidation"]) or (
                d == "short" and close_g > armed["invalidation"]
            ):
                armed["consumed"] = True  # band died untouched-side-first
                break
            hit = m["low"][g] <= armed["entry_edge"] if d == "long" else m["high"][g] >= armed["entry_edge"]
            if not hit:
                continue

            armed["consumed"] = True
            touches += 1
            edge, inval = armed["entry_edge"], armed["invalidation"]
            buffer = PARAMS.stop_buffer_frac * edge
            ctl_stop = inval - buffer if d == "long" else inval + buffer

            tape = bars_as_dicts(m, g - PRE_TOUCH_BARS, min(len(m_open_time), g + PARAMS.confirm_window_bars + 5))
            entry_ev = confirm_entry(tape, PRE_TOUCH_BARS, d, PARAMS, invalidation_price=inval)

            event_rows = []
            for r_mult in R_TARGETS:
                ctl = resolve_bracket(m, g, edge, ctl_stop, r_mult, d)
                if ctl:
                    event_rows.append({"arm": "control_all", "r_mult": r_mult, **ctl})
                if entry_ev:
                    ge = g - PRE_TOUCH_BARS + entry_ev.entry_index
                    trt = resolve_bracket(m, ge, entry_ev.entry_price, entry_ev.stop_price, r_mult, d)
                    if trt:
                        event_rows.append({"arm": "treatment", "r_mult": r_mult, **trt})
                    # v1 verdict: absorption-low stops sit inside 1m noise and fee drag
                    # scales with 1/risk — so isolate entry timing at CONSTANT stop:
                    # same flip-close entry, structural (invalidation-edge) stop.
                    wide = resolve_bracket(m, ge, entry_ev.entry_price, ctl_stop, r_mult, d)
                    if wide:
                        event_rows.append({"arm": "treatment_wide", "r_mult": r_mult, **wide})
                    # the implementable oracle: confirm FIRST, then rest a limit back at
                    # the band edge and trade only if the retest fills. Same entry price
                    # as control_confirmed, but knowable in real time.
                    rt_end = min(len(m_open_time), ge + 1 + RETEST_WINDOW_BARS)
                    if rt_end > ge + 1:
                        seg = m["low"][ge + 1: rt_end] if d == "long" else m["high"][ge + 1: rt_end]
                        refill = seg <= edge if d == "long" else seg >= edge
                        if refill.any():
                            gf = ge + 1 + int(np.argmax(refill))
                            rt = resolve_bracket(m, gf, edge, ctl_stop, r_mult, d)
                            if rt:
                                event_rows.append({"arm": "treatment_retest", "r_mult": r_mult, **rt})
                    if ctl:
                        event_rows.append({"arm": "control_confirmed", "r_mult": r_mult, **ctl})
            if entry_ev:
                confirmed += 1
            for row in event_rows:
                trades.append({"symbol": symbol, "direction": d, "touch_ts": int(m_open_time[g]), **row})
            if event_rows:
                busy_until = max(r["exit_index"] for r in event_rows) + 1
            break

    print(f"{symbol}: touches={touches} confirmed={confirmed} "
          f"({100 * confirmed / max(1, touches):.1f}%) trade-rows={len(trades)}")
    return trades


def summarize(trades: list) -> str:
    lines = ["| arm | R target | n | win% | time-stop% | avg net R | median bars held |",
             "|---|---|---|---|---|---|---|"]
    groups = defaultdict(list)
    for t in trades:
        groups[(t["arm"], t["r_mult"])].append(t)
    for (arm, r_mult) in sorted(groups):
        g = groups[(arm, r_mult)]
        wins = sum(1 for t in g if t["exit_reason"] == "target")
        timeouts = sum(1 for t in g if t["exit_reason"] == "time")
        avg_r = sum(t["net_r"] for t in g) / len(g)
        med_bars = sorted(t["bars_held"] for t in g)[len(g) // 2]
        lines.append(f"| {arm} | {r_mult} | {len(g)} | {100 * wins / len(g):.1f} "
                     f"| {100 * timeouts / len(g):.1f} | {avg_r:+.3f} | {med_bars} |")
    return "\n".join(lines)


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_trades = []
    for sym in SYMBOLS:
        all_trades.extend(run_symbol(sym))

    import csv
    with open(os.path.join(RESULTS_DIR, f"s1_ab_trades_{SAME_BAR}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
        w.writeheader()
        w.writerows(all_trades)

    pooled = summarize(all_trades)
    per_symbol = "\n\n".join(
        f"### {sym}\n" + summarize([t for t in all_trades if t["symbol"] == sym])
        for sym in SYMBOLS
    )
    per_direction = "\n\n".join(
        f"### {d}\n" + summarize([t for t in all_trades if t["direction"] == d])
        for d in ("long", "short")
    )
    md = (f"# S1 A/B results (defaults, no sweeps)\n\nFees {TAKER_FEE * 1e4:.0f}bps/side, "
          f"time stop {TIME_STOP_BARS}m, same-bar = {SAME_BAR}, zero slippage all arms.\n\n"
          f"## Pooled\n{pooled}\n\n## By symbol\n{per_symbol}\n\n## By direction\n{per_direction}\n")
    with open(os.path.join(RESULTS_DIR, f"s1_ab_summary_{SAME_BAR}.md"), "w") as f:
        f.write(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
