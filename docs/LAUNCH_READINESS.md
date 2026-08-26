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
| Auto mode, with keys | ⚠️ | Real testnet orders placed; positions now visible to the monitor via a venue refresh. Remaining caveat: monitor coverage depends on that refresh succeeding, and a stale cache reports *unknown* by design |
| Real money | ✅ blocked | `LIVE_TRADING_CONFIRMED=false` forces testnet, and `/api/exchange-keys` rejects non-testnet keys. Two independent layers |
| Monitoring | ⚠️ | Paper: time stops, profit protection, restart-durable. Live: positions now discovered from the venue (120s cache, honest `unknown` when stale). `/api/monitors` truthful in both |

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

**~~P0 — live positions are unmonitored and unrehydrated.~~ CLOSED 2026-08-25.**
`LiveExecutionEngine.get_positions()` was a stub returning `[]` while the venue had
the data all along (`ExchangeClient.get_open_positions`). Now `refresh_positions()`
pulls the venue and caches it in the SAME shape the paper engine publishes, so the
monitor and dashboard need no per-engine special case. Refreshed on the tick loop's
slow heartbeat (not every 3s — that would be ~1,200 venue calls/hour/user for data
that only changes on fills), and once at boot so a restart mid-position is not a blind
window. Live rehydration now reconciles from the VENUE rather than skipping outright —
the venue is the source of truth for a live account, exactly as our rows are for paper.

The rule that keeps it honest: **a position list we cannot confirm is reported as
nothing, never as stale truth.** Past `LIVE_POSITION_CACHE_TTL_S` (120s default)
`get_positions()` returns `[]` and says so loudly, because managing a phantom already
closed at the venue is worse than admitting we don't know — and `/api/monitors`
already renders that as `monitored: false`. A transient venue error does NOT clear the
cache (that would recreate the very silence this closes); it ages out instead.
`tests/test_live_position_visibility.py`

**~~P0 — the money path is the least-tested code.~~ CLOSED 2026-08-25.**
Quarantining whole FILES was hiding **45 of 58 already-passing tests** on the money
path. Un-quarantined `test_deterministic_risk_calculator` (36 pass),
`test_exchange_client` (14) and `test_emergency_exit` (2) — 52 tests now guard the
sizing gate, order parsing, and panic exit. Reading the failures found **three real
bugs**, exactly as this repo's `test_order_manager` lesson predicts:
- Two safety warnings could never fire at their own threshold, because thresholds
  computed as products land a hair high (`0.20 * 0.75 == 0.15000000000000002`, so an
  exactly-15% drawdown compared false). Fixed via `at_or_above()`; rejections keep
  strict comparisons on purpose.
- A venue returning `STOP_MARKET` was silently parsed as `OrderType.MARKET`, so a
  **live stop-loss fill was recorded as an ordinary market order** and its exit
  attribution read "manual close" instead of "stopped out" — the live half of the
  fabricated-exit_reason bug fixed on the paper side the same day. Fixed with
  `_ORDER_TYPE_ALIASES` + a loud fallback.
- The consecutive-loss circuit breaker had been tightened 3 → 2 and its guard
  quarantined rather than updated; the test now pins the tighter contract.

`test_execution_agent` stays quarantined **deliberately** (not as a TODO): it tests
`ExecutionAgent`, which only `src/main.py` constructs — dead on the shipped path.

**P0 (NEW) — two risk caps were widened and their guards quarantined instead.**
Needs a founder decision; nothing was silently changed. See
`tests/conftest.py::QUARANTINED_NODEIDS`:
- `min_risk_reward_ratio`: code **1.0** ("for more trade opportunities") vs test 2.0
  vs plan doc 1.5. At 1.0 RR a strategy needs >55% wins to break even before fees,
  and `backtest-lab/FINDINGS.md` shows fee drag is what killed every S1 arm.
- `max_position_size_usd`: code **$100,000** ("increased for 10x leverage") vs test
  $5,000 — a 20x widening. On a $10k desk a $100k cap is barely a backstop.

**P1 — the docs claimed two execution gates; there is one.**
`ENABLE_EXECUTION` is dead code on both live entrypoints and unset in production. Only
`LIVE_TRADING_CONFIRMED` + the testnet-only key gate hold. Corrected in `CLAUDE.md`.

**~~P1 — the order-book poller has no venue fallback.~~ CLOSED 2026-08-26.**
Observed in production: klines bootstrapped from Bybit while the book poller took a
Binance 418 and paused 3600s, so `/api/pulse` reported `available: true` with
`symbols_vetoed: 3, tradability_max: 0` — the plane looked healthy and no session
could produce a setup. The book now comes from the SAME venue bootstrap chose
(`book_url_batch` / `book_url_single` + `parse_book` in `venue.rs`): Binance answers
every symbol in one round trip, Bybit is per-symbol, and an unparseable body is a
failed fetch rather than a zero spread — a fake zero would drive the very veto this
feeds. **Funding/OI remain Binance-only**; they inform the `positioning` factor, not
the veto, so a ban degrades that factor instead of zeroing everything.

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
