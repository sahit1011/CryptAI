# CryptAI

Multi-agent crypto futures trading engine. Going 0→1 to public paying users.

See `AGENTS.md` for the backend architecture map (agents, message bus, DB layout) —
it is accurate and worth reading before touching `crypto-trading-agent/src`.

**Start here (2026-08-02):** `docs/PRD_CURRENT_STATE.md` — audited ground truth of what
is built/deployed/broken — and `docs/HLD.md` — the target design, functional
requirements, and M1–M6 roadmap. They supersede the entire Jan-2026 doc generation
(`docs/prd.md`, `docs/COMPLETE_SPECIFICATION_SUMMARY.md`, `SETUP.md`, etc.).

## ⚠️ Branches: work on `feat/m0-foundation`

Three-branch reality (verified 2026-08-02):
- **`feat/m0-foundation`** — the active branch: `v2` + 21 commits (sessions, proposals,
  preferences, Rust signal engine). All new work lands here.
- **`v2`** — what production Render actually deploys (probed: the live host 404s the
  m0 session/preferences endpoints). The signal engine does not exist on it.
- **`main`** — stale 8-commit snapshot, still the GitHub default. Its only exclusive
  files are cruft plus the keepalive workflow copy.

**Open task (M1):** make the m0 line the default branch and repoint Render — until then
every fix on this branch is silently absent from production, and the deployed `/health`
still has the lying-probe bug that is already fixed here.

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
npm test                 # vitest run — 52 tests, <1s
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
`.claude/verify.sh` gates every turn in **~6s**. Four checks:
frontend typecheck · 52 frontend unit tests · backend import smoke · 309 backend tests.

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

**Remaining:** 189 tests are quarantined as "stale, drifted from the current
API" (see `tests/conftest.py`) out of 500 collected. That's ~38% providing no protection —
the largest correctness gap in the repo. Un-quarantine them incrementally. Never
un-quarantine by loosening an assertion.

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
- 34 loose one-off scripts sit at `crypto-trading-agent/` root — `nuclear_clear_positions.py`,
  `force_close_positions.py`, `delete_all_trades.py`. These are **destructive and
  operate on real trade state**. Never run one to "clean up" during development.
- `httpx` is pinned `<0.28` deliberately — unpinning broke the Analysis + Strategy agents.
- OpenRouter free-tier models are **rotated**, not pinned; a dead model previously
  made the engine silently produce nothing.
- Some unit tests were quarantined to make CI honest. Don't un-quarantine without fixing.
- loguru format strings crash on unescaped braces — keep error messages brace-safe.

## Before real users
Run `/prod-audit` and the `security-auditor` subagent. For this product the ranked
risks are: cross-user trade leakage, accidental live execution, and unbounded LLM
spend per user.
