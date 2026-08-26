# CryptAI — High-Level Design & Functional Requirements

> **What this is:** the from-scratch target design for CryptAI as a multi-tenant SaaS,
> written against the founder's product vision and reconciled with what already exists.
> Companion to `docs/PRD_CURRENT_STATE.md` (audited ground truth) and
> `docs/MULTI_TENANCY.md` (the tenancy design contract this builds on).
>
> **Design stance:** the vision and the existing `MULTI_TENANCY.md` contract agree far
> more than they conflict. Where the code already went *further* than the vision (per-user
> setup synthesis instead of one-shared-setup; continuous in-session analysis instead of a
> single snapshot; unmetered monitors that survive restarts), this HLD adopts the stronger
> version and flags it. Where the vision has a mechanic the code lacks (per-session channel
> pick, per-crypto-per-channel trade caps), this HLD specifies how to add it.

---

## 0. Reading guide

- **§1 Product concept** — one screen of what CryptAI is.
- **§2 Personas & the day-in-the-life** — your flow, made concrete.
- **§3 System architecture** — the three planes, with a diagram.
- **§4 The session lifecycle** — the core state machine, end to end.
- **§5 Functional requirements** — FR-1…FR-N, testable, grouped by capability.
- **§6 The agent swarm** — roster, shared vs per-user, message contracts.
- **§7 Data model & money** — tables, tenancy, integer-minor-units.
- **§8 Non-functional requirements** — safety, cost, latency, availability.
- **§9 The channels model** — resolving the vision's biggest gap vs the code.
- **§10 Compliance & the India problem** — the blockers the vision doesn't mention.
- **§11 Delivery roadmap** — M1…M6, each shippable and verifiable.

---

## 1. Product concept

CryptAI is an **AI trading co-pilot for crypto perpetual futures**. A user brings their own
exchange account (Delta Exchange India, later CoinDCX/BingX); CryptAI brings a professional
trading terminal, an always-on market-condition engine, and a swarm of AI agents that
propose, size, execute, and actively manage trades on the user's behalf — inside a metered,
consent-gated **trading session**.

The product's three honest promises:
1. **"Is now a good time to trade, and how?"** — answered by a validated, always-on signal
   engine, not vibes.
2. **"A trade team that works your book, not a generic tip."** — per-user synthesis, sizing,
   and risk gating against *your* capital, positions, and goals.
3. **"It doesn't fall asleep after entering."** — a per-position monitor re-evaluates open
   trades against changing conditions and decides stay-in vs take-profit-and-exit.

The moat is the combination: a shared, cheap, validated market-fact layer + per-user
judgment + active management, all inside a cost-bounded session.

---

## 2. Personas & the day-in-the-life

**Personas.** Beginner (paper-only, learning, wants explanations), Intermediate (small
real capital on testnet→mainnet, wants the co-pilot to size and manage), Advanced (uses the
terminal directly, wants the agents as a second opinion and an execution assistant).

**The day (target flow — this is what we are building toward):**

1. **Ambient signal.** The Rust engine has been running all along. The user opens the app
   and the dashboard shows a **market pulse**: per-symbol regime + a 0-100 tradability
   score + a cross-market "market is hot / quiet" banner. No session needed, no cost — these
   are shared facts. This is the honest version of "should I even trade right now."
2. **Pick a channel & start a session.** The user selects one of three **channels** —
   *Scalp*, *Intraday/Swing*, *Position* — and hits **Start Session**. The server clock
   starts; free tier gets a daily quota (see §5 FR-SESSION). A **SessionWorker** spawns for
   this user.
3. **Synthesis.** The worker reads the shared pulse (fail-closed on staleness), pulls the
   user's preferences (capital, risk appetite, chosen symbols, 30-day PnL goal, month-to-
   date actual) and their open book, and synthesizes **per-user setups** for the chosen
   channel — genuinely different from another user's on the same chart.
4. **Gate & propose.** Per-user gating agents decide *whether* to trade (portfolio heat,
   correlation, goal state, memory of past outcomes on this pattern/regime), then *how much*
   and *what leverage* (deterministic sizing). A **Proposal** is created with entry/stop/
   targets, size, leverage, R:R, a shelf life, and a plain-language rationale. **The session
   clock pauses** while the user considers it.
5. **Consent & execute.** The user approves (or the session is in auto mode within their
   consent settings). At approval time the proposal is **re-validated** against the current
   price and its shelf life; if still valid it routes to the user's exchange (paper by
   default). Free tier: at most **one open trade per crypto per channel**.
6. **Active management.** On fill, a **MonitorWorker** is spawned for that position. It is
   **unmetered and unconditional** — it outlives the session, a process restart, and a
   deploy. It watches the position against live price *and* re-polls the analysis when the
   pulse/regime/structure drifts from the thesis, and decides stay-in, tighten-stop, take-
   partial, or exit.
7. **Session ends, monitors continue.** When the quota is spent (or the user ends it), the
   SessionWorker is torn down. Any open position's MonitorWorker keeps running. The user can
   start a new session tomorrow; the monitors never stopped.

---

## 3. System architecture

Three planes, separated by the tenancy boundary: **shared facts** vs **per-user judgment**.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ PLANE 1 — SHARED SIGNAL PLANE          Rust · 1 process · always-on         │
│ Binance ingest → indicators → structure (OB/FVG/liquidity/BOS-CHoCH)        │
│ → regime + tradability (validated) → market:pulse:{symbol} + :global        │
│ NO user_id anywhere. Publishes to Redis. Also appends to pulse_snapshots    │
│ calibration log.                                                            │
└──────────────────────────────┬────────────────────────────────────────────┘
                               │  read-only · versioned · staleness-checked
        ┌──────────────────────┼──────────────────────────────┐
        ▼                      ▼                              ▼
┌────────────────┐   ┌──────────────────────┐   ┌──────────────────────────┐
│ PLANE 2 —      │   │ SESSION WORKERS       │   │ MONITOR WORKERS          │
│ CONTROL/API    │   │ 1 per ACTIVE session  │   │ 1 per OPEN position      │
│ FastAPI +      │   │ METERED · dies at     │   │ UNMETERED · outlives     │
│ Supabase JWT   │   │ quota. Runs the       │   │ session/restart/deploy.  │
│ Session state  │   │ per-user agent        │   │ Re-evaluates vs drift.   │
│ machine, prefs,│   │ pipeline → Proposals  │   │                          │
│ proposals API, │   └──────────────────────┘   └──────────────────────────┘
│ WS fan-out     │              │                            │
└────────────────┘              └───────────┬────────────────┘
        ▲                                   ▼
        │                   ┌───────────────────────────────────┐
        │                   │ PLANE 3 — SINGLETONS (sweep tenants)│
   ┌────┴─────┐             │ paper tick · exchange reconciler ·  │
   │ FRONTEND │             │ monitor supervisor · session-expiry │
   │ Next.js  │             │ sweeper · daily-quota reset         │
   │ terminal │             └───────────────────────────────────┘
   └──────────┘                          │
        │                                ▼
        │                   ┌───────────────────────────────────┐
        └──── REST + WS ────│ Postgres (Supabase) · Redis · Vault │
                            └───────────────────────────────────┘
```

**Process/scaling reality** (`MULTI_TENANCY.md` §Scaling): 1,000 registered users ≈ 30
concurrent sessions + 50 open positions ≈ **~80 asyncio tasks + 1 Rust process**, not 5,000
workers. The shared/per-user split is what buys that.

**Stack (keep — all already chosen and working):** Rust signal engine; Python 3.12
LangGraph/FastAPI backend on Render; Next.js 16 + React 19 frontend; Supabase (auth +
Postgres); Redis (message bus + pulse + per-user state); Fernet credential vault.

---

## 4. The session lifecycle (core state machine)

This already exists and is well-tested (`src/core/session_manager.py`) — the work is
**wiring it to a worker and a UI**, not building it.

```
        POST /api/session/start (channel, symbols?)
                     │
                     ▼
   ┌─────────────┐  worker synthesizes    ┌──────────────────┐
   │  SCANNING   │───────────────────────▶│  SETUP_PROPOSED   │
   │ (metered ⏱) │   proposal created      │ (clock PAUSES ⏸) │
   └─────────────┘◀───────────────────────└──────────────────┘
        │  ▲            reject / expire            │
        │  │                                       │ approve (re-validate)
        │  │ quota spent / user ends               ▼
        │  │                              ┌──────────────────┐
        │  │                              │    EXECUTING      │
        │  │                              │ order → exchange  │
        │  │                              └──────────────────┘
        ▼  │                                       │ fill
   ┌─────────────┐                                 ▼
   │    ENDED     │                    spawn MonitorWorker (unmetered,
   │ worker torn  │                    survives ENDED — see §6.3)
   │ down         │
   └─────────────┘
```

**Invariants (from `MULTI_TENANCY.md`, each must have a test):** shared plane is read-only
from per-user plane; staleness is fail-closed; no shared mutable state between sessions;
per-session token budget fail-closed; every DB query filters `user_id` in app code;
credentials never leave the vault→client path; per-user Redis keys namespaced; **monitoring
is unmetered and unconditional**; amounts are integer minor units + currency-tagged.

---

## 5. Functional requirements

Each FR is testable. **[EXISTS]** = built and wired; **[PARTIAL]** = built, not wired;
**[NEW]** = to build. IDs are stable references for the roadmap.

### FR-SIGNAL — Shared signal plane
- **FR-SIGNAL-1 [PARTIAL]** The engine SHALL publish `market:pulse:{symbol}` v1 for the
  supported universe (~20 liquid perps), refreshed ≤5s, TTL 120s. *(Built; not deployed.)*
- **FR-SIGNAL-2 [NEW]** The engine SHALL publish `market:pulse:global` (cross-market
  "hot/quiet" signal). *(Declared in `pulse_client.py:33`, never published.)*
- **FR-SIGNAL-3 [NEW]** Every published pulse SHALL be appended to the `pulse_snapshots`
  calibration log for forward-return scoring. *(Table exists; no writer.)*
- **FR-SIGNAL-4 [EXISTS]** The pulse SHALL carry facts and scores only — **never** an
  entry/stop/target or a trade direction. Enforced by a consumer-side contract test.
- **FR-SIGNAL-5 [EXISTS]** Consumers SHALL reject pulses older than the staleness budget
  (fail-closed) and reject unknown schema majors.
- **FR-SIGNAL-6 [NEW]** The engine SHALL run as a deployed, monitored, auto-restarting
  service; its uptime is the product's uptime. *(No deployment artifact today.)*

### FR-SESSION — Metered sessions
- **FR-SESSION-1 [EXISTS]** A user SHALL start at most one active session at a time; the
  server clock is authoritative; time accrues only in metered states (SCANNING).
- **FR-SESSION-2 [EXISTS]** Free tier SHALL enforce a daily quota. **Decision needed:**
  code says 30 min/day, vision says 1 hr/day (see §11 open decisions). Starter/Pro session
  quotas are **undefined and MUST be set**.
- **FR-SESSION-3 [BUG→FIX]** `quota_seconds` from the client MUST be clamped to the
  remaining daily allowance, and the quota MUST be re-checked mid-session each tick.
  *(Currently bypassable — PRD §5.1.)*
- **FR-SESSION-4 [PARTIAL]** Starting a session SHALL spawn a SessionWorker that runs the
  per-user pipeline; a session that meters time MUST do work. *(Worker exists, unwired —
  the single most important gap.)*
- **FR-SESSION-5 [EXISTS]** The clock SHALL pause in SETUP_PROPOSED and resume on
  reject/expire.
- **FR-SESSION-6 [NEW]** A session-expiry sweeper singleton SHALL end sessions of
  disconnected users (today only WS-connected users are ticked).
- **FR-SESSION-7 [EXISTS]** Per-session LLM token budget SHALL be enforced fail-closed —
  **once accounting is fed** (FR-AGENT-7).

### FR-CHANNEL — Channel selection (the vision's mechanic; see §9)
- **FR-CHANNEL-1 [NEW]** `POST /api/session/start` SHALL accept a `channel` ∈
  {scalp, intraday, position}. Maps onto the existing `goal_horizon` enum
  (scalp/intraday/swing/position).
- **FR-CHANNEL-2 [NEW]** The SessionWorker SHALL parameterize synthesis by channel
  (timeframes, strategy set, min R:R, hold horizon).
- **FR-CHANNEL-3 [NEW]** Free tier SHALL enforce **≤1 open trade per (symbol, channel)**.
  *(Today only a global max-concurrent cap exists, and it's non-binding — FR-RISK-1.)*

### FR-PREF — Preferences & goals
- **FR-PREF-1 [EXISTS]** Users SHALL set capital, risk appetite, symbol universe, per-trade
  risk %, max positions, max leverage, min R:R, min confidence — all clamped to
  min(hard cap, plan cap), tighten-only. *(`preferences.py`.)*
- **FR-PREF-2 [EXISTS]** Users SHALL set a `monthly_pnl_target_pct` (the 30-day PnL goal)
  and `goal_horizon`. *(Fields exist…)*
- **FR-PREF-3 [NEW]** …but synthesis/sizing/ranking MUST actually **consume** them. Today
  `monthly_pnl_target_pct` and `goal_horizon` are write-only. Goal-aware ranking
  ("at 85% of target, 3 days left → cut risk") is a headline feature that reads these.
- **FR-PREF-4 [NEW]** A preferences UI SHALL exist. *(Backend endpoints have zero frontend
  callers.)*

### FR-SYNTH — Per-user setup synthesis
- **FR-SYNTH-1 [NEW]** Synthesis SHALL be per-user, per-session, per-channel — producing
  genuinely different trades for different users on the same chart (portfolio-, goal-, and
  memory-aware). *(This is the core departure from the deployed one-shared-setup model.)*
- **FR-SYNTH-2 [NEW]** Synthesis SHALL be pulse-gated: no metered LLM cycle when tradability
  is vetoed. *(`detect_regime` node removed from per-user graph; regime arrives from pulse.)*
- **FR-SYNTH-3 [EXISTS]** The strategy stack (setup builder, R:R, position sizer, confluence
  scorer, LLM prompter) SHALL back synthesis. *(Wired in `strategy_agent.py`.)*

### FR-PROPOSAL — Proposals & consent
- **FR-PROPOSAL-1 [PARTIAL]** A proposal SHALL carry deterministic size + leverage, a shelf
  life, entry/stop/targets, R:R, and a rationale. *(`ProposalService` built, unwired.)*
- **FR-PROPOSAL-2 [PARTIAL]** Approval SHALL re-validate price + shelf life before execution;
  a stale/drifted proposal is rejected, not filled. *(Built in `proposals.py`, not on the
  execution path.)*
- **FR-PROPOSAL-3 [NEW]** Proposal HTTP endpoints (create/list/pending/approve-by-id) and a
  frontend approve/reject UI SHALL exist. *(Today `/api/session/approve` flips session state
  with no proposal row.)*
- **FR-PROPOSAL-4 [NEW]** Auto mode SHALL execute within explicit per-user consent settings
  (max leverage, max size, allowed channels) with a full audit trail.

### FR-EXEC — Execution
- **FR-EXEC-1 [EXISTS]** Paper is the default; every user gets a seeded paper desk with real
  fill simulation. Two money gates (`ENABLE_EXECUTION`, `LIVE_TRADING_CONFIRMED`) fail closed.
- **FR-EXEC-2 [BUG→FIX]** The Delta India adapter MUST place bracket orders without crashing
  (`OrderStatus.PENDING` bug — PRD §5.4) and MUST be validated on Delta's testnet.
- **FR-EXEC-3 [NEW]** Per-user live engines SHALL have OCO/fill-tracking (a filled SL must
  cancel resting TPs). *(Only single-bot + paper have this today.)*
- **FR-EXEC-4 [NEW]** A per-venue price sanity gate SHALL run immediately before every order
  (basis risk: pulse from Binance, fills on Delta/CoinDCX).
- **FR-EXEC-5 [NEW]** Per-user paper desks SHALL survive daemon restarts (hydration gap —
  PRD §4.3).
- **FR-EXEC-6 [DEFER]** CoinDCX execution — stubbed, no testnet; defer to post-launch and
  keep it unselectable until implemented.

### FR-MONITOR — Active position management (the vision's point 6)
- **FR-MONITOR-1 [NEW]** On fill, a MonitorWorker SHALL spawn per open position, **unmetered
  and unconditional**, surviving session end / restart / deploy. *(No such class exists.)*
- **FR-MONITOR-2 [NEW]** The monitor SHALL re-evaluate the position against changed
  conditions — regime flip, pulse veto, invalidation-level breach, structure change — not
  only static SL/TP crossings.
- **FR-MONITOR-3 [NEW]** On material drift the monitor SHALL re-poll synthesis and decide:
  hold, tighten stop, take partial, or exit. This is the "doesn't fall asleep after entry"
  promise.
- **FR-MONITOR-4 [NEW]** A monitor-supervisor singleton SHALL restart crashed monitors and
  reconcile monitors against actual open positions on boot.

### FR-RISK — Risk gating
- **FR-RISK-1 [BUG→FIX]** Portfolio-level limits (heat, max-concurrent, daily loss,
  drawdown, streaks, circuit breaker) MUST evaluate the **real** portfolio.
  `PortfolioStateTracker` MUST be fed by every execution. *(Today it's empty → all limits
  non-binding — PRD §4.3.)*
- **FR-RISK-2 [NEW]** The active risk path SHALL enforce a leverage cap. *(No `max_leverage`
  in `RiskParameters`; only the unwired proposals module caps it.)*
- **FR-RISK-3 [NEW]** Circuit breaker SHALL halt a user's session on breach of their daily
  loss / drawdown limits, with a clear user-visible state.

### FR-MEMORY — Learning loop
- **FR-MEMORY-1 [BUG→FIX]** Every booked trade MUST write an entry row so exit updates
  resolve. *(Deployed daemon path never writes entries → exits error, vector store stays
  empty — PRD §4.2.)*
- **FR-MEMORY-2 [NEW]** Synthesis SHALL retrieve similar past trades (this user, this
  pattern, this regime) and surface the outcome ("you've lost 4 of your last 5 on this
  pattern in this regime"). *(Read side has zero callers today.)*

### FR-ASSIST — AI assistant (the vision's third pillar)
- **FR-ASSIST-1 [NEW]** A conversational assistant SHALL exist: ask about the market, a
  position, a proposal's rationale, or "why did you exit?" Grounded in the user's own pulse,
  book, and session events (no fabrication). *(Nothing conversational exists in any layer.)*
- **FR-ASSIST-2 [NEW]** The assistant SHALL be read-only by default; any action it takes
  (place/close) goes through the same proposal+consent path as the agents.

### FR-BILLING — Monetization
- **FR-BILLING-1 [NEW]** A real payment integration (Razorpay for India / Stripe) SHALL back
  tier resolution via a `subscriptions` table — not env vars. *(No checkout exists; tiers are
  env-granted — PRD §4.4.)*
- **FR-BILLING-2 [NEW]** Until FR-BILLING-1 ships, the product SHALL present as a **free
  beta** — remove purchasable-looking $19/$79 pricing or mark it "coming soon."

### FR-AUTH — Identity & account
- **FR-AUTH-1 [EXISTS]** Supabase JWT verified at the edge; every tenant endpoint scoped.
- **FR-AUTH-2 [BUG→FIX]** `require_admin` MUST fail closed (`ADMIN_USER_IDS` unset ⇒ nobody
  is admin — PRD §5.2); anonymous-open mode MUST be impossible in production.
- **FR-AUTH-3 [NEW]** Password reset, account deletion, and data export SHALL exist (DPDP
  Act — §10).

### FR-UI — Frontend surface (new screens)
- **FR-UI-1 [NEW]** Market-pulse widget (regime + tradability + global hot/quiet banner).
- **FR-UI-2 [NEW]** Session control: channel picker, start/stop, live timer, quota display.
- **FR-UI-3 [NEW]** Proposal cards with approve/reject + rationale + shelf-life countdown.
- **FR-UI-4 [NEW]** Preferences screen (capital, risk, goals, symbols, channels, consent).
- **FR-UI-5 [NEW]** Assistant chat panel.
- **FR-UI-6 [BUG→FIX]** Fix forgot-password 404 and post-login redirect.

---

## 6. The agent swarm

### 6.1 Roster & tenancy
| Agent | Plane | Tenancy | Status |
|---|---|---|---|
| Signal engine (ingest, indicators, structure, scoring) | 1 · Rust | user-blind | built, undeployed |
| Data collection agent | 1 · shared | user-blind | exists (LangGraph) |
| Market analysis agent | split | shared facts, per-user synthesis | exists as shared; synthesis is per-user [NEW] |
| Strategy generation agent | 3 · per-user | per-user | wired |
| Risk gating agent | 3 · per-user | per-user | exists, but tracker unfed [FIX] |
| Execution agent | 3 · per-user | per-user | single-bot only; per-user OCO [NEW] |
| Monitor agent (per position) | 3 · per-position | per-user | **absent [NEW]** |
| Memory agent | 3 · per-user | per-user | write-side severed [FIX], read-side unused [NEW] |
| Assistant agent | 3 · per-user | per-user | **absent [NEW]** |

### 6.2 Shared vs per-user (the boundary that keeps cost O(1) in users)
- **Shared, computed once:** OHLCV, funding, OI, orderbook, indicators, market structure,
  regime label, tradability score, key levels, invalidation zones.
- **Per-user, computed per session cycle:** symbol universe, setup synthesis, tradability-
  *for-this-user*, sizing, portfolio-aware filtering, goal-aware ranking, memory retrieval,
  narrative, execution venue + credentials.

### 6.3 Why the monitor is a separate instance, not a session phase
A monitor **outliving its session is the normal case**. Sessions are metered and die at
quota; positions are money at risk and must be watched regardless of billing. Making the
monitor a category-3 per-position instance (not a phase of the session worker) is what makes
"monitoring is unmetered and unconditional" structurally true rather than a promise.

### 6.4 Message contracts
- Shared → per-user: the **pulse** (Redis `market:pulse:*`), read-only, versioned,
  staleness-checked. No other coupling.
- Per-user agents ↔ each other: Redis pub/sub over `{agent}_inbox` / `{agent}_response`
  (exists). Add: execution → risk tracker feed (FR-RISK-1), execution → memory entry write
  (FR-MEMORY-1), monitor → synthesis re-poll (FR-MONITOR-3).

---

## 7. Data model & money

**Tenancy:** every per-user table carries an indexed `user_id`; the backend connects as an
RLS-bypassing role, so **app-layer `WHERE user_id = …` is the only guard** — a missing filter
is a launch blocker, not a bug. Add RLS defense-in-depth to the five new tables
(`user_settings`, `user_preferences`, `sessions`, `session_events`, `proposals`).

**Money (must fix before real money):** convert **all** price/size/pnl columns from `Float`
to integer minor units + a currency tag, in one wholesale migration (trades,
trade_executions, proposals, user_preferences, performance_metrics, market_data,
pulse_snapshots). Only `sessions.llm_cost_micros` is correct today. INR settlement on Indian
venues makes a USDT assumption a correctness bug.

**Migrations:** resolve the `alembic upgrade` vs `checkfirst=True` collision — the production
DB already has some tables created ad hoc. Introduce an alembic-stamp step in deploy so
migrations run cleanly and forward-only. Never edit an applied migration.

**Pulse calibration:** write `pulse_snapshots` on every publish (FR-SIGNAL-3) so the
tradability score stays falsifiable over time.

---

## 8. Non-functional requirements

- **NFR-SAFETY-1** Paper is default; live is double-gated and fail-closed. Never widen a
  risk gate, position cap, or stop to get a test green.
- **NFR-SAFETY-2** Monitors are unmetered/unconditional; a quota expiry never stops a monitor.
- **NFR-COST-1** Per-session LLM token budget enforced fail-closed; synthesis is per session
  *cycle* (~10 LLM calls per 30-min session), not per tick. Cache what repeats; stream what's
  slow; always handle refusal/timeout/malformed output.
- **NFR-COST-2** No unbounded per-user LLM spend — the current top-3 ranked risk. The session
  token cap is the safety net; the minute quota is the product.
- **NFR-AVAIL-1** The signal engine is a single point of failure once sessions gate on it →
  it needs a host, restart policy, and monitoring. Fail-closed staleness means users see an
  honest "market data unavailable" rather than trading on stale facts.
- **NFR-LAT-1** Pulse refresh ≤5s; staleness budget ~15s; order path adds a per-venue price
  sanity gate.
- **NFR-DATA-1** No fabricated numbers in the UI — every value traces to backend API/WS or
  shows an honest empty/loading/error state.

---

## 9. The channels model — resolving vision vs code

**The gap:** the vision wants **per-session channel selection** (scalp / swing / position)
with **per-channel trade limits**. The code encodes trading style as a **persistent
persona** (`goal_horizon`) with no channel concept and no per-channel caps.

**Decision (this HLD):** adopt a hybrid.
- `goal_horizon` stays as the user's **default** channel (good onboarding default).
- `POST /api/session/start` gains a `channel` parameter that **overrides** the default for
  that session (FR-CHANNEL-1). This gives the vision's "pick a mode before you start."
- Synthesis is parameterized by channel (FR-CHANNEL-2): timeframes, strategy set, min R:R,
  hold horizon all shift with the channel.
- The trade cap becomes **per (symbol, channel)** for free tier (FR-CHANNEL-3), enforced by
  the (now-fed) portfolio tracker.

**Caution from the signal engine's own evals:** tradability weights are **horizon-specific**
and validated at a 4–12 bar half-life. A *Scalp* channel on 1–5m bars and a *Position*
channel on daily bars **cannot reuse the same tradability score** without re-validation, or
they silently void the calibration. Either (a) run per-channel scoring in the engine, or
(b) restrict channels to horizons the current score is validated for and mark others "beta."
This is a real constraint, not a nice-to-have — it's why the vision's "which style fits now"
advice needs its own validation before it can be trusted.

---

## 10. Compliance & the India problem (vision blind spots)

These are not in the vision but are **launch blockers** for a product placing leveraged
derivatives trades for Indian retail users. Get a lawyer; this is engineering's read, not
legal advice.

1. **KYC/AML.** An automated system trading users' accounts with only email signup is a
   blocker. At minimum: identity verification before any live (real-money) connection.
2. **FIU-IND registration.** A platform facilitating VDA (virtual digital asset) trades is
   likely a PMLA reporting entity. Assess before public launch.
3. **VDA tax regime.** 30% tax on VDA gains + **1% TDS** on transfers materially punishes
   the high-frequency **Scalp** channel — the product must be honest that scalping's edge is
   eaten by TDS for Indian users. This affects which channels you even offer.
4. **Investment-advice / algo-trading licensing.** AI-directed order placement for retail may
   trigger advisory/algo regulation. Unexamined.
5. **Exchange API key scoping.** The vault stores keys but never verifies **trade-only,
   no-withdrawal** scope. A stored withdrawal-capable key turns any compromise into direct
   theft. MUST enforce/verify key permissions.
6. **Consent & disclosure.** No ToS, leverage-risk disclosure, or explicit automated-
   execution consent flow exists. Required before a user's real money moves.
7. **DPDP Act.** Holding trading history + exchange credentials requires account deletion +
   data export (FR-AUTH-3).
8. **Market-data TOS.** Redistributing Binance data through the charting frontend may violate
   Binance's data terms — check before scaling.

---

## 11. Delivery roadmap

Each milestone is independently shippable and gated by `.claude/verify.sh` + a stated
manual proof. Ordered so the product becomes **coherent** (does what it says) before it
becomes **bigger**.

### M1 — Deploy truth & foundation fixes (make the three planes real)
Make one branch canonical (merge `feat/m0-foundation` → default; repoint Render). Deploy the
signal engine as a Render worker (FR-SIGNAL-6) and the frontend (Vercel). Add the alembic
stamp/upgrade deploy step (§7). Fix the confirmed bugs: quota clamp (FR-SESSION-3), admin
fail-open (FR-AUTH-2), Delta crash (FR-EXEC-2), risk-tracker feed (FR-RISK-1), memory entry
write (FR-MEMORY-1). Remove/guard the 34 destructive scripts; fix `NEXT_PUBLIC_API_TOKEN`.
**Proof:** all three planes running in one environment; `market:pulse:*` populated in prod;
migrations run clean; the confirmed exploits no longer reproduce.

### M2 — Wire the session pipeline (a session that meters does work)
Instantiate `SessionWorkerPool` + `analyze_fn` + `PulseClient` in an entrypoint
(FR-SESSION-4, FR-SYNTH-2). Feed the LLM cost accounting (FR-SESSION-7). Add the session-
expiry sweeper (FR-SESSION-6). Build the session-control UI: channel picker, timer, quota
(FR-UI-2, FR-CHANNEL-1/2). **Proof:** a real session synthesizes per-user setups, meters
real LLM spend against the cap, and ends honestly — demonstrated on the seeded paper desk.

### M3 — Proposals, consent & per-user synthesis
Wire `ProposalService` end-to-end: proposal endpoints, approval-time re-validation on the
execution path, proposal UI (FR-PROPOSAL-1..4). Make synthesis genuinely per-user and
goal-aware (FR-SYNTH-1, FR-PREF-3). Preferences UI (FR-UI-4, FR-PREF-4). Enforce per-(symbol,
channel) caps (FR-CHANNEL-3). **Proof:** two users with different preferences get different
proposals on the same chart; a stale proposal is rejected at approval, not filled.

### M4 — Active management (the "doesn't fall asleep" promise)
Build MonitorWorker + monitor supervisor (FR-MONITOR-1..4). Re-evaluation against regime
flip / pulse veto / invalidation breach; dynamic stay-in vs exit. Per-user live OCO
(FR-EXEC-3), price sanity gate (FR-EXEC-4), paper-desk hydration (FR-EXEC-5), leverage cap
(FR-RISK-2), circuit-breaker halt (FR-RISK-3). **Proof:** a position opened in a session and
then abandoned (session ended, daemon restarted) is still monitored and exits on a thesis
break — demonstrated on testnet.

### M5 — Assistant & memory
Conversational assistant grounded in the user's pulse/book/session events (FR-ASSIST-1/2).
Memory retrieval surfaced in synthesis (FR-MEMORY-2). **Proof:** the assistant answers
"why did you exit BTC?" from real session events; synthesis cites a real past-trade outcome.

### M6 — Monetization & compliance floor
Razorpay/Stripe + `subscriptions` table (FR-BILLING-1); define Starter/Pro session quotas.
Compliance floor: ToS + risk disclosure + automated-execution consent, API-key scope
verification, account deletion/export, KYC gate before any live connection (§10). Money
columns → integer minor units (§7). **Proof:** a real subscription grants a tier; a
withdrawal-capable API key is rejected; the live gate is unreachable without KYC + consent.

### Open product decisions (need the founder — not code)
1. **Free session quota: 30 min/day (code) or 1 hr/day (vision)?** And Starter/Pro minutes?
2. **Which channels ship at launch**, given TDS eats Scalp's edge for Indian users (§10.3)?
3. **Launch as free beta or with payments live?** (Affects M6 ordering and the landing page.)
4. **Delta India only at launch, or also BingX?** (CoinDCX defers — no testnet.)
5. **Mainnet (real money) in the public beta, or paper/testnet only first?**
