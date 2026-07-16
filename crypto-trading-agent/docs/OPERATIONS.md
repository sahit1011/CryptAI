# Operations runbook

Day-2 operations for a deployed CryptAI stack: backups, migrations, health, logs.

## Database backup & restore

The trading DB (Postgres) holds trades, encrypted exchange keys, and user settings —
**it is the thing to back up**. Redis is ephemeral state (safe to lose; it repopulates).

### Supabase-hosted Postgres (recommended prod setup)
- Supabase runs **daily automatic backups** (retention by plan tier); Pro adds PITR.
- Manual snapshot before risky changes: Dashboard → Database → Backups, or:
  ```bash
  pg_dump "$POSTGRES_URL" --no-owner --format=custom -f cryptai-$(date +%F).dump
  ```

### Self-hosted Postgres (docker compose)
```bash
# Backup (run from crypto-trading-agent/)
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom > backups/cryptai-$(date +%F).dump

# Restore into a FRESH database
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists < backups/cryptai-YYYY-MM-DD.dump
```
Automate with cron (daily) and keep ≥14 days. Test a restore quarterly — an untested
backup is a hope, not a backup.

**⚠️ VAULT_ENC_KEY is part of the backup story**: user exchange keys are Fernet
ciphertext. A DB restore without the same `VAULT_ENC_KEY` orphans every stored key.
Store the key in your secret manager alongside backup credentials.

## Schema migrations (Alembic)

Migrations are versioned in `alembic/versions/`. The compose `migrate` service runs
[`scripts/migrate.py`](../scripts/migrate.py) before the app starts: it stamps
databases provisioned by the legacy `create_all` bootstrap, then upgrades to head.

```bash
# Status / history
alembic current && alembic history

# Create a migration after editing src/data/data_models.py
alembic revision --autogenerate -m "add <thing>"

# Apply / roll back one step
alembic upgrade head
alembic downgrade -1
```
Rules: never edit an applied migration — add a new one; take a backup before
`downgrade` in production.

## Health endpoints

| Endpoint | Meaning | Use for |
|---|---|---|
| `/health/live` | process is up (no dependency checks) | liveness probe / restart decisions |
| `/health/ready` | Redis + DB reachable; 503 if not | load-balancer routing / readiness probe |
| `/health` | legacy summary (status + WS connections) | dashboards, humans |

A dead Redis makes `/ready` 503 (traffic drains) but `/live` stays 200 (no restart
loop while the dependency recovers).

## Logs & error correlation

- Every API response carries **`X-Request-ID`**; the same ID is stamped on every log
  line emitted while handling that request. Client reports an error → grep the ID.
- `LOG_JSON=true` switches to structured JSON lines (for Loki/Datadog/CloudWatch).
- `SENTRY_DSN=<dsn>` activates error tracking (API + daemon); no-op when unset.
- Client error responses are **generic by design** — full details are server-side only.

## Rate limits (defaults)

240 reads/min + 60 writes/min per caller (user token, else IP), `/health*` exempt,
8 concurrent WS connections per caller. Tune via `RATE_LIMIT_PER_MINUTE`,
`RATE_LIMIT_WRITE_PER_MINUTE`, `WS_CONNECTIONS_PER_CLIENT`.

## Safety gates (do not relax casually)

- `USE_TESTNET=true` + `LIVE_TRADING_CONFIRMED=false`: real-money trading is refused
  until the live path is validated on testnet and the operator flips both deliberately.
- The vault only accepts testnet keys while gated (`is_testnet=false` → 400).
