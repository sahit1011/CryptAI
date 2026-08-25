# CryptAI

Multi-agent crypto futures trading engine. Going 0→1 to public paying users.

See `AGENTS.md` for the backend architecture map (agents, message bus, DB layout) —
it is accurate and worth reading before touching `crypto-trading-agent/src`.

**Start here (2026-08-24):** the doc hierarchy, newest first —
1. **`docs/plan-2026-08/`** — the current rescue plan: 6 PDFs (audit → product → system
   design → UX → infra → roadmap) + editable HTML sources in `src/`. **The roadmap
   (doc 06, task IDs R0.x–R4.x) is the work queue — pick ONE task ID per session.**
2. `docs/ARCHITECTURE.md` — what the code actually does today (verified 2026-08-11).
3. `docs/PRD_CURRENT_STATE.md` + `docs/HLD.md` — the 2026-08-02 baseline + FR-* target
   design. Still authoritative for anything the plan docs don't cover.
4. `backtest-lab/FINDINGS.md` — the committed quant evidence ledger (what has been
   tested offline, what it licenses, what it forbids). Authoritative for strategy claims.
Superseded docs live in **`_attic/`** (see its README) — never cite them as current.

**Queue status (2026-08-25):** R0 ✅ · R1 ✅ (all of R1.2–R1.7) · R2.1 ✅ rehydration ·
S1/S2 strategy split scaffolded (S1 flag OFF, awaiting lab evidence). **Next: R2.2**
slot metering v2 — a slot is spent on PROPOSAL DELIVERY, not session start.

## ⚠️ Branches: work on `fix/m1-foundation-bugs`

Reality (verified 2026-08-24):
- **`fix/m1-foundation-bugs`** — the active branch (`v2` + 44 commits: wired session
  pipeline, per-user synthesis, proposals, monitors, session billing, bandwidth fixes).
  All new work lands here. Production Render **tracks this branch with autoDeploy** —
  a push deploys the moment the service is resumed.
- **`v2`** — 44 commits behind, but **still the GitHub default branch**, which means
  scheduled workflows (the load-bearing keepalive) run ITS stale copies. Flipping the
  default to the m1 line is task R1.2.
- `feat/m0-foundation`, `main` — historical; do not build on them.

**Production is LIVE and healthy** (restored 2026-08-24 after the Aug-10 bandwidth
suspension; R0 + R1 + R2.1 deployed). What is live: demand-gated streams, the Rust
engine publishing `market:pulse:*` every 5s with `SIGNAL_PLANE_ENABLED=true`, the
calibration ledger writing `pulse_snapshots`, the daily LLM request budget, and
engine rehydration. Ops via `scripts/render_ops.py` (status/set-env/resume/verify).

**⚠️ The BACKEND auto-deploys from this branch; the FRONTEND does not.** Render
redeploys `cryptai-backend` on every push to `fix/m1-foundation-bugs`. Vercel's
`cryptai` project (cryptai-app.vercel.app) has NOT deployed since 2026-08-12 —
its git integration is not following the active branch (GitHub's default is still
the stale `v2`, task R1.2). So "pushed" means shipped for the API and NOT shipped
for the UI. Check `npx vercel ls cryptai` before claiming a UI change is live;
ship it with `cd frontend && npx vercel --prod` (run `npm run build` first —
verify.sh deliberately skips it), and roll back with
`npx vercel rollback <previous-url>`.

Two things that look like incidents but are not:
- **Every deploy reboot eats a Binance 418 on the shared Render IP** — and it can cost
  up to ~1h of signal plane, not the ~15 min first observed. Measured 2026-08-25: the
  plane published for 9 minutes (09:00–09:08), then a deploy restart hit a ban and it
  recovered at **10:51** — 1h42m later, self-healed, exactly when the engine's computed
  backoff said (600s → 3302s parsed from the venue's own ban timestamp). Do not
  intervene; do not add retries. **We are not causing these bans**: bootstrap is 12
  requests at weight ~24 against a 1200/min limit — other Render tenants on the shared
  egress IP burn the quota. Consequence to respect: with `SIGNAL_PLANE_ENABLED=true`
  the pulse gate fail-closes, so no user can start a scan during a ban (they see
  "Market analysis is offline… your scan time is safe" — correct and honest). **Batch
  deploys** rather than pushing each commit; each restart re-rolls this dice.
  A Redis warm-start cache does NOT fix it — pulses carry the market data's `feed_ts`,
  so cached candles produce pulses the staleness gate rightly rejects (see
  `staleness_uses_feed_ts_not_computation_ts`). The only real fix is a fallback data
  venue, which is an open founder decision, not a queued task.
- **Free tier sleeps after ~15 min idle**; the GitHub keepalive cron is load-bearing.

## Layout
```
crypto-trading-agent/   Python 3.12 backend — LangGraph multi-agent engine
frontend/               Next.js 16 + React 19 dashboard & trading terminal
```

## Stack
**Backend:** Python 3.12 · LangGraph/LangChain · FastAPI (`src.api.server`) ·
SQLAlchemy + Alembic on Supabase Postgres · Redis hot cache · pandas-ta ·
loguru · OpenRouter + Anthropic + OpenAI. Deployed on Render (`render.yaml`).

**Frontend:** Next.js 16.2 · React 19 · Supabase auth (SSR) · TanStack Query ·
Zustand · lightweight-charts · Tailwind + shadcn/ui · Vitest + Playwright.

## Commands
```bash
# Frontend
cd frontend && npm install
npm run dev              # next dev
npm run build
npm test                 # vitest run — 99 tests, ~1s
npm run test:e2e         # playwright
npx tsc --noEmit

# Backend (venv at crypto-trading-agent/.venv, Python 3.12)
cd crypto-trading-agent
.venv/bin/pytest                        # hermetic: contract + unit, fully mocked
.venv/bin/pytest tests/integration      # opt-in, needs live Redis + Postgres
.venv/bin/python -c "import src.api.server"   # import smoke test
.venv/bin/python -m src.main            # run the engine
.venv/bin/flake8 src tests              # non-blocking in CI
```

### Backend setup
Already done locally: venv at `crypto-trading-agent/.venv` on Python 3.12.13 (pyenv),
`requirements-dev.txt` installed — pandas 3.0.5, numpy 2.2.6, httpx 0.27.2.

To rebuild:
```bash
cd crypto-trading-agent
~/.pyenv/versions/3.12.13/bin/python -m venv .venv
.venv/bin/pip install --upgrade pip wheel setuptools
.venv/bin/pip install "numpy>=1.26.4"     # must precede other builds
.venv/bin/pip install -r requirements-dev.txt
```

**ta-lib is not needed** — v2 removed it (`pandas-ta` replaced it) precisely because
the C library broke installs. The ta-lib build step still in `ci.yml` is stale
relative to v2 and wastes CI minutes; deleting it is a safe cleanup.

## Verification
`.claude/verify.sh` gates every turn in **~38s**. Four checks:
frontend typecheck · 99 frontend unit tests · backend import smoke · 796 backend tests.
Signal-engine changes additionally need `cargo test` (129 tests) — cargo is NOT on the
default PATH; use the rustup shims at `/opt/homebrew/opt/rustup/bin` (pinned 1.97.1).
`cargo clippy --all-targets -- -D warnings` is CLEAN as of 2026-08-25; keep it that way.

Not covered, and why:
- `npm run build` — ~60s. Run before pushing.
- Playwright e2e, and `tests/integration` (needs live Redis + Postgres).
- The **191 quarantined/skipped backend tests** (see below).

First run in a fresh clone can take ~50 min: chromadb downloads an ONNX embedding
model on first use. That is one-time — every run after is ~6s.

## Backend test suite: was 64s, now 3s
`tests/unit/test_circuit_breaker.py::test_auto_reset_enabled` contained a literal
`time.sleep(61)` — **95% of the suite's entire runtime in one line**. Fixed 2026-08-01
by rewinding `triggered_at` past the cooldown instead, which exercises the identical
`datetime.now() - triggered_at >= cooldown_minutes` branch in `reset()`. Same 204
tests pass; nothing was weakened.

Keep this pattern: never `sleep()` to wait out a cooldown, expiry, or retry window.
Rewind the stored timestamp or inject the clock.

**Remaining (re-counted 2026-08-25):** 191 tests are quarantined as "stale, drifted from
the current API" (see `tests/conftest.py`) out of 987 collected — 796 pass. ~19% of the
suite provides no protection — a standing correctness gap. Un-quarantine incrementally.
Never un-quarantine by loosening an assertion.

Run the quarantined tests to see their real failures without editing the list:
```bash
CRYPTAI_RUN_QUARANTINED=1 .venv/bin/pytest tests/unit/test_state_manager.py -q
```

**⚠️ "Quarantined" does not always mean "stale."** `test_order_manager` was
un-quarantined 2026-08-02 and it had **not** drifted — it was correctly failing because
it asserted the *old, dangerous* rollback behaviour (cancel a filled entry, which is a
no-op that leaves a naked unprotected position). The code had been fixed to close
reduce-only; the test was quarantined rather than updated. **Read each quarantined
failure before assuming the test is at fault — some of them are real signal.**

## M0 findings (verified 2026-08-02) — read before M1

Architecture for the session/agent rebuild is in **`docs/MULTI_TENANCY.md`** (design
contract, not yet built). Ground truth established this session:

**CoinDCX has NO testnet.** Checked against `docs.coindcx.com`: only
`api.coindcx.com` / `public.coindcx.com` are documented — no sandbox base URL exists.
The CoinDCX write path therefore cannot be validated without real money on production.
Delta India *does* have one, and `DeltaExchangeClient.TESTNET_URL`
(`cdn-ind.testnet.deltaex.org`) is correct. **Consequence: Delta is the reference live
adapter; CoinDCX order placement stays unproven until a manual small-size prod smoke.**

**`/health` lied, and `render.yaml` probed it — FIXED on this branch** (commit
`c793c0e`: `/health` now pings Redis, `render.yaml:35` probes `/health/live`). Still
live in production, which deploys `v2` — the fix ships when Render is repointed (M1).

**`/api/setups` is unauthenticated by design** — "setups are the same for everyone;
only EXECUTION is per-user". That is exactly the model `docs/MULTI_TENANCY.md`
supersedes. When setups become per-user synthesis, this endpoint **must** become
authenticated and user-scoped. Tracked as a tenancy blocker, not a nice-to-have.

**The API boots fine without Redis or Postgres** — it logs the failure and degrades
rather than crashing. Verified by probe: `/health` 200, `/health/ready` 503,
`/api/portfolio` and `/api/settings` 403 (fail-closed auth), `/api/setups` 200.

**No Redis, Postgres, or Docker locally.** Unit tests are hermetic so this does not
block them; `tests/integration` and any real boot do need services (`brew install
redis postgresql@16`).

**New schema layer.** `user_preferences`, `sessions`, `session_events`, `proposals`,
`pulse_snapshots` — models in `src/data/data_models.py`, migration
`alembic/versions/9c4e7a1b2d03_*`. Purely additive, safe to apply ahead of the code.
`tests/test_schema_migration_parity.py` builds the schema from *both* the models and
the migration and diffs them, so they can never drift; it also asserts the tenancy
boundary (`pulse_snapshots` must never gain a `user_id`; every per-user table must have
an indexed one).

**The gate was hiding 97 tests.** `pytest.ini`'s `testpaths` was a two-entry allowlist
(`tests/test_exchange_contract.py` + `tests/unit`), so every file at `tests/` root —
including `test_multi_user.py` (tenancy) and `test_oco_management.py` (money safety) —
never ran, and any new file added there would have been excluded silently. Widened to
the whole `tests/` tree; `tests/integration` stays opt-in via `norecursedirs`. **309
passing / 191 skipped, was 213 / 189.** If you add a test file, confirm it appears in
`pytest --collect-only -q`.

**`MessageBus.connect()` reported success without connecting.** `redis.from_url()` is
lazy — no socket until the first command — so `connect()` logged "connected to Redis"
against a dead Redis and the failure surfaced later somewhere else. It now pings.
Same root cause as the `/health` bug: **constructing is not reaching.** Assume any
"connected"/"initialized" flag in this codebase is unverified until you see a ping.

**Money precision debt.** The new tables use `Float` to match the existing `trades`
columns they join against, which conflicts with the workspace integer-minor-units rule.
Mixing `Numeric` into new tables while old ones stay `Float` would create conversion
bugs at the boundary — the fix is one wholesale migration across all money columns.
`currency` columns were added now since INR settlement on the Indian venues is additive.

## Known state (verified 2026-08-01, on v2)
- `frontend`: `tsc --noEmit` clean, **52/52 vitest passing**, `npm run build` passes.
- Backend unit tests are **hermetic** — mocked Redis/Postgres, no Docker needed.
  CI proves this; only `tests/integration` needs services.
- A live backend runs at `cryptai-backend.onrender.com`, kept awake by a GitHub
  Actions cron because Render free tier sleeps after ~15 min.
- Docker is **not installed locally**. Only needed for the integration suite
  (`docker-compose.yml` provides redis + postgres + pgadmin).

## The four laws (2026-08-24 — this repo's scar tissue, enforce in every session)
1. **The wiring law:** "tested" ≠ "wired". Never claim a feature done without tracing a
   constructor from an entrypoint (`src/api/server.py` or `src/multi_user_daemon.py`).
   Tested-but-unwired libraries are this repo's signature failure, three audits running.
2. **The cost law:** every stream, loop, and LLM call must name its live consumer
   (a session, a viewer, an open position) or it doesn't ship. Never subscribe at process
   startup. Bandwidth budget: 5 GB/mo ≈ 167 MB/day for the whole Render workspace —
   state bytes/day×30 for any new network loop. The Aug-10 suspension was this law broken.
3. **The money law:** never widen a risk gate, cap, or stop to get green; the two
   execution gates stay fail-closed; every query filters `user_id`.
4. **The honesty law:** no fabricated numbers in the UI; regime is never mapped to a
   trade direction (empirically refuted); no forward "hottest hour" claims until logged
   calibration data earns them.

The wiring law has a corollary the ledger P0 earned (2026-08-25): **when a component
is made optional, check what else was riding on it.** `DAEMON_DISABLE_AGENTS=memory`
(needed — chromadb won't fit 512MB) silently removed the ONLY subscriber to
`memory_agent_inbox`, so production persisted **zero trade rows** for weeks: no user
journal, no outcome ledger, nothing for rehydration to restore. `src/core/trade_ledger.py`
is now the non-optional row-persistence core; exactly one of it or `MemoryAgent`
subscribes (both would double-insert). Before disabling anything, grep for its
subscriptions and constructor side effects.

## Persistence & restart (R2.1, live 2026-08-25)
Restarts are routine on free tier (deploys, crashes, sleep/wake), so **rows are the
source of truth and Redis is a display cache to be converged, never believed.**
- `src/core/rehydration.py` rebuilds each paper desk from `trades` (open = `exit_time
  IS NULL`; `status` now written too but historical rows predate it). Positions use
  `POS_{trade_id}` — the close path strips that prefix to find the row, so any other
  convention updates the WRONG trade. SL/TP legs are re-placed through the engine's
  own order methods so the tick loop fills them identically to live ones.
- **Trading is blocked per-user until their pass completes** (`UserSession.rehydrated`
  tri-state; `None` = no regime, `False` = pending/failed → bookings refused, `True` =
  done). Failures fail CLOSED and are isolated per tenant.
- Boot order in `MultiUserTradingDaemon.start()` is load-bearing and tripwired by
  `tests/test_rehydration.py::test_boot_ordering_is_wired`: rehydrate AFTER
  `initialize_multi_user()`, BEFORE the `user_commands` subscribe, the tick loop, the
  stream gate, and `MonitorSupervisor(` construction.
- `scripts/verify_trade_ledger.py` proves the write path against real Postgres inside
  an always-rolled-back transaction (the unit tests use sqlite).

## The offline quant lab (`backtest-lab/`, never shipped)
Excluded from the Docker image; own venv (nautilus 1.x installed, unused so far);
`data/`+`results/` gitignored and regenerable via `download_klines.sh`. It imports
strategy math **from `crypto-trading-agent/src/`** so evidence is about shipped code.
`FINDINGS.md` is the committed ledger — read it before proposing strategy work, and
**pre-register the next experiment there before running it** (no threshold sweeps
after the fact). Current verdict: S1's absorption→flip confirmation is a real
*filter* but no implementable entry captures it; `S1_ENABLED` stays false.

## Money safety — read before touching execution
This system can place real futures orders. Two independent gates, both fail-closed:
- `ENABLE_EXECUTION=false` → paper trading. **This is the default. Keep it.**
- Mainnet additionally requires `LIVE_TRADING_CONFIRMED=true`
  (`src/execution/live_execution_engine.py`).

Never flip either to make a test pass or a feature "work". Never widen a risk gate,
position-size cap, or stop-loss to get green. Default to `USE_TESTNET=true` locally.
Every user gets a seeded $10k paper desk — build and verify against that.

## Multi-tenancy
Trades are per-user. The backend scopes reads by `user_id` in application code and
connects as a privileged role that **bypasses RLS**; `scripts/sql/rls_trades.sql` is
defense-in-depth for anything hitting Postgres as the `authenticated` role. So an
app-layer scoping bug is NOT caught by RLS on the backend path — every new query must
filter by `user_id` explicitly. Treat a missing filter as a launch blocker.

## Gotchas
- The 44 loose one-off scripts (incl. `nuclear_clear_positions.py`, `delete_all_trades.py`)
  were retired to `_attic/cta-scripts/` on 2026-08-24 and no longer ship in the image.
  **Never run anything from `_attic/`** — the sanctioned path for those operations is
  `python3.12 scripts/admin.py <cmd> --confirm`.
- `httpx` is pinned `<0.28` deliberately — unpinning broke the Analysis + Strategy agents.
- OpenRouter free-tier models are **rotated**, not pinned; a dead model previously
  made the engine silently produce nothing.
- Some unit tests were quarantined to make CI honest. Don't un-quarantine without fixing.
- loguru format strings crash on unescaped braces — keep error messages brace-safe.

## Before real users
Run `/prod-audit` and the `security-auditor` subagent. For this product the ranked
risks are: cross-user trade leakage, accidental live execution, and unbounded LLM
spend per user.
