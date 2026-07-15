-- Row-Level Security for multi-tenancy (defense-in-depth) — Supabase Postgres.
--
-- The backend already scopes every read by user_id in application code, and it connects
-- as a privileged role (postgres) that BYPASSES RLS. This policy is the second line of
-- defense: it enforces per-tenant isolation for ANY access that goes through Supabase's
-- `authenticated` role (PostgREST / the JS client using a user's JWT), so a future
-- direct-client query — or an app-layer scoping bug on a role that respects RLS — cannot
-- leak one tenant's trades to another.
--
-- Idempotent: safe to run repeatedly (e.g. in the Supabase SQL editor).
--
-- NOTE: we intentionally do NOT `FORCE ROW LEVEL SECURITY`. Forcing it would also apply
-- to the table owner / service role, breaking the backend's legitimate service queries
-- (unscoped admin reads, cross-tenant maintenance). The service path stays app-scoped;
-- RLS guards the untrusted `authenticated` path.

alter table public.trades enable row level security;

-- Least-privilege grants for the authenticated role (RLS then narrows to own rows).
grant select, insert, update, delete on public.trades to authenticated;

-- A user may only see and write rows they own. user_id is text; auth.uid() is uuid.
drop policy if exists trades_tenant_isolation on public.trades;
create policy trades_tenant_isolation
    on public.trades
    for all
    to authenticated
    using (user_id = auth.uid()::text)
    with check (user_id = auth.uid()::text);

-- Rows with a NULL user_id (legacy/global/single-bot data) are visible to NO
-- authenticated user — they belong to the service/global context only, reachable via the
-- privileged backend. This prevents legacy unowned rows from leaking to any tenant.
