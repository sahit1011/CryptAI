#!/usr/bin/env python3
"""Verify the R2.1 trade-ledger write path against the REAL Postgres schema.

Why this exists: the ledger's tests run on sqlite. Production is Supabase
Postgres, where column types (JSON vs JSONB), the new `leverage` column, and the
explicit `status` write can behave differently. Until a real user books a trade,
nothing proves the row insert works there — and the failure mode is silent
(the consumer logs an error and the journal stays empty, exactly the P0 this
task fixed).

Safety: everything runs inside ONE transaction that is ALWAYS ROLLED BACK. The
row is written, read back, asserted, and discarded — production data is never
modified. No secrets printed; POSTGRES_URL is fetched from the Render API into
memory only.

Run from repo root:  python3 scripts/verify_trade_ledger.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import render_ops as ro  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent")
VENV_PY = os.path.join(BACKEND_DIR, ".venv", "bin", "python")

PROBE = r'''
import os
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.data.data_models import Trade

engine = sa.create_engine(os.environ["PGURL"])

# 1. the schema itself
cols = {c["name"]: c for c in sa.inspect(engine).get_columns("trades")}
assert "leverage" in cols, "trades.leverage MISSING — migration e5a6b7c8d9f0 not applied"
print("schema: trades.leverage present (%s)" % cols["leverage"]["type"])
print("schema: status present (%s), tp_order_ids (%s)"
      % (cols["status"]["type"], cols["tp_order_ids"]["type"]))

# 2. the write path — inside a transaction that is always rolled back
with engine.connect() as conn:
    tx = conn.begin()
    try:
        s = Session(bind=conn)
        probe_id = "LEDGER_PROBE_ROLLBACK_ONLY"
        s.add(Trade(
            trade_id=probe_id,
            user_id="00000000-0000-0000-0000-000000000000",
            symbol="BTCUSDT", direction="LONG", strategy_type="DAY_TRADE",
            entry_price=100.0, entry_time=datetime.now(timezone.utc).replace(tzinfo=None),
            position_size=0.5, stop_loss=95.0,
            take_profit_levels=[103.0, 106.0],
            tp_order_ids=[{"order_id": "PT_x_0002", "price": 103.0, "size": 0.6}],
            entry_order_id="PT_x_0001", sl_order_id="PT_x_0003",
            risk_amount=2.5, leverage=7.0, status="OPEN",
        ))
        s.flush()

        row = s.query(Trade).filter_by(trade_id=probe_id).one()
        assert row.leverage == 7.0, row.leverage
        assert row.status == "OPEN", row.status
        assert row.tp_order_ids[0]["size"] == 0.6, row.tp_order_ids
        assert row.entry_order_id == "PT_x_0001"
        print("write path: insert + readback OK (leverage=%s, status=%s, sized TP legs OK)"
              % (row.leverage, row.status))

        # 3. the exit transition writes CLOSED (what update_trade_exit now does)
        row.exit_price, row.exit_time = 103.0, datetime.now(timezone.utc).replace(tzinfo=None)
        row.exit_reason, row.status = "TP_HIT", "CLOSED"
        s.flush()
        assert s.query(Trade).filter_by(trade_id=probe_id).one().status == "CLOSED"
        print("exit path: status flips to CLOSED OK")
        s.close()
    finally:
        tx.rollback()
        print("rolled back — no production rows written")

# 4. what the live journal actually holds right now
with engine.connect() as conn:
    total = conn.execute(sa.text("select count(*) from trades")).scalar()
    open_rows = conn.execute(
        sa.text("select count(*) from trades where exit_time is null")).scalar()
    mislabelled = conn.execute(sa.text(
        "select count(*) from trades where exit_time is not null and status <> 'CLOSED'"
    )).scalar()
print("live journal: %d row(s), %d open, %d closed-but-mislabelled (backfill target: 0)"
      % (total, open_rows, mislabelled))
'''


def main() -> int:
    code, envs = ro._req("GET", f"/services/{ro.BACKEND}/env-vars?limit=60")
    if code != 200:
        print(f"Render env fetch failed: HTTP {code}")
        return 1
    url = next(e["envVar"]["value"] for e in envs if e["envVar"]["key"] == "POSTGRES_URL")

    r = subprocess.run([VENV_PY, "-c", PROBE], cwd=BACKEND_DIR, text=True,
                       capture_output=True, env={**os.environ, "PGURL": url})
    print(r.stdout.strip() or "(no output)")
    if r.returncode != 0:
        print("FAILED:\n" + r.stderr.strip()[-1500:])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
