# CryptAI — Production Rebuild Plan

> Goal: turn a half-broken personal project into a **production-ready, real-time,
> multi-tenant SaaS crypto-trading platform**.
> Hard safety constraints: trading is validated on **BingX VST testnet only**; live
> real-money trading stays **hard-gated** (the owner flips `LIVE_TRADING_CONFIRMED=true`
> as the final manual step). No mainnet orders are ever placed by this rebuild.

Audit basis: 8-subsystem agent audit (2026-07-04) + direct P0 reproduction. The core is
genuinely real (LangGraph orchestrator, Redis message bus, live Binance data, real
SMC/ICT analysis, working paper engine) — but the **canonical entrypoint could not boot**
and multiple execution/analysis/SaaS layers were broken or absent.

---

## Current-state verdict

**The system could not boot at all** before this rebuild (three independent P0s):
1. LangGraph graph failed to compile under pinned `langgraph==0.2.0` — `handle_error`
   node was unreachable (`ValueError: Node 'handle_error' is not reachable`). Reproduced
   deterministically. → **FIXED** (errors now route into `handle_error`; short-circuits
   wasted downstream LLM calls too).
2. `main.py` constructed `DataCollectionAgent` with kwargs it doesn't accept → `TypeError`.
   → **FIXED**.
3. `main.py` never constructed an `ExecutionAgent`, so every approved trade timed out into
   the void; the only complete pipeline lived in the legacy `run_paper_trading_simulation.py`.
   → **FIXED** (main.py now wires PaperTradingEngine + ExecutionAgent, paper by default,
   live path env-gated + hard-gated).

Beyond boot: BingX live path has real bugs (signing order, order-envelope parsing, Binance
vs BingX field names), no OCO/reconciliation wiring, risk circuit-breaker unit bugs, and
**zero multi-tenancy** (one global bot; Supabase frontend identity is not linked to backend).

---

## Frontend design direction (decided)

**"Trading terminal"** — a focused, professional fintech aesthetic:
- Near-black canvas (`#0a0b0d`-ish), layered elevated surfaces, hairline borders.
- Single confident accent = **emerald/green** for the trading identity, with red reserved
  strictly for loss/sell/danger. Numbers in a **monospace** face (Geist Mono) so P&L,
  prices, and sizes align and read like a terminal.
- Dense but calm information architecture: real-time tiles, live charts (lightweight-charts),
  an agent-activity feed, positions/portfolio, and honest empty/loading/error states.
- No fabricated metrics anywhere. Every number traces to the backend API/WS or shows an
  honest empty state. Dark-only (a trading product lives in the dark).

---

## Phases

Each phase is executed by a focused agent fleet, verified, and committed before the next.

### Phase 1 — Architecture + critical boot fixes  ✅ (in progress)
- [x] Orchestrator graph compiles (error routing + short-circuit).
- [x] `main.py` boots all agents including ExecutionAgent (paper default, live env+hard gated).
- [ ] MessageBus survives Redis outage (reconnect w/o busy-spin; store task handles).
- [ ] Startup state recovery actually reconciles vs exchange (not cosmetic).
- [ ] Pub/sub request/response race (subscribe before publish); bounded persist queues.
- [ ] Signal-safe shutdown (loop.add_signal_handler; guarded single stop; drain cycle).

### Phase 2 — Frontend rebuild + UI/UX product design
- Trading-terminal design system (tokens, typography, components).
- Real data everywhere; WS auth token wired (`useMarketData` sends bearer).
- Remove admin token from public bundle (`NEXT_PUBLIC_API_TOKEN`) — route destructive
  actions through an authenticated server route, not the browser.
- Landing → auth → dashboard flows; loading/empty/error states; responsive.

### Phase 3 — Core backend + trading engine (testnet-ready)
- BingX: signing over the exact transmitted query string; un-nest `data.order` envelope;
  map BingX position/field names (avgPrice/unrealizedProfit); normalize symbol everywhere.
- OCO management (register fill callbacks, link SL/TP legs); `_handle_sl_trigger` force
  reduce-only close; feed prices into PositionMonitor.
- OrderManager: stop swallowing exceptions; real rollback of filled entries; persist
  `trade_executions` (survive restart); idempotent client-order-ids across retries.
- `EmergencyExit` → OrderTracker API mismatch (`get_active_orders`).
- BingX VST testnet smoke harness (`scripts/testnet_smoke.py`).

### Phase 3b — Market data / analysis / risk correctness
- Circuit-breaker unit mismatch (trips at ~0.1%); daily-loss uses real equity not $10k.
- `check_correlation` / `reset_daily_stats` non-reentrant-lock deadlocks; wire daily reset.
- Confluence inflation (dedupe across timeframes); HTF bias uses latest structure break.
- pandas-ta Bollinger middle/width column collision; position-size unit conflict.
- WS reconnect + staleness; ICT killzone timezone.

### Phase 4 — AI multi-agent system fully functional
- Memory agent: fix signature mismatches; make the learning loop real (trade outcomes →
  vector memory → similarity retrieval informs future decisions).
- LLM robustness: 3-tier fallback that actually works (fix Groq path); JSON-mode parsing;
  cache keys keyed on real context; cost controls.
- Agent supervision: health monitor + auto-restart wired into main.py; orchestrator hears
  `agent_error` instead of eating timeouts.

### Phase 5 — SaaS wiring (product layer)
- Link Supabase identity ↔ backend API auth (verify JWT; per-user scoping).
- Tenancy foundation: users table + `user_id` scoping on state/positions/trades; per-user
  exchange API-key vault (encrypted), per-user risk config. Architecture: **shared engine,
  per-user portfolios/config** first (single deploy), designed so per-user isolation can
  come later without a rewrite.
- Persistence: async DB access in the API (no per-request engine); real Alembic migrations.
- Infra: fix conflicting `requirements.txt` pins; Redis auth; healthchecks; CI; consolidate
  ~50 loose destructive scripts into one guarded admin CLI. Deploy to a container platform
  (never serverless — stateful WS + long-running loop).

---

## Verification model
- No Redis/Postgres/Docker assumed in CI-of-record; local dev uses brew Redis + SQLite/PG.
- Backend: `py_compile` + unit/contract tests (no network) + boot smoke (Redis only) +
  full paper-trading run locally; live path only ever on BingX VST testnet.
- Frontend: `next build` green + manual flows.
- Live trading remains hard-gated pending the owner's testnet validation.
