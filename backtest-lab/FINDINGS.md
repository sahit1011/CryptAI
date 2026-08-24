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
