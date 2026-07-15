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

1. **Identity at the API edge — DONE.** The API verifies each request's Supabase JWT
   against the project JWKS (ES256) and resolves the tenant's `user_id`; the static
   `API_AUTH_TOKEN` is now the internal/service credential. (`src/api/server.py`
   `verify_supabase_jwt` / `current_principal`.)
2. **Stamp on write — DONE.** Published state + persisted portfolio/positions carry the
   owning `user_id`, and `StateManager` Redis keys are per-user
   (`state:{user_id}:portfolio` hash, `state:{user_id}:positions` list). The paper engine
   stamps `self.user_id`.
3. **Scope on read — DONE.** `/api/trades` scopes by the principal's `user_id`; the WS
   handshake authenticates the JWT and the `ConnectionManager` delivers each tenant only
   their own messages (per-user hydration cache + activity replay).
4. **RLS defense-in-depth — DONE.** `scripts/sql/rls_trades.sql` enables Postgres RLS on
   `trades` and `exchange_credentials`, restricting the `authenticated` role to
   `user_id = auth.uid()`; the privileged backend bypasses and app-scopes.
5. **Per-user config & keys — DONE (keys).** Encrypted per-user exchange-key vault
   (`src/security/credential_vault.py`, Fernet) + `/api/exchange-keys` (testnet-gated).
   Per-user risk config flows through `UserRiskConfig` (see engine below). Per-user
   symbol selection is a thin follow-on.
6. **Billing / usage metering — TODO.** Subscription tiers, usage limits.

## Engine architecture — DECIDED & IMPLEMENTED: shared engine, per-user portfolios

Implemented in `src/core/multi_user.py`. Market analysis (data → indicators → regime →
candidate setups) is **user-independent and computed once per cycle**; only risk
validation + execution are per-user:

- **UserSession** — a tenant's isolated resources: their own `PaperTradingEngine`
  (stamped with `user_id`), `OrderManager`, `PortfolioStateTracker`, and
  `DeterministicRiskCalculator`. A live exchange client built from the vault keys can be
  injected in place of the paper engine.
- **UserRegistry** — discovers/caches active tenants (those with vault credentials).
- **MultiUserExecutor.book_for_all(setup)** — validates one shared setup against each
  tenant's portfolio and books it into their engine independently; fault-tolerant (one
  tenant's failure doesn't abort the rest).
- **MultiUserCoordinator.run_cycle(analysis_provider)** — the daemon loop primitive:
  runs the shared analysis ONCE, then fans every setup out to all active tenants.

**Integration seam for the daemon:** provide `analysis_provider` as an async callable
that runs the existing analysis pipeline (the orchestrator's data/analysis/regime/strategy
phases) once and returns setup dicts; the coordinator handles per-user risk + booking.
Verified by `tests/test_multi_user.py` (shared-once, per-tenant isolation, fault
tolerance). Per-user bot instances remain an option only for bespoke/enterprise tiers.

## Hard constraint (unchanged)

Live real-money trading stays hard-gated (BingX VST testnet only until validated;
`LIVE_TRADING_CONFIRMED=true` is the user's explicit final step). Multi-tenancy does not
relax this — each tenant's live path is independently gated.
