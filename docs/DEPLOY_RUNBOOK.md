# CryptAI — Deploy Runbook (fix/m1-foundation-bugs → production)

> Purpose: ship the verified `fix/m1-foundation-bugs` build (M1 fixes + M2 sessions +
> M4 monitor + preferences/channels) to production, replacing the stale `v2` code Render
> runs today. Phased and **reversible** — each phase has a rollback and a verification.
>
> **Division of labor:** the dashboard actions (Render, Vercel, Supabase) are yours — I
> can't log into them. After each phase, tell me it's done and I verify with read-only
> probes of the live services. Do the phases **in order**; don't start a phase until the
> prior one verified.

---

## Safety invariants — these do NOT change in this deploy

The system can place real futures orders. This deploy stays **paper/testnet only**:

- `USE_TESTNET=true` — keep. `LIVE_TRADING_CONFIRMED=false` — keep (never flip here).
- `ENABLE_EXECUTION` — leave unset (paper default).
- Only testnet exchange keys are accepted; the vault endpoint rejects mainnet keys.

If any step tempts you to change one of these to "make it work" — stop. That is never the fix.

---

## Pre-flight (5 min)

1. **Find your Supabase user UUID** (needed in Phase 1). Supabase → Authentication →
   Users → your account → copy the `id` (a UUID). If you haven't signed up on the app
   yet, do that first on the *current* live site, then grab the UUID.
2. **Back up the database.** Supabase → Database → Backups → take a manual snapshot (or
   note the latest automatic one). The new code only *adds* a nullable column and creates
   new tables (both additive, non-destructive), but back up before touching prod anyway.
3. **Note the current Render deploy** of `cryptai-backend` and `cryptai-daemon` (which
   branch/commit each tracks now) so Phase 1 is reversible.

---

## Phase 1 — Deploy the new backend code

Brings M1–M4 + preferences/channels live. The backend + daemon build from the same
`Dockerfile`; the schema self-heals on boot (adds `sessions.channel`, creates the new
session/proposal tables via `checkfirst`) — no manual migration needed.

**Steps (you):**

1. **Set `ADMIN_USER_IDS` on `cryptai-backend`** to your Supabase UUID from pre-flight.
   ⚠️ This is fail-closed: if it's empty, **no one** can control the AI engine switch —
   you'd lock yourself out. (It's declared in `render.yaml` as a `sync:false` secret.)
2. **Repoint both services** `cryptai-backend` and `cryptai-daemon` to track branch
   **`fix/m1-foundation-bugs`**: each service → Settings → Build & Deploy → Branch →
   set it → Save. Then **Manual Deploy → Deploy latest commit** on each.
   - The env you already set (POSTGRES_URL, SUPABASE_URL, VAULT_ENC_KEY, API_AUTH_TOKEN,
     OPENROUTER_API_KEY, API_CORS_ORIGINS) carries over — only `ADMIN_USER_IDS` is new.
3. Wait for both to go green.

**Rollback:** repoint both services back to the previously-tracked branch and Manual
Deploy. No data migration to undo (the added column/tables are additive and harmless to
the old code — it simply ignores them).

**I verify** (tell me when the deploys are green): `/health/ready` still 200 with
`redis:true, database:true` (self-heal ran, DB healthy), and `/api/session` /
`/api/monitors` now return **403** (auth required) instead of **404** — 403 means the new
routes exist, i.e. the new code is live.

---

## Phase 2 — Deploy the signal engine

The always-on Rust engine that publishes `market:pulse:*`. It deploys as its **own**
Render worker (like the frontend deploys separately) — it is NOT in the backend
blueprint. Artifacts are prepared: `signal-engine/Dockerfile` + `.dockerignore`.

**Steps (you):**

1. **Create the service.** Render → New → **Background Worker** → connect the same repo →
   **Root Directory: `signal-engine`** → Runtime **Docker** (it finds `Dockerfile`) →
   plan **starter** → name it `cryptai-signal-engine`.
2. **Env vars on it:**
   - `REDIS_URL` → the **same** `cryptai-redis` this backend uses. Easiest: on the new
     worker, Add Environment Variable → *Add from service* → `cryptai-redis` →
     `connectionString`. (It must be the identical Redis, or the daemon reads an empty
     pulse plane.)
   - `SYMBOLS` — leave the default (`BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT`); it must be
     a **superset** of the daemon's `PLATFORM_SYMBOLS` (`BTCUSDT,ETHUSDT,SOLUSDT`).
   - `RUST_LOG=info`.
3. Deploy. In its logs you should see it bootstrap history and start scoring/publishing
   (per-symbol pulse lines every few seconds).
4. **Only then**, flip **`SIGNAL_PLANE_ENABLED=true`** on `cryptai-daemon` and redeploy
   the daemon.

**Rollback:** set `SIGNAL_PLANE_ENABLED=false` on the daemon and redeploy (sessions/
monitors run ungated again, exactly as in Phase 1); optionally suspend the engine worker.
Turning the engine off never stops monitoring or breaks a session — the pulse gate just
no-ops.

**I verify:** after the daemon redeploys, its logs should read
`Session plane ready | pulse_gating=on`. (Redis pulse keys aren't externally probeable, so
this is a logs check on your side; paste me the relevant lines and I'll confirm.)

---

## Phase 3 — Deploy the frontend and wire it together

**Steps (you):**

1. **Vercel** → New Project → import the repo → **Root Directory: `frontend`** (framework
   auto-detects Next.js).
2. **Env vars:**
   - `NEXT_PUBLIC_SUPABASE_URL` = `https://<ref>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = Supabase → Settings → API → anon key
   - `NEXT_PUBLIC_API_URL` = `https://cryptai-backend.onrender.com`
   - `NEXT_PUBLIC_WS_URL` = `wss://cryptai-backend.onrender.com/ws`  ← **wss**, not ws
   - `CRYPTAI_ADMIN_TOKEN` (server-only, **no** `NEXT_PUBLIC_` prefix) = the same value as
     the backend's `API_AUTH_TOKEN`. Powers the same-origin close-positions route so the
     admin secret never reaches the browser.
   - **Do NOT set `NEXT_PUBLIC_API_TOKEN`.** Leaving it empty makes the browser use the
     user's Supabase JWT — setting it would bundle the admin-capable token publicly (the
     footgun from the audit).
3. Deploy. Note the Vercel URL, e.g. `https://cryptai.vercel.app`.
4. **Wire back:** set the backend's `API_CORS_ORIGINS` to that exact origin and redeploy
   `cryptai-backend`.
5. **Supabase auth:** Authentication → URL Configuration → add the Vercel URL to *Site URL*
   and *Redirect URLs* (so email confirms / OAuth land back on the app).
6. **RLS defense-in-depth:** run `crypto-trading-agent/scripts/sql/rls_trades.sql` in the
   Supabase SQL editor (belt-and-suspenders; app-layer scoping is the primary guard).

**Rollback:** the frontend is independent — deleting/pausing the Vercel project reverts to
no public UI without touching the backend.

**I verify:** the Vercel URL serves 200, and the backend now allows that origin (CORS).

---

## Post-deploy smoke — "does the whole loop work?" (you, ~5 min)

On the live Vercel URL, signed in as yourself (paper mode):

- [ ] Sign up / log in works (Supabase).
- [ ] Settings → **Trading preferences** saves (style, goal, symbols).
- [ ] Overview → **Trading session**: pick a channel, **Start** → the timer runs.
- [ ] Within a cycle, a **proposal card** appears; **Approve** → a paper position opens.
- [ ] Positions table shows the **Watch** dot (the monitor is live).
- [ ] Connect a **BingX VST testnet** key in Settings → the daemon logs pick you up.

Report anything that doesn't light up and I'll debug it against the live logs/probes.

---

## After the deploy — cleanup (not blocking)

- Merge PR #2 (`fix/m1-foundation-bugs`) so the deployed branch becomes canonical, and
  point Render at the merge target; retire the stale `v2`/`main` branches.
- Consider adding a `preDeployCommand: python scripts/migrate.py` to the backend service
  so Alembic becomes the managed source of truth on deploy (the self-heal carries it
  safely until then).
- 34 loose destructive scripts still ship in the image — consolidate behind one guarded
  admin CLI before widening access.
