#!/usr/bin/env python3
"""End-to-end probe of the LIVE trade-ledger path: Redis bus -> daemon -> Postgres.

The offline probe (verify_trade_ledger.py) proves the schema accepts the write.
This proves the wiring: that the running daemon's TradeLedgerConsumer is actually
subscribed to `memory_agent_inbox` and persists what arrives. That is exactly the
thing that was broken for weeks (only the disabled MemoryAgent subscribed), and
"the subscription exists in the code" is not evidence — the wiring law.

Safety: the probe row is owned by a synthetic all-zeros user UUID that belongs to
no tenant, is clearly named, and is DELETED at the end (with the count re-checked).
It never touches an engine, a session, or a real user's data. Read-only otherwise.

⚠️ CANNOT RUN FROM A LAPTOP, BY DESIGN. cryptai-redis is internal-only
(`ipAllowList: []` in render.yaml), so this fails with "Client IP address is not in
the allowlist". **Do not add your IP to run it** — that exposes the message bus to
the internet, and no verification is worth that. Run it from inside the Render
network (a shell on the service, or a one-off job), or accept the cheaper evidence:
the daemon logs `Subscribed to channel: memory_agent_inbox` at boot (confirmed live
2026-08-24 23:39 and 2026-08-25 09:08), `scripts/verify_trade_ledger.py` proves the
real Postgres schema accepts the write, and tests/test_rehydration.py proves the
consumer's behavior. This script closes the last hop when a shell is available.

Run from repo root:  python3 scripts/probe_trade_ledger_live.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import render_ops as ro  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent")
VENV_PY = os.path.join(BACKEND_DIR, ".venv", "bin", "python")

PROBE = r'''
import asyncio, json, os, time
from datetime import datetime, timezone

import redis.asyncio as aioredis
import sqlalchemy as sa

PROBE_ID = "LEDGER_LIVE_PROBE_%d" % int(time.time())
NOBODY = "00000000-0000-0000-0000-000000000000"


async def main():
    r = aioredis.from_url(os.environ["REDISURL"], decode_responses=True)
    msg = {
        "id": "log_%s" % PROBE_ID,
        "correlation_id": "log_%s" % PROBE_ID,
        "sender": "ops_probe",
        "receiver": "memory_agent",
        "type": "log_trade",
        "payload": {
            "trade_id": PROBE_ID,
            "user_id": NOBODY,
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 1.0,
            "entry_time": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "position_size": 0.001,
            "stop_loss": 0.9,
            "take_profit_levels": [1.1],
            "risk_amount": 0.0001,
            "strategy_type": "OPS_PROBE",
            "leverage": 7.0,
            "entry_order_id": "PROBE_E",
            "sl_order_id": "PROBE_SL",
            "tp_order_ids": [{"order_id": "PROBE_TP", "price": 1.1, "size": 1.0}],
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    receivers = await r.publish("memory_agent_inbox", json.dumps(msg, default=str))
    print("published to memory_agent_inbox; live subscribers on this channel: %d" % receivers)
    if receivers == 0:
        print("VERDICT: FAIL — nothing is listening; the ledger is NOT wired")
        await r.aclose()
        return 1

    engine = sa.create_engine(os.environ["PGURL"])
    row = None
    for _ in range(20):                       # the consumer writes in a thread
        await asyncio.sleep(1)
        with engine.connect() as c:
            row = c.execute(sa.text(
                "select trade_id, user_id, leverage, status, sl_order_id, tp_order_ids "
                "from trades where trade_id = :t"), {"t": PROBE_ID}).fetchone()
        if row:
            break

    if row is None:
        print("VERDICT: FAIL — a subscriber acked but no row appeared within 20s")
        await r.aclose()
        return 1
    print("row persisted by the LIVE daemon: leverage=%s status=%s sl=%s tp=%s"
          % (row.leverage, row.status, row.sl_order_id, row.tp_order_ids))

    with engine.begin() as c:
        deleted = c.execute(sa.text("delete from trades where trade_id = :t"),
                            {"t": PROBE_ID}).rowcount
    with engine.connect() as c:
        left = c.execute(sa.text("select count(*) from trades where trade_id = :t"),
                         {"t": PROBE_ID}).scalar()
        total = c.execute(sa.text("select count(*) from trades")).scalar()
    print("probe row deleted (%d); remaining copies %d; journal total %d" % (deleted, left, total))
    print("VERDICT: PASS — Redis bus -> live daemon consumer -> Postgres is wired")
    await r.aclose()
    return 0


raise SystemExit(asyncio.run(main()))
'''


def main() -> int:
    code, envs = ro._req("GET", f"/services/{ro.BACKEND}/env-vars?limit=60")
    if code != 200:
        print(f"Render env fetch failed: HTTP {code}")
        return 1
    values = {e["envVar"]["key"]: e["envVar"]["value"] for e in envs}
    # The service's own REDIS_URL is an INTERNAL Render hostname (red-xxx:6379),
    # unreachable from a laptop — always use the KV's external connection string
    # for operator probes, regardless of what the env var says.
    redis_url = None
    kv = ro._find_kv()
    if kv:
        code, conn = ro._req("GET", f"/key-value/{kv['id']}/connection-info")
        if code == 200:
            redis_url = (conn or {}).get("externalConnectionString")
    redis_url = redis_url or values.get("REDIS_URL")
    if not redis_url:
        print("could not resolve a Redis URL (KV connection-info + env var both failed)")
        return 1

    r = subprocess.run([VENV_PY, "-c", PROBE], cwd=BACKEND_DIR, text=True,
                       capture_output=True,
                       env={**os.environ, "PGURL": values["POSTGRES_URL"],
                            "REDISURL": redis_url})
    print(r.stdout.strip() or "(no output)")
    if r.returncode != 0 and r.stderr.strip():
        print("stderr:\n" + r.stderr.strip()[-1200:])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
