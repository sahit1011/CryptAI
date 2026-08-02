# Multi-Tenancy Architecture

> **Status: DESIGN CONTRACT — not yet built.** This is the reference we build M0–M5
> against. Where it describes something that already exists in `crypto-trading-agent/src`,
> it says so explicitly. Everything else is target state. Do not read this document as a
> description of what runs today.
>
> Decided 2026-08-02. Supersedes the tenancy model described in the `multi_user.py`
> module docstring (see [What changes in existing code](#what-changes-in-existing-code)).

---

## The principle

> **Shared = objective facts about the market.
> Per-user = judgment about what to do with them.**

Facts are identical for every user, expensive to compute, and cost **O(1) in user count**.
Judgment depends on capital, risk appetite, open positions, goals, and trade history — so
it cannot be shared without becoming a lie.

Exactly one component is universal: the **Rust signal engine**. It is not an agent — no
LLM, no `user_id`, no awareness that users exist. **Every LLM agent is per-user.**

---

## Three categories

Not two. The middle category is what keeps the process count sane.

| # | Category | Runs as | Tenant-aware? |
|---|---|---|---|
| 1 | **Universal, user-blind** | 1 process, always on | No — structurally cannot be |
| 2 | **Singleton, sweeps tenant state** | 1 process, loops over tenants | Yes, but holds no per-tenant state |
| 3 | **Per-session / per-position instance** | N tasks, spawned on demand | Fully |

### Category 1 — Signal Plane (Rust, shared)

Market data ingest · indicators · **market structure detection (ICT/SMC: order blocks,
FVGs, liquidity pools, BOS/CHoCH)** · regime classification · tradability score ·
funding/OI anomalies.

All of it is a pure function of price. A fair value gap is a fair value gap regardless of
who is looking at it. This plane publishes to Redis and **never reads a `user_id`**.

### Category 2 — Singletons that sweep tenant state

Paper tick loop · exchange reconciler · monitor supervisor · session-expiry sweeper ·
daily quota reset.

One process each, iterating over tenants. Cheap, and avoids N idle processes. These read
and write per-tenant state but hold none of it between iterations.

*Partly exists today:* `src/core/paper_tick.py`, `src/core/health_monitor.py`.

### Category 3 — Per-user instances

`SessionWorker` (one per **active session**) · `PositionMonitor` (one per **open
position**) · and per-tenant resources: portfolio, risk calculator, memory handle,
exchange client.

*Partly exists today:* `UserSession` in `src/core/multi_user.py`.

---

## The boundary

### Shared — computed once, consumed by everyone

| Concern | Why it's shared |
|---|---|
| OHLCV, funding, open interest, orderbook depth | Raw facts |
| Indicators (EMA, ATR, RSI, ADX, efficiency ratio) | Pure function of price |
| Market structure (order blocks, FVGs, liquidity pools, BOS/CHoCH) | Deterministic pattern detection; user-independent |
| Regime label + tradability score | Property of the market, not the trader |
| Key levels, invalidation zones | Geometry of the chart |

### Per-user — computed per session

| Concern | Why it can't be shared |
|---|---|
| Symbol universe | Comes from user preferences |
| Setup synthesis (the LLM thesis) | Depends on risk appetite, horizon, goals |
| Tradability *for this user* | Min R:R, allowed strategies, concurrent-position cap |
| Position sizing | Capital × risk appetite. Deterministic, but per-tenant |
| Portfolio-aware filtering | Needs their existing exposure and correlation |
| Ranking | Goals, monthly PnL target vs. month-to-date actual |
| Memory retrieval | Their trades, their outcomes |
| Narrative / explanation | Their language, their context |
| Execution venue + credentials | Their exchange account |

---

## Why setup *generation* is per-user

This is the deliberate departure from the current code.

Today, `multi_user.py` computes candidate setups once and `MultiUserExecutor` books **the
same setup into every user's portfolio**. Two problems:

1. Every user receives an identical trade. The "personal agent team" is really a filter.
2. The 30-minute session meters nothing, because no user-specific compute occurs.

So the boundary moves. The Signal Plane emits a **market context object** — structure map,
key levels, liquidity pools, regime, score, invalidation zones — but **no trade decision**.
The per-user session performs the synthesis.

This produces genuinely different output, not cosmetic variation:

- **Same chart, different trade.** A conservative user gets the 1h pullback continuation
  at 2.5R; an aggressive user gets the 5m liquidity sweep at 4R.
- **Portfolio-aware.** A user already holding three BTC-correlated longs should be shown a
  short or nothing. That requires *their* book.
- **Goal-aware.** A user at 85% of their monthly target with three days left should be told
  to cut risk, not add.
- **Memory-aware.** "You have lost 4 of your last 5 trades on this pattern in this regime."

**Cost stays bounded** because synthesis is per *session cycle*, not per tick. A 30-minute
session at ~3-minute cycles is ~10 LLM syntheses. That is exactly what the session meter
is metering — which is what makes the 30-minute limit honest rather than arbitrary.

---

## Runtime shape

```
┌────────────────────────────────────────────────────────┐
│  RUST SIGNAL ENGINE            1 process · always on   │
│  no user_id anywhere           → redis: market:pulse:* │
└────────────────────────┬───────────────────────────────┘
                         │  read-only · versioned · timestamped
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌────────────────────┐          ┌─────────────────────┐
│ SESSION WORKERS    │          │ MONITOR WORKERS     │
│ 1 per ACTIVE       │          │ 1 per OPEN position │
│ session · METERED  │          │ NEVER metered ·     │
│ dies at quota end  │          │ outlives the session│
└────────────────────┘          └─────────────────────┘
         │                               │
         └───────────────┬───────────────┘
                         ▼
         ┌───────────────────────────────┐
         │ SINGLETONS                    │
         │ reconciler · paper tick ·     │
         │ quota reset · monitor supvr   │
         └───────────────────────────────┘
```

### Scaling

You need a worker per **active session**, not per registered user.

| Registered users | Concurrent sessions | Open positions | Runtime units |
|---|---|---|---|
| 1,000 | ~30 | ~50 | 80 asyncio tasks + 1 Rust process |

The naive reading of "an agent team per user" would be 1,000 × 5 = 5,000 workers. The
shared/per-user split is what buys the difference.

---

## The pulse contract

The only interface between the shared plane and the per-user plane. Versioned so the Rust
and Python sides can deploy independently.

**Keys:** `market:pulse:{symbol}` per symbol, `market:pulse:global` for the cross-market
"market is hot" signal.

```jsonc
{
  "v": 1,
  "symbol": "BTCUSDT",
  "ts": 1754092800000,          // when this pulse was computed
  "feed_ts": 1754092799850,     // newest market event it incorporates
  "regime": "trending_up",      // trending_up | trending_down | ranging | volatile_chop
  "tradability": 72,            // 0-100
  "vetoes": [],                 // non-empty => tradability is 0, reasons listed
  "factors": {                  // each 0.0-1.0, for explainability and calibration
    "trend_alignment": 0.81,
    "volatility_band": 0.64,    // hump function: too low AND too high both score poorly
    "efficiency_ratio": 0.58,
    "liquidity_window": 1.00,
    "positioning": 0.42,        // funding + OI crowding
    "book_quality": 0.90        // spread + depth
  },
  "structure": {
    "htf_bias": "bullish",
    "swing_high": 69120.5,
    "swing_low": 66840.0,
    "order_blocks": [],
    "fvgs": [],
    "liquidity_pools": [],
    "key_levels": []
  },
  "context": {
    "atr_pct": 1.34,
    "atr_percentile_30d": 0.47,
    "funding_rate": 0.00012,
    "oi_delta_1h": 0.031,
    "spread_bps": 1.2,
    "btc_correlation_30d": 0.88
  }
}
```

**Contract rules:**

- The pulse carries **facts and scores, never a trade decision**. No entry, stop, or target
  fields. Ever. That is the line that keeps synthesis per-user.
- Consumers **must** check `ts` and refuse to run if the pulse is older than the staleness
  threshold. See invariant 2.
- `v` is bumped on any breaking field change. Consumers reject unknown major versions
  rather than best-effort parsing.
- Every published pulse is also appended to the calibration log for forward-return
  scoring. A tradability score that cannot be falsified is decoration.

---

## Isolation invariants

These make the split safe rather than merely efficient. Each is testable; each should have
a test.

1. **The shared plane is read-only from the per-user plane.** A session worker can never
   write to the feature store. No cross-tenant contamination path exists structurally.
2. **Staleness is fail-closed.** If pulse data is older than the threshold, sessions refuse
   to run rather than trade on stale facts. The shared plane is a single point of failure
   for every user — treat it like one.
3. **No shared mutable state between `UserSession` objects.** One tenant's failure cannot
   reach another's.
4. **Per-session token budget, enforced fail-closed.** Bounds the noisy-neighbour LLM cost
   problem. The minute quota is the product; the token cap is the safety net.
5. **Every DB query filters `user_id` in application code.** The backend connects as a
   privileged role that **bypasses RLS**, so `scripts/sql/rls_trades.sql` will *not* catch
   a missing filter on the backend path. The application layer is the only guard. A missing
   filter is a launch blocker, not a bug.
6. **Credentials flow vault → exchange client only.** Never into logs, cache, LLM context,
   error messages, or the pulse.
7. **Redis keys are namespaced by `user_id`** for everything in the per-user plane. The
   shared plane's keys are deliberately un-namespaced — that asymmetry is the tenancy
   boundary made visible.
8. **Monitoring is unmetered and unconditional.** A quota expiring while a position is open
   must never stop the monitor. This is a money-safety property, not a billing one.
9. **Amounts are integer minor units and currency-tagged.** Delta India and CoinDCX settle
   some products in INR; a USDT assumption is a correctness bug, not a display bug.

---

## Lifecycle interaction

Sessions and positions have **independent lifetimes**, and this is deliberate:

```
session start ──▶ SCANNING ⏱ ──▶ SETUP_PROPOSED (clock PAUSES)
                                   │
                 [auto] ───────────┼──▶ EXECUTING ──▶ position opens
                 [manual] approval ┘                      │
                                                          ▼
session may END (quota exhausted)          MONITOR RUNS ON — unmetered,
        │                                  survives session end, process
        ▼                                  restart, and deploy
    worker torn down                              │
                                            position closes
                                                  │
                                            monitor torn down
```

A monitor outliving its session is the normal case, not an edge case. It is why monitors
are a separate category-3 instance rather than a phase of the session worker.

---

## What changes in existing code

| Component | Change |
|---|---|
| `src/core/multi_user.py` — `MultiUserExecutor` | Narrows from "book one shared setup into every user" to **execution routing only** |
| `src/core/multi_user.py` — `UserSession` | Widens: gains preferences, session clock, memory handle, and the agent pipeline. Becomes the single per-tenant unit |
| `src/core/orchestrator.py` — `detect_regime` node | **Removed** from the per-user graph. Regime arrives from the shared pulse. Straight cost saving — it is currently recomputed per user |
| `src/core/orchestrator.py` — graph entry | Becomes **pulse-gated**: do not spend a metered cycle when tradability is vetoed |
| `src/security/credential_vault.py` | Unchanged in shape; this document is the reference its docstring points at |
| New | `signal-engine/` (Rust), `SessionManager`, `UserPreferences`, `Proposal`, `PulseClient` |

---

## Open risks

1. **Shared-plane outage stalls every user.** Mitigated by invariant 2 (fail-closed
   staleness) — users see an honest "market data unavailable" state rather than trading on
   stale facts. Accepted, but it means the signal engine's uptime is the product's uptime.
2. **Basis risk.** The pulse is computed from Binance data; execution happens on
   CoinDCX/Delta. The signal fires on one venue's price and fills at another's. Requires a
   per-venue price sanity gate immediately before every order.
3. **CoinDCX testnet availability is unverified.** If no futures testnet exists, adapter
   validation falls back to recorded-fixture mocks plus read-only live calls. Resolve in M0
   before committing to the M4 validation strategy.
4. **Common-universe limitation.** Shared analysis covers ~20 liquid perps. A user wanting
   a symbol outside it needs an on-demand deep-dive charged against their session. Not yet
   designed.
