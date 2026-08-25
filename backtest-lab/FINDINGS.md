# Lab findings ledger

Committed conclusions only — raw trade CSVs and per-run summaries live in
`results/` (gitignored, regenerable). Every entry states what was run, what it
showed, and what it does NOT license.

---

## 2026-08-25 — S1 entry-confirmation A/B (v1, defaults, no sweeps)

**Setup:** 2024-08→2026-07, BTC/ETH/SOL USDT-M perps. Location = 0.705–0.886
retracement of the last confirmed 1h fractal impulse; confirmation = absorption →
dominance flip on 1m taker-delta (`crypto-trading-agent/src/strategy/s1_signals.py`,
default `S1Params`, the exact shipped code). Brackets 1.5R/2R, 8h time stop, taker
fees 5bps/side, zero slippage, one event at a time per symbol. ~2,970 touch events,
~25% confirmation rate. Same-bar stop/target ambiguity: tested both resolutions —
**zero difference** (never co-occurs at these widths), so that bias is not a caveat.

**Pooled result (avg net R per trade):**

| arm | entry | stop | 1.5R | 2R | n |
|---|---|---|---|---|---|
| control_all (product today) | band edge at touch | invalidation edge | −0.268 | −0.290 | 2,974 |
| control_confirmed (**oracle**) | band edge at touch | invalidation edge | **−0.139** | −0.173 | 730 |
| treatment | flip close | behind absorption low | −0.473 | −0.501 | 730 |
| treatment_wide | flip close | invalidation edge | −0.325 | −0.335 | 730 |
| treatment_retest | edge, after confirmation | invalidation edge | −0.430 | −0.437 | 583 |

**Findings:**

1. **The confirmation signal carries real information.** Touches that later confirm
   outperform the full set by **+0.13R** (43.6% vs 38.2% win at 1.5R), consistent
   across all three symbols and both directions. Absorption-then-flip *identifies
   better touches*.
2. **No implementable execution captures it.** The oracle arm needs a fill at the
   edge conditioned on FUTURE confirmation. Waiting for the flip and paying up loses
   the edge advantage (−0.33); a tight stop behind the absorption low sits inside 1m
   noise and doubles fee drag in R terms (−0.47); resting a limit back at the edge
   after confirmation fills 80% of the time but adversely selects — the retest *is*
   the failure signal (−0.43). The +0.13R is the price of the information.
3. **Every arm is net negative at defaults.** The mechanical location layer alone
   (1h fib band, no environment gate) does not clear taker fees at 1.5–2R intraday.
   This matches the champion's own structure: he trades stage 1 (regime) and a
   narrow session window FIRST — v1 deliberately tested without that stage.

**What this licenses / forbids:**

- ✅ Use `confirm_entry` as a proposal-quality **score/filter input** (it has
  information) — e.g. S2 proposals at a zone gain a "confirmed flow" annotation.
- ❌ Do NOT wire S1 as a live entry trigger. The `S1_ENABLED` flag stays false.
- Next (v2, pre-registered to avoid a forking-paths garden — run EXACTLY these):
  1. add the **environment stage**: gate touches by a realized-vol/participation
     regime proxy (the offline stand-in for the live tradability pulse), and
     separately by session window (NY open hours);
  2. re-price fees for **maker entries** at the edge (2bps or rebate vs 5bps);
  3. nothing else — no threshold sweeps until (1)+(2) pick a lane.

Runs: `results/s1_ab_summary_{pessimistic,optimistic}.md` (regenerate with
`study_s1_ab.py`; `SAME_BAR=optimistic` for the bound check).

---

## 2026-08-25 — S1 A/B v2: pre-registered environment gates + maker/taker fees

**Setup:** exactly the three changes v1 pre-registered, nothing else — no sweeps, no
new arms. Same v1 event stream (2,974 touches, identical per-symbol counts 991/1023/960,
same brackets/time stop/pessimistic same-bar; `study_s1_ab_v2.py` imports v1's
enumeration and bracket walk, so exits are bit-identical and only pricing/filtering
changed). (1) Three binary gates at the touch bar, past data only: `G_vol` (trailing
24h realized vol inside the P25–P75 of its own trailing 30-day hourly-sampled
distribution; fails closed on <30d history), `G_part` (shipped `participation_ok` at
the touch), `G_session` (touch in 13:30–16:30 UTC). (2) Maker/taker fees by how each
fill executes: edge entries + target exits maker 2bps; flip entries, stops, time-stops
taker 5bps. (3) Report matrix: {baseline, each gate alone, all three} × the 5 arms.
Gates filter the fixed baseline event stream.

**Gate survival:** G_vol 46.0% (1,368 events) · G_part 87.4% (2,600) · G_session
17.1% (510) · all three 8.1% (240).

**Pooled baseline (v1 events, new fee model — avg net R):**

| arm | 1.5R | 2R | n |
|---|---|---|---|
| control_all | −0.159 | −0.188 | 2,974 |
| control_confirmed (oracle) | −0.024 | −0.066 | 730 |
| treatment | −0.432 | −0.468 | 730 |
| treatment_wide | −0.301 | −0.317 | 730 |
| treatment_retest | −0.326 | −0.337 | 583 |

**Pooled all-three gates (avg net R):**

| arm | 1.5R | 2R | n |
|---|---|---|---|
| control_all | −0.033 | −0.041 | 240 |
| control_confirmed (oracle) | **+0.339** | +0.238 | 55 |
| treatment | −0.303 | −0.354 | 55 |
| treatment_wide | −0.186 | −0.174 | 55 |
| treatment_retest | −0.277 | −0.352 | 38 |

**Findings:**

1. **Maker repricing alone recovers ~0.10–0.11R on edge-entry arms** (control_all
   −0.268 → −0.159; oracle −0.139 → −0.024) and much less on flip arms (treatment
   −0.473 → −0.432, still paying taker in). Nothing implementable clears zero on fees
   alone.
2. **The session window is the decisive gate.** G_session alone: oracle goes positive
   (+0.110 at 1.5R, n=100), control_all improves to −0.145, and touches cluster in the
   window (17.1% survive vs 12.5% if uniform). G_vol alone is a mild positive filter
   (control_all −0.112, oracle +0.023, n=329). **G_part alone does nothing at event
   level** (control_all −0.165 vs −0.159 baseline, i.e. a hair worse on 87% survival) —
   its value in v1 was inside confirmation, not as an event gate.
3. **Under all three gates, the oracle clears zero for the first time: +0.339 ± 0.171
   (se) at 1.5R** — but n=55 over 24 months × 3 symbols (~2.3/month), t≈2.0, and it is
   one cell in a 5-config × 5-arm × 2-target matrix; that is one modest-significance
   cell among 50, on the arm that needs a fill conditioned on FUTURE confirmation.
4. **No implementable arm clears zero anywhere in the matrix.** Best is control_all
   under all three gates at −0.033 ± 0.082 (t=−0.40): statistically indistinguishable
   from zero — and from modestly negative. Total, not per-trade: −7.9R over 24 months
   at ~10 trades/month. The flip-entry arms stay decisively negative in every config
   (−0.17 to −0.35 gated); the environment stage does not rescue paying up at the flip.
5. Directionally consistent with v1's mechanism story: gates + maker fees closed ~87%
   of control_all's baseline deficit (−0.268 → −0.033) but the oracle-vs-implementable
   gap (~+0.37 under all three) is still the un-capturable price of the confirmation
   information.

**What this licenses / forbids:**

- ✅ Use the environment stage (session window first, vol regime second) as
  **proposal-context/scoring inputs** alongside v1's confirmed-flow annotation — both
  now have event-level evidence of positive selection.
- ❌ Do NOT wire S1 as a live entry trigger. `S1_ENABLED` stays false. Nothing
  implementable cleared zero — a ~breakeven-at-best config is not a product.
- ❌ Do NOT treat the +0.34R oracle cell as a strategy: one pre-registered
  configuration, n=55, non-implementable entry. If anything is pursued it is
  walk-forward + held-out validation of the gated config (and an honest attempt at an
  implementable capture under the gates), not shipping.
- ❌ Still no threshold sweeps; v2 spent the pre-registered budget. Any v3 must be
  pre-registered the same way before it runs.

Runs: `results/s1_ab_v2_summary.md`, `results/s1_ab_v2_trades.csv` (regenerate with
`study_s1_ab_v2.py`; requires v1's `study_s1_ab.py` unchanged, pessimistic same-bar).

---

## 2026-08-25 — Intraday activity profile (measured; earns the "hot window" badge)

**Setup:** all 3,153,600 1m bars (BTC/ETH/SOL, 2024-08→2026-07). For each UTC hour,
the mean of per-symbol z-scores of (mean 1m volume, mean 1m range/price) — per-symbol
z-scoring so a high-notional symbol cannot dominate the shape. Backward-looking
measurement only; `study_hour_profile.py` emits no forecast and the API exposes none.

**Result — top 6 UTC hours are 13,14,15,16,17,18** (18:30–23:30 IST), peaking at
14:00 UTC (19:30 IST, z=+2.70) and 15:00 UTC (z=+2.21). Quietest: 04:00–06:00 UTC
(09:30–11:30 IST, z≈−0.95). Per-year agreement with those six hours: **5.67 (2024),
6.00 (2025), 5.67 (2026)** out of 6 — the shape is stable, not an artifact of one
regime.

**Findings:**

1. The profile is stable enough to state publicly as a past-tense fact. A badge saying
   "this hour has historically been the Nth most active of 24 (3.15M bars, 2024-08→
   2026-07)" is checkable and sourced; anything about the NEXT hour is not, and is
   not exposed by `/api/pulse`.
2. **Independent corroboration of v2's session gate.** The v2 A/B found `G_session`
   (13:30–16:30 UTC) the decisive environment gate; this volume/range measurement,
   computed from a different statistic on the same bars, puts its top window at 13:00–
   18:00 UTC. Two different analyses agreeing raises confidence that the session
   effect is real, even though v2 showed no implementable entry captures it.
3. **Corrects the plan's assumed window.** The 2026-08-24 product plan pencilled the
   session-liquidity schedule at 17:30–20:30 IST. Measured, the active window is
   18:30–23:30 IST — roughly 1–3h later than assumed, and the assumed window's first
   hour (17:30 IST = 12:00 UTC) actually ranks 10th of 24. Free-tier session slots
   should be steered by the measured window, not the assumed one.

**What this licenses / forbids:**

- ✅ Ship the measured rank as a past-tense, sourced badge (`GET /api/pulse` → `hour`).
- ✅ Use the measured window when scheduling/nudging free-tier session slots.
- ❌ No forward "hottest hour" claim, no "expected activity", no countdown to a hot
  window. The artifact ships with its caveat string and the API carries it through.
- ❌ Do not regenerate the artifact silently: it is a dated measurement. Re-run
  `study_hour_profile.py` deliberately, and update the date range everywhere it shows.

Runs: `results/hour_profile.{json,md}`; shipped artifact
`crypto-trading-agent/src/signals/hour_profile.json`.
