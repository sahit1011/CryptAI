# Deploying CryptAI (multi-tenant SaaS)

This gets CryptAI reachable at a public URL where a user can sign up, connect their
exchange, and have the agents trade their own account. Four moving parts:

| Part | What | Where |
|------|------|-------|
| **Auth + Postgres** | users, trades, encrypted keys | **Supabase** (already provisioned) |
| **Redis** | message bus + per-user state | Render (managed) or your host |
| **Backend** | FastAPI API + WebSocket | Render web service |
| **Daemon** | multi-user trading engine | Render background worker |
| **Frontend** | Next.js dashboard | Vercel (or Render web service) |

> **Safety gate stays on.** Every deploy ships with `USE_TESTNET=true` and
> `LIVE_TRADING_CONFIRMED=false`. Only BingX **VST testnet** keys are accepted until the
> live path is validated. Do not flip these without deliberately validating live.

---

## 0. Secrets you need first

Generate/collect these once:

```bash
# Vault master key (encrypts users' stored exchange keys). Generate ONCE, keep stable.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Service/admin token (close-positions etc.)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- **POSTGRES_URL** — Supabase session pooler URI (Supabase → Settings → Database →
  *Connection string* → **Session** pooler, port 5432):
  `postgresql://postgres.<ref>:<db-password>@aws-1-<region>.pooler.supabase.com:5432/postgres`
- **SUPABASE_URL** — `https://<ref>.supabase.co`
- **NEXT_PUBLIC_SUPABASE_ANON_KEY** — Supabase → Settings → API → anon key
- **LLM key** — an `OPENROUTER_API_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).
  Without it, analysis/strategy/insights are disabled and the daemon books nothing.

---

## Option A — Render + Vercel (recommended, gives a URL fast)

### A1. Backend + daemon + Redis → Render

1. Push this repo to GitHub. In Render, **New → Blueprint**, point it at the repo.
   Render reads [`render.yaml`](./render.yaml) and creates `cryptai-redis`,
   `cryptai-backend`, and `cryptai-daemon`.
2. Fill the `sync: false` env vars on **both** `cryptai-backend` and `cryptai-daemon`:
   `POSTGRES_URL`, `SUPABASE_URL`, `VAULT_ENC_KEY`, `OPENROUTER_API_KEY`
   (backend also: `API_AUTH_TOKEN`, `API_CORS_ORIGINS`; daemon also optional
   `MULTI_USER_SEED_IDS`). `REDIS_URL` is wired automatically.
3. Deploy. Note the backend URL, e.g. `https://cryptai-backend.onrender.com`.
   Check `GET /health` returns ok.

### A2. Frontend → Vercel

1. Import the `frontend/` repo in Vercel (framework auto-detected as Next.js).
2. Set env vars:
   - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL` = `https://cryptai-backend.onrender.com`
   - `NEXT_PUBLIC_WS_URL` = `wss://cryptai-backend.onrender.com/ws`  ← **wss**, not ws
   - `API_TOKEN` (server-only, no `NEXT_PUBLIC_`) = the same `API_AUTH_TOKEN` — used by
     the same-origin `/api/close-positions` route so the admin secret never reaches the browser.
3. Deploy. Note the frontend URL, e.g. `https://cryptai.vercel.app`.

### A3. Wire them together

- Set the backend's **`API_CORS_ORIGINS`** to the exact frontend origin
  (`https://cryptai.vercel.app`) and redeploy the backend.
- In Supabase → Authentication → URL Configuration, add the frontend URL to
  **Site URL / Redirect URLs** so email confirmations land back on the app.

---

## Option B — Self-host with Docker Compose

One host (VPS) running everything, including a local Postgres if you don't use Supabase.

```bash
cp .env.example .env      # then fill it (POSTGRES_URL, REDIS_URL, VAULT_ENC_KEY, LLM key, NEXT_PUBLIC_*)
docker compose up -d --build
```

Compose services (see [`docker-compose.yml`](./docker-compose.yml)):
`redis`, `postgres`, `migrate` (one-shot), `backend` (:8000), **`daemon`** (the
multi-user engine — runs by default), `frontend` (:3000). The legacy single-bot
`worker` is behind `--profile legacy` and stays **off** (running both would double-trade).

Put a TLS reverse proxy (Caddy/nginx) in front of `:8000` and `:3000` for a public
HTTPS URL, and set `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL` to the `https`/`wss` origin.

To point a self-hosted stack at Supabase instead of the local Postgres, set
`POSTGRES_URL` to the Supabase pooler URI; the local `postgres` container simply goes unused.

---

## 1. Post-deploy checklist — "can my friend sign up and trade?"

- [ ] Friend opens the frontend URL, signs up / logs in (Supabase).
- [ ] **Connect** tab → pastes BingX **VST testnet** key + secret → shows "Exchange connected".
- [ ] Backend logs show the daemon picked them up as an active tenant next cycle.
- [ ] Overview/Portfolio/Agents populate from their own scoped data over the WebSocket.
- [ ] Apply RLS once (defense-in-depth): run [`scripts/sql/rls_trades.sql`](./scripts/sql/rls_trades.sql)
      in the Supabase SQL editor.

If insights/trades never appear: confirm the **LLM key** is set on both backend and daemon,
and that market-data egress is open on the host (the daemon needs the exchange feed).
