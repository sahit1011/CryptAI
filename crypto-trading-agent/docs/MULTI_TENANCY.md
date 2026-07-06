# Multi-tenancy — architecture & foundation

CryptAI is moving from a single global bot toward a multi-tenant SaaS. This documents
the target architecture and what is already in place vs. still to build.

## One database (done)

Auth and trading data now live in **one Postgres**: the project's **Supabase** instance.

- **Auth**: Supabase Auth (frontend `@supabase/ssr`) manages users/sessions. Each user
  has a UUID = `auth.users.id`.
- **Trading data**: the backend points `POSTGRES_URL` at the same Supabase Postgres
  (direct connection, e.g.
  `postgresql://postgres:<db-password>@db.<ref>.supabase.co:5432/postgres`).
  `TradeHistoryManager` / `StateManager` create and read their tables there.

Previously the backend used a separate self-hosted Postgres — two databases for one
product. Consolidating removes that split and is the prerequisite for tenant scoping
(auth identity and trading rows now live side by side and can be joined/scoped).

## Scoping primitive (done)

`trades.user_id` (`data_models.Trade.user_id`, indexed, nullable) holds the owning
Supabase user UUID. `TradeHistoryManager.get_recent_trades(..., user_id=...)` filters by
it. Nullable + optional filter keeps single-tenant/legacy rows working unchanged.

## Still to build (ordered)

1. **Identity at the API edge** — verify the Supabase JWT on backend requests (the anon
   JWT is signed by the project's JWT secret) and resolve `request.state.user_id`.
   Today the API uses a single static `API_AUTH_TOKEN`; that becomes an
   internal/service token while user requests carry the Supabase JWT.
2. **Stamp on write** — set `user_id` when persisting trades/positions/portfolio so every
   row is owned. Extend `StateManager` Redis keys to be per-user
   (`state:{user_id}:portfolio`, `positions:{user_id}`, …) instead of global.
3. **Scope on read** — thread `user_id` through `/api/trades`, the WS hydration, and the
   agent feed so a user only ever sees their own data.
4. **RLS defense-in-depth** — enable Postgres Row-Level Security on `trades` (and future
   per-user tables) keyed on `auth.uid()`, so isolation is enforced at the DB even if an
   app-layer scope is missed.
5. **Per-user config & limits** — per-user exchange API-key vault (encrypted), risk
   limits, and enabled symbols.
6. **Billing / usage metering** — subscription tier gating (e.g. number of live symbols,
   agent frequency).

## Engine architecture decision (open)

Two ways to run the trading engine for many users:

- **Shared engine, per-user portfolios (recommended):** one orchestrator/agent process
  computes market analysis once (it's user-independent), then applies per-user risk
  config and books trades against per-user portfolios keyed by `user_id`. Efficient —
  analysis/LLM cost is shared, not multiplied per user.
- **Per-user bot instances:** one process/container per user. Simple isolation but cost
  and ops scale linearly with users; only justified for large/bespoke accounts.

Recommendation: shared engine + per-user portfolio/risk state, with the `user_id`
scoping above. Revisit per-user instances only for enterprise tiers.

## Hard constraint (unchanged)

Live real-money trading stays hard-gated (BingX VST testnet only until validated;
`LIVE_TRADING_CONFIRMED=true` is the user's explicit final step). Multi-tenancy does not
relax this — each tenant's live path is independently gated.
