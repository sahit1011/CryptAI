# Memo — the Robbins Cup orderflow strategy vs CryptAI (2026-08-24)

Source: youtu.be/PL7LKUsCgIQ ("Trading WORLD CHAMPION Reveals the Orderflow Strategy…").
Trader identified: **Chris Creamer** (@thraxxtrades), Robbins World Cup **Micro Day-Trading
division monthly winner** (~100% that month, micro account, self-reported 60–65% win rate).
Transcript unreachable; reconstruction from a transcript-derived summary + corroborating
search. **Steal principles, not authority** — a monthly micro-division win is real but thin.

## His method (reconstructed)

1. **Environment** — classify the day via options gamma exposure (GEX): positive gamma →
   fade moves; negative → moves amplify. Trades MNQ, first ~90 min of NY open.
2. **Location** — longs only from *discount* (deep Fib band 0.705/0.788/0.886); close
   beyond 0.886 invalidates.
3. **Confirmation** — 5-minute orderflow trigger: **absorption** (aggressive sellers hit the
   low, price refuses to go lower — effort without result) then a **dominance flip**. Enter
   on the flip, never on the level touch.
4. **Risk** — stop behind the failed sellers; targets at swings/POC/walls, 1.5–2R; **hard
   participation filter** (no trades under 20k contracts/5-min); **shutdown after 2 losses**.

## Mapping to our stack

| Element | Status in CryptAI |
|---|---|
| Environment gate before any trade | **HAVE** — it *is* the validated tradability NOW-cast (scoring.rs) |
| Participation (volume) floor | **PARTIAL** — depth veto + liquidity_window exist; no *realized-volume* veto |
| Discount-zone location (deep retracement) | **HAVE** — OTE zones (literally the 0.705–0.79 band), OBs, FVGs in strategy_agent; unvalidated per FINDINGS §6 |
| Stop at invalidation, 1.5–2R | **HAVE** — RR floor 1.5, recomputed not trusted |
| Absorption / dominance-flip entry trigger | **ABSENT** — proposals fill at the level with no flow confirmation |
| GEX regime | **ABSENT**; the crypto analog (funding/OI crowding) = our unmeasured `positioning` factor |
| 2-loss shutdown | **HAVE in code** (circuit_breaker.py) — verify wiring from the entrypoint |
| Gamma-sign → fade/trend direction | **CONTRADICTS our evidence** — regime→direction refuted out-of-sample |
| 5-min day-trading cadence | **CONTRADICTS** — scalp horizon failed validation; India's 1% TDS kills the economics |

## Worth stealing (ranked)

1. **Realized-volume participation veto.** His hardest rule, and exactly our validated
   product shape (a NOW-cast veto). Kline volume is already ingested: one new veto, zero
   new bandwidth, immediately falsifiable via pulse_snapshots.
2. **Environment → location → confirmation ordering.** We have stages 1 and 2. Stage 3 —
   a proposal *arms* only on confirmation instead of filling at the level touch — slots
   cleanly into the per-user synthesis layer.
3. **Absorption as that confirmation — via the free proxy first.** Binance klines already
   carry **taker-buy volume** → per-candle aggressor delta (≈ 2×takerBuy − total) from data
   we already fetch. Candle-level absorption detection at zero marginal bandwidth.
4. **Positioning calibration priority.** His GEX regime is dealer positioning; ours is
   funding+OI — already a factor, empirically unmeasured. Argues for calibrating it once
   live data flows, not for buying options data.
5. **Codified tilt control.** Consecutive-loss + daily-loss breakers exist — verify wiring,
   surface per-user.

## Do NOT adopt

- **His timeframe.** 5-min triggers are the scalp horizon our own eval refuted, and 1% TDS
  makes the economics negative for Indian users regardless of edge. Import the *ordering*,
  not the cadence — keep the 4–12h horizon.
- **GEX regime→direction.** The exact claim our walk-forward refuted, plus a paid options
  feed for an unproven edge — the cost law violated twice.
- **Always-on aggTrade tick streams** (~1–5 GB/day/symbol — 10–30× the entire budget). If
  the free proxy validates, a **demand-gated aggTrade burst** (subscribe only while a
  specific proposal is inside its entry window; consumer = that proposal) costs ~10–20 MB
  per window — lawful under the cost law.
- **His performance numbers as evidence.** Nothing ships without falsifiable
  pulse_snapshots evidence — same bar as everything else.

## Cheapest experiment (paper desks, zero new streams)

A/B on entry confirmation. Control: proposals fill at the level (today). Treatment:
proposal arms only when the 1m taker-buy-delta proxy shows absorption-then-flip at the
level. Log both arms' MAE, fill quality, and 4–12h forward return into proposals +
pulse_snapshots. ~2 weeks of paper data decides. If the free proxy shows nothing, the
tick-level version isn't worth its bandwidth either.

**Sequencing suggestion:** the volume veto fits R1.5's calibration work; the
absorption-proxy A/B is a natural R3-era experiment once proposals flow on live pulses.
