#!/usr/bin/env python3
"""One-shot prod fix (2026-08-25): create the missing pulse_snapshots table.

Production's other new tables (sessions, proposals, ...) were created by boot-time
create_all, but pulse_snapshots never was — the calibration writer (R1.5) has had
nothing to write into since the plane went live. The alembic ledger says
7f1a2c9d4e01 while every schema change through head d4f5a6b7c8e9 is already live
EXCEPT this one table, so a plain `alembic upgrade head` would fail on the first
CREATE TABLE sessions. The honest reconciliation:

  1. create ONLY pulse_snapshots from the live model (checkfirst — idempotent;
     tests/test_schema_migration_parity.py guarantees model == migration), then
  2. stamp alembic to head so future migrations apply cleanly.

Purely additive. No data touched, no secrets printed. POSTGRES_URL is fetched
from the Render API in-memory (key read from ~/.render/cli.yaml by render_ops).

Run from repo root:  python3 scripts/apply_pulse_snapshots.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import render_ops as ro  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "crypto-trading-agent")
VENV_PY = os.path.join(BACKEND_DIR, ".venv", "bin", "python")
VENV_ALEMBIC = os.path.join(BACKEND_DIR, ".venv", "bin", "alembic")

DDL_SNIPPET = """
import os
import sqlalchemy as sa
from src.data.data_models import PulseSnapshot
eng = sa.create_engine(os.environ["PGURL"])
PulseSnapshot.__table__.create(eng, checkfirst=True)
with eng.connect() as c:
    n = c.execute(sa.text("select count(*) from pulse_snapshots")).scalar()
    print("pulse_snapshots exists, rows:", n)
"""


def main() -> int:
    code, envs = ro._req("GET", f"/services/{ro.BACKEND}/env-vars?limit=60")
    if code != 200:
        print(f"Render env fetch failed: HTTP {code}")
        return 1
    url = next(e["envVar"]["value"] for e in envs if e["envVar"]["key"] == "POSTGRES_URL")

    env = {**os.environ, "PGURL": url, "POSTGRES_URL": url}
    r = subprocess.run([VENV_PY, "-c", DDL_SNIPPET], env=env, cwd=BACKEND_DIR,
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-500:])
    if r.returncode != 0:
        return r.returncode

    r2 = subprocess.run([VENV_ALEMBIC, "stamp", "head"], env=env, cwd=BACKEND_DIR,
                        capture_output=True, text=True)
    print((r2.stdout + r2.stderr).strip().splitlines()[-1])
    return r2.returncode


if __name__ == "__main__":
    sys.exit(main())
