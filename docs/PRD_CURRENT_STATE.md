# CryptAI — Current-State PRD

> **What this is:** the audited ground truth of what is built, deployed, and running as of
> 2026-08-02. Basis: a 9-agent subsystem audit of the `feat/m0-foundation` working tree
> (539 tool calls, every claim file:line-verified), live probes of the production host, and
> a green run of `.claude/verify.sh` (frontend typecheck + 52 unit tests, backend import
> smoke + 309 tests).
>
> **Companion doc:** `docs/HLD.md` — the target design and functional requirements.
> **Supersedes** the entire Jan-2026 doc generation: `docs/prd.md`,
> `docs/COMPLETE_SPECIFICATION_SUMMARY.md`, `docs/CURRENT_PROJECT_SETUP.md`,
> `docs/frontend_design_spec.md`, `docs/TYPICAL_24HR_WORKFLOW.md`, `docs/taskmanager/*`,
> `SETUP.md`, `TRADE_STORAGE_AND_UPDATES_GUIDE.md` — those describe a Nov-2025
> single-user hobby bot that no longer exists. Trust only: this doc, `docs/HLD.md`,
> `docs/MULTI_TENANCY.md` (design contract), root `CLAUDE.md`, `AGENTS.md` (mostly).

---

## 1. Executive verdict

CryptAI today is **three good products that have never met**:

1. **Production** (`cryptai-backend.onrender.com`) runs **v2-generation code**: the old
   one-global-analysis-broadcast-to-every-user daemon model, a healthy API, and none of
   the last 21 commits. The m0 endpoints (`/api/session`, `/api/preferences`) 404 on the
   live host.
2. **`feat/m0-foundation`** (the active branch) carries a well-tested per-user control
   plane — session state machine, preferences, proposals, spend metering, pulse client —
   that is **wired into nothing**. A session started via the API meters the user's quota
   while running zero analysis.
3. **The Rust signal engine** is the most finished subsystem in the repo (125 tests,
   live Binance ingest, empirically validated tradability score) and **runs nowhere but a
   laptop**. It has no Dockerfile, no Render service, no CI job, and zero production
   consumers. It does not exist on `v2` at all.

The frontend is real and wired to the backend (auth → onboarding → dashboard → terminal →
paper execution), but has **no deployment evidence** and no UI for any of the new session/
proposal/preferences surface.

**Nothing here needs a rewrite.** The parts are individually sound; the product gap is
almost entirely *wiring* + *deployment* + *a handful of confirmed bugs*, catalogued below.

---

## 2. What is deployed and running right now

| Plane | Status | Evidence |
|---|---|---|
| Backend API (Render, `cryptai-backend.onrender.com`) | **LIVE**, healthy, no cold start | `/health` 200, `/health/ready` 200 `{redis:true, database:true}` — probed 2026-08-02 |
| …but which code? | **v2-generation**, not this branch | `/api/session` and `/api/preferences` 404 on live host; `main` lacks `render.yaml` entirely, so Render must track `v2` |
| Connected database | **Production Supabase Postgres** | `/health/ready` reports `database:true` — any branch repoint runs new code against real data |
| Trading daemon (`cryptai-daemon`) | **Unknowable from the repo** | `keepalive.yml` says free tier + `RUN_DAEMON_IN_API=true`; `render.yaml` says starter plan + separate worker and never sets that var. Live `/api/setups` returns `{"setups":[]}` |
| Keepalive cron | **WORKS** | GitHub Actions on `main`, pings `/health/live` every 10 min, ~80 ms responses |
| Frontend | **NOT deployed** | No `vercel.json`, no `.vercel/`, no URL anywhere in the repo; `DEPLOY.md` §A2 is a plan, not evidence |
| Rust signal engine | **NOT deployed** | No deployment artifact of any kind; `market:pulse:*` keys are never populated in production; directory absent from `origin/v2` |
| Alembic migrations | **Never run in deploy or CI** | Production schema is created ad hoc by store constructors (`checkfirst=True`); `proposals` + `pulse_snapshots` have no production creator |
| CI | Gates `v2`/PR branches only | `main` has no `ci.yml`; frontend tests never run in CI; a stale TA-Lib C build burns minutes for a lib nothing imports (`ci.yml:74-87`) |

**Branch facts:** `main` = stale 8-commit snapshot and still the GitHub default. `v2` =
111 commits, what production runs. `feat/m0-foundation` = `v2` + 21 commits, where all
current work lives.

---

## 3. What a user can actually do today (on the live v2 deployment)

Works end-to-end:
- Sign up / log in (Supabase email + Google OAuth), server-side route gating.
- Onboard: pick trading mode, connect BingX or Delta India keys (Fernet-encrypted vault,
  verify-before-store, testnet-only enforced at the API — `server.py:973-1031`).
- Dashboard with real backend data over authenticated REST + WS: portfolio, positions,
  markets, agent activity feed.
- Trading terminal: klinecharts v10 chart with drawings/indicators, live order book,
  bracket trade ticket → `POST /api/execute-setup` (paper), per-position close,
  open-orders cancel. All user-scoped, Supabase JWT throughout.
- Get a seeded $10k paper desk with real fill simulation (slippage, taker fees, margin
  checks, self-managing SL/TP brackets via the daemon tick loop).

Does not exist for users, anywhere:
- Starting a **trading session** (no UI; endpoints only on the undeployed branch).
- Seeing the **signal engine's** regime/tradability (the "regime" chip in the UI comes
  from LLM setup payloads, not the Rust engine).
- **Approving/rejecting a proposal** (no UI; backend endpoints can only 409 anyway — see §5).
- **AI assistant/chat** — nothing conversational exists in any layer.
- **Paying for anything** — no Stripe/Razorpay/checkout; the landing page advertises
  $19/$79 plans nobody can buy; tiers resolve from env vars (`plans.py:84-105`).
- Password reset (`/auth/forgot-password` link 404s).

---

## 4. Subsystem inventory

### 4.1 Backend API (`src/api/server.py`, 1861 lines) — solid surface, hollow middle
**Works:** Supabase JWT verification at the edge (JWKS, ES256/RS256, aud/issuer checked);
`require_user` on every tenant endpoint; IDOR-safe session endpoints (never accept a
session_id from the client); server-authoritative session clock + boot-time tick loop;
per-tenant WS fan-out with handshake auth; rate limiting; vault endpoints; honest
`/health` (pings Redis) / `/health/ready` / `/health/live`. 146 API tests pass.
**Hollow:** `SessionManager.propose()` has no production caller, so `SETUP_PROPOSED`
(the clock-pause state) is unreachable and `/api/session/approve|reject` can only return
409. LLM cost-cap enforcement checks a number nothing feeds.

### 4.2 Multi-agent core — deployed reality is the superseded model
The deployed daemon (`src/multi_user_daemon.py`) computes shared analysis once per symbol
and **books the identical setup into every tenant** (`multi_user.py:246-300`) — exactly
the model `docs/MULTI_TENANCY.md` supersedes. The new control plane (SessionManager,
PreferencesStore, SessionBudget, SessionWorker/Pool, ProposalService, PulseClient — 111
tests) is **a layer of plumbing with no engine**: `SessionWorkerPool` is constructed
nowhere, its `analyze_fn` is explicitly deferred ("M3's job", `session_worker.py:18-23`),
`ProposalService` and `PulseClient` have zero importers in `src/`.
**No per-position monitor exists** that re-evaluates open positions against changed market
conditions — exits are static SL/TP price crossings only. The memory agent's learning loop
is severed on the deployed path (daemon-booked trades never write entry rows, so exit
updates hit "Trade not found" and the vector store accumulates nothing). Dead code:
`AgentHealthMonitor` (unwired), `EventCoordinator`/`CycleState` (zero importers), a
guaranteed 5s stall at the top of every full-graph cycle (`orchestrator.py:841` awaits a
correlation-id that was never sent).

### 4.3 Execution + risk — paper is real, risk limits are decorative
**Works:** paper engine (real fills/slippage/fees/margin, plan-seeded desks, honest
rejections); BingX adapter genuinely rebuilt — the three REBUILD_PLAN bugs (signing,
envelope, field names) demonstrably fixed with passing contract tests; OrderManager
rollback closes filled entries reduce-only; OCO works for paper + single-bot live; the two
money gates fail closed.
**Broken:**
- `DeltaExchangeClient._to_order` **crashes on any non-filled order** —
  `OrderStatus.PENDING` doesn't exist in the enum (`exchange_client.py:855` vs `:42-49`).
  Delta is the designated reference live adapter and its bracket path cannot work. Zero
  tests target it.
- **CoinDCX is a pure `NotImplementedError` stub** (`exchange_client.py:700-749`) yet
  selectable via the factory. CoinDCX has **no testnet** (M0 finding) — its write path
  can't be validated without real money.
- **Every portfolio-level risk limit is non-binding**: `PortfolioStateTracker.add_position`
  is never called from any production path, so portfolio heat, max-concurrent-positions,
  daily-loss, drawdown, and circuit-breaker triggers all evaluate an **empty portfolio**.
  The daily-trade cap reads a nonexistent attribute → always passes.
- No leverage cap in the active risk path (`RiskParameters` has no `max_leverage`; the only
  cap lives in unwired `proposals.py:139-143`; paper engine hardcodes 10×).
- `ENABLE_EXECUTION` — documented as *the* paper/live switch — **is dead on the deployed
  daemon path** (only `src/main.py` reads it). Effective gates there: vault keys + per-user
  trading mode + `LIVE_TRADING_CONFIRMED` (mainnet).
- Per-user paper desks **evaporate on every daemon restart** (hydration gap,
  self-acknowledged at `multi_user_daemon.py:449`); margin-rejected paper entries are
  reported as approved/active.
- No live adapter has ever run against a real testnet — all live claims rest on mocked
  contract tests.

### 4.4 Data / tenancy / billing — best-tested layer, two structural debts
**Works:** 13 tables, one metadata, linear 3-revision Alembic chain with a
schema↔migration parity test; every per-user table has an indexed `user_id`;
`pulse_snapshots` is tested to never gain one; Fernet vault wired to API + daemon; RLS
defense-in-depth for `trades` + `exchange_credentials`; per-user Redis namespacing.
**Debts:** (1) **Float money columns everywhere** (trades, trade_executions, proposals,
user_preferences, performance_metrics, market_data, pulse_snapshots) — only
`sessions.llm_cost_micros` follows the integer-minor-units rule; needs one wholesale
migration. (2) `alembic upgrade` **will collide** with `checkfirst=True`-created tables on
the production DB — no stamping strategy exists. Also: no RLS on the five new per-user
tables; vault has zero dedicated tests; no key-rotation path (`VAULT_ENC_KEY` loss bricks
every tenant's exchange connection). Billing is quota logic only — tier resolution via env
vars means whoever controls the environment grants paid plans, no audit trail.

### 4.5 Rust signal engine (`signal-engine/`) — finished, validated, homeless
**Works:** live Binance SPOT WS ingest (klines 5m/15m/1h/4h + bookTicker) + REST bootstrap
+ 60s futures funding/OI poller; real structure detection (fractal swings, BOS/CHoCH,
unfilled FVGs, ATR-scaled order blocks, clustered liquidity pools — 22 tests, no
repainting); 5 veto gates → 6 weighted factors → regime + tradability 0-100; Lo-MacKinlay
variance ratio wired into regime classification; pulse v1 published to
`market:pulse:{SYMBOL}` with 120s TTL; 125 unit tests + 8 Python differential tests
against a numpy oracle; graceful SIGTERM.
**The eval harness is unusually honest and its findings are product-relevant:**
- Tradability **is** empirically validated as a short-horizon filter (IC +0.083/+0.096 at
  4 bars, survives volatility normalization). "Is NOW a good time to trade" has a real,
  falsifiable backing signal.
- The **regime-as-direction claim was killed out of sample** (walk-forward, mean IC delta
  −0.008). The engine deliberately refuses to emit direction. **No consumer may ever map
  regime → trade side.**
- Weights re-derived on BTC/ETH/SOL, validated on six held-out symbols (IC +0.0901→+0.1052,
  5/6 improved). Caveat: cross-sectional only; re-validation on later data is blocked on
  the unwritten `pulse_snapshots` calibration log.
**Gaps:** zero deployment surface; zero production consumers; `market:pulse:global` is
documented + declared in `pulse_client.py:33` but never published; `pulse_snapshots` has
no writer on either side; `btc_correlation_30d` mixes timeframes (4h vs 1h returns) in
live wiring; `cargo clippy -D warnings` fails on the pinned 1.97.1 toolchain despite the
README claiming it as a gate; no CI touches the crate.

### 4.6 Frontend — real, wired, undeployed, blind to the new backend
**Works (verified: `tsc` clean, 52/52 vitest):** SSR auth middleware; login/signup/OAuth;
2-step onboarding persisting to settings + vault; dashboard fully on real data; deep
terminal (klinecharts v10, drawings, order book, mode-aware bracket ticket, shortcuts,
mobile); WS auth + client-driven subscriptions; close-all routed through a server-only
admin token (`app/api/close-positions/route.ts`, fails closed); error/empty/loading states
in 15+ components.
**Absent:** any session UI (`rg 'api/session'` in `frontend/src` → zero hits), proposal
approve/reject UI, preferences UI (only the older settings), AI chat, TradingView widget
(charting is klinecharts + lightweight-charts; "TradingView" appears only in styling
comments), password reset, billing UI, `GET /api/positions` consumer (positions seeded
from `/api/trades` instead).
**Broken:** forgot-password 404; post-login `?redirect=` ignored; stale tenancy TODO in
`ActiveTrades.tsx` contradicting the (correct) code.

---

## 5. Confirmed bugs and security findings (ranked)

1. **Session quota bypass — CONFIRMED by execution.** `POST /api/session/start` with
   `quota_seconds=86400` grants 24h against a 30-min daily quota; the explicit value is
   used unclamped (`session_manager.py:204`) and nothing re-checks `remaining_today`
   mid-session. This defeats the monetization mechanic outright.
2. **`require_admin` fails open.** With `ADMIN_USER_IDS` unset (it is not in
   `render.yaml`), **any logged-in user is an engine admin** for `POST /api/engine`
   (`server.py:955-957`).
3. **Risk limits evaluate an empty portfolio** (§4.3) — free-tier caps (1 position,
   3 trades/day, 5% daily loss) enforce nothing.
4. **Delta adapter deterministically crashes** on any non-filled order (§4.3) — the
   reference live adapter cannot place brackets.
5. **LLM spend is uncapped in practice.** Per-session cap guards a number that never
   moves; real agent calls meter floats into global Redis keys, per-deployment not
   per-user. Only real protection: the manual owner EngineSwitch.
6. **`NEXT_PUBLIC_API_TOKEN` is a loaded gun.** The backend has exactly one static token
   tier and it is admin-capable; `api.ts:9` mislabels it "read-only";
   `docker-compose.yml:149` passes it as a build arg. One operator mistake ships an admin
   token in the public bundle.
7. **Fail-open anonymous mode.** If `SUPABASE_URL` and `API_AUTH_TOKEN` are both absent,
   `/api/trades` returns ALL tenants' trades unscoped (`server.py:182-183`, `800-804`).
   Safety rests entirely on Render env vars.
8. **34 destructive scripts ship in the production image** (`nuclear_clear_positions.py`,
   `delete_all_trades.py`, …) with no confirmation gates.
9. Supabase JWT travels as `?token=` in the WS URL (lands in proxy access logs);
   `/metrics` is publicly reachable; session tick loop only enforces meters for
   WS-connected users; in-process rate limits multiply under horizontal scaling.
10. **189 backend tests remain quarantined** — precedent (`test_order_manager`) shows some
    encode real regressions, not staleness.

---

## 6. Product decisions already made (live in code, no doc until now)

| Decision | Where it lives |
|---|---|
| Tiers: Free $0 / Starter $19 / Pro $79 with concrete risk ceilings (paper capital, risk/trade, positions, trades/day, live access) | `src/billing/plans.py:57-79`, mirrored on the landing page |
| Metered analysis sessions; free = **30 min/day** (vision says 1 hr — undecided conflict); clock pauses while a proposal awaits the user; monitoring never metered | `src/core/session_manager.py` |
| Per-session LLM token budget as safety net ($0.50 default) | `src/core/session_budget.py` |
| Exchange lineup: BingX + Delta India + CoinDCX execution; Binance data-only | `src/execution/exchange_client.py` |
| Delta India = reference live adapter (only venue with a testnet); CoinDCX unvalidatable without real money | root `CLAUDE.md` M0 findings |
| Frontend design: "trading terminal" — near-black, emerald accent, red = loss only, Geist Mono numerals, dark-only | `REBUILD_PLAN.md:36-46`, shipped |
| Pulse contract v1 (shared plane ↔ per-user plane interface) | `docs/MULTI_TENANCY.md` + `signal-engine/src/pulse.rs` |
| Regime must never be mapped to trade direction (empirically refuted) | `signal-engine/FINDINGS.md` §2, `pulse.rs:23-34` |
| Starter/Pro session quotas | **NOWHERE — undefined in code and docs; must be decided in the PRD/HLD** |

---

## 7. Launch blockers (paper-trading public beta)

Ordered by "cannot ship a paying product without":

1. Deploy truth: make one branch canonical, repoint Render, deploy the signal engine and
   the frontend. The three planes have never run in the same environment.
2. Wire the session pipeline: `SessionWorkerPool` + `analyze_fn` + `PulseClient` +
   `ProposalService` into the entrypoints — sessions must do work when they meter time.
3. Fix §5.1–§5.4 (quota bypass, admin fail-open, unfed risk tracker, Delta crash).
4. Session/proposal/preferences UI in the frontend.
5. Migration strategy for the production DB (alembic stamp vs checkfirst collision).
6. Payments or an honest "free beta" posture (remove purchasable-looking pricing).
7. Compliance floor for India: risk disclosure + ToS + consent for automated execution;
   FIU-IND / VDA-tax / DPDP assessment (see HLD §10).
