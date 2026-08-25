# Launch readiness — can a new user actually use this?

**Audited 2026-08-25** by tracing every step from a live entrypoint
(`src/api/server.py` / `src/multi_user_daemon.py`), not from file existence. This
document is the answer to "my friend wants to try it — will it work?"

Verified against production: Render tracks `fix/m1-foundation-bugs` with autoDeploy,
live commit at audit time `8c47003`; Vercel `cryptai` last deployed 2026-08-25.
Prod flags: `SIGNAL_PLANE_ENABLED=true`, `USE_TESTNET=true`,
`LIVE_TRADING_CONFIRMED=false`, `RUN_SIGNAL_ENGINE_IN_API=true`,
`OPENROUTER_API_KEY` set, `ENABLE_EXECUTION` **not set at all**.

Legend: ✅ works · ⚠️ works with caveats · ❌ missing/broken

---

## The journey

| Step | State | Notes |
|---|---|---|
| Google sign-in / sign-up | ✅ | Supabase OAuth → `/auth/callback` → `/dashboard` → `/desk` |
| JWT → user_id | ⚠️ | JWKS verify accepts **ES256/RS256 only** (`server.py:151`). A Supabase project still issuing legacy **HS256** tokens 401s on every per-user call, and the UI degrades quietly into an empty shell. **Check the project's JWT signing keys before inviting anyone.** |
| New-user rows | ✅ | Created on demand; nothing needs manual seeding. A $10k paper desk seeds on first portfolio read |
| Onboarding — trading mode | ✅ | Persists on click via `POST /api/settings` |
| Onboarding — exchange connect | ⚠️ | Full path works incl. a real testnet auth probe. If `VAULT_ENC_KEY` is unset the user gets a bare 500 *after* their keys already validated |
| Onboarding — capital / risk / monthly target | ❌ | **Onboarding is only 2 steps.** `trading_capital` has **no UI field anywhere** yet it sizes every position (`proposals.py:136`). Risk appetite reaches the LLM prompt but maps to **no numeric cap** |
| First-run redirect into onboarding | ⚠️ | Client-side 4s race that **fails open** against a backend that cold-starts in ~1 min. First-ever load likely skips onboarding silently; `/chart` has no check at all |
| Market-activity ("hot hour") signal | ✅ | `GET /api/pulse` + badge on `/desk` and the chart footer. Measured rank is past-tense with its sample; live half degrades to explicit UNKNOWN |
| Session start + quota | ⚠️ | Enforced, but see **Quota** below — it is not what the product promises |
| Live AI insight during a session | ⚠️ | Genuinely wired: session → worker → shared analysis → LLM synthesis → sized proposal → card → approve → **revalidate at live price** → book. Caveat: the first 1–2 cycles usually return "no qualifying setups" while `SharedSetupCache` warms, burning 3–6 of the 30 minutes |
| Manual mode | ⚠️ | Sees setups, executes via `/api/execute-setup`. **Inconsistency:** a manual user *with keys* books to **paper** on approve but **live** via execute-setup |
| Auto mode, no keys | ✅ | Isolated paper desk, self-managing SL/TP legs, monitored, survives restart |
| Auto mode, with keys | ⚠️ | Real testnet orders placed. **Live positions are unmonitored and unrehydrated** — see blockers |
| Real money | ✅ blocked | `LIVE_TRADING_CONFIRMED=false` forces testnet, and `/api/exchange-keys` rejects non-testnet keys. Two independent layers |
| Monitoring | ⚠️ | Paper: time stops, profit protection, restart-durable, `/api/monitors` honest. **Live: none** |

---

## Quota: what's built ≠ what's promised

The product says **2 sessions/day × 30 min**. The code has
`DEFAULT_DAILY_QUOTA_SECONDS = 1800` — **one pooled 30 minutes per day**, unlimited
sequential sessions (one concurrent). `billing/plans.py` has **no quota field**, and
the daemon builds `SessionManager(db_url)` bare, so **every tier gets the same 30
minutes**. Plans only feed risk sizing.

Slots are spent on **metered time while scanning** — not on session start, and not on
proposal delivery (the roadmap's R2.2 redesign, unstarted). Describe it as "30 minutes
of scan time per day" until R2.2 lands, or it's a false claim.

---

## Fixed 2026-08-25 (this audit)

1. **Paper users were traded without asking.** `paper` is the default mode and the
   fan-out is driven by a deployment-*global* "is anybody scanning" signal, so one
   user's session booked trades into every other paper user's desk. Now `paper` is
   session-gated per user; `auto` still books continuously. `tests/test_consent_gates.py`
2. **`mode=off` didn't stop `/api/execute-setup`.** It never read `trading_mode`, so
   "off" meant "the daemon won't auto-trade you", not "don't trade my account". Now 409s.
3. **`plan.allow_live` was decorative** — defined, unit-tested, read nowhere. Any
   free-tier user could set themselves to `auto`. Now enforced at `POST /api/settings`,
   failing closed when the plan can't be resolved.
4. **The activity badge was unreachable.** Shipped only in the chart footer, two nav
   clicks from the landing route and hidden below `md`. Now on `/desk` too, sharing one
   tested interpretation module so the two can't disagree.

---

## Blockers before real users

**P0 — live positions are unmonitored and unrehydrated.**
`LiveExecutionEngine.get_positions()` returns `[]`, and monitor discovery plus
rehydration are both position-driven. An auto+keys position has no time stop, no
profit protection, and vanishes from the engine's view on restart. The code already
logs this (`monitor_worker.py:466`). Either implement `get_positions()` or refuse
`auto` while keys are attached.

**P0 — the money path is the least-tested code.**
`test_deterministic_risk_calculator`, `test_exchange_client`, `test_execution_agent`
and `test_emergency_exit` are all **quarantined**. That is the sizing gate, order
placement, and panic exit. The session-plane tests are healthy — the coverage hole is
precisely where money moves. Per this repo's own `test_order_manager` lesson, read
each failure before assuming staleness.

**P1 — the docs claimed two execution gates; there is one.**
`ENABLE_EXECUTION` is dead code on both live entrypoints and unset in production. Only
`LIVE_TRADING_CONFIRMED` + the testnet-only key gate hold. Corrected in `CLAUDE.md`.

**P1 — the order-book poller has no venue fallback.**
Klines fall back to Bybit (`signal-engine/src/venue.rs`) but the book and funding
pollers are Binance-only. During a shared-IP ban the plane reports *available* while
every symbol is vetoed on spread — so sessions produce nothing. Observed live.

**P1 — capital is unaskable and un-editable** yet sizes every position (default
$10,000). A user with ₹50k or $500k gets positions sized for a number nobody asked
them for.

**P1 — "risk appetite" is decorative for anything numeric.** It reaches the LLM prompt
but never maps to `max_risk_per_trade_pct`, `max_leverage`,
`max_concurrent_positions`, or `max_daily_trades` — none of which the UI can set.
Choosing "aggressive" changes one prompt line while the real caps stay conservative.

**P2 — onboarding is bypassable and fails open** (see the table). Consequence chain is
silent: no settings row → `onboarded=false` → excluded from `active_user_ids()` → the
practice desk does nothing, with no error anywhere.

**P2 — dead LLM cycles at session start** burn 3–6 of the user's 30 minutes.

**P2 — no automated coverage of signup → onboarding → first dashboard.** The e2e suite
logs in as a pre-seeded user and navigates routes deleted in the Aug-12 refactor.

---

## Operational facts that bite

- **Deploys are expensive.** Each push rebuilds the Rust engine in Docker; 20 deploys
  across 2026-08-24/25 plausibly drove the bandwidth alert. Runtime traffic is fine
  (measured flat 6 MB/h ≈ 144 MB/day against a 167 MB/day budget). **Batch deploys.**
- **Only ONE always-on free service may run in this Render workspace.** `klaro-backend`
  was found unsuspended on 2026-08-25 — two always-on services is ~1,460 instance-hours
  against a ~750h allowance, which is exactly what caused the Aug-10 suspension.
- **A boot-time Binance 418 is normal** and self-heals; measured worst case 1h42m
  before the Bybit fallback existed, seconds after.
- **Vercel does not auto-deploy** from the active branch. `npx vercel ls cryptai`
  before claiming any UI change is live.
