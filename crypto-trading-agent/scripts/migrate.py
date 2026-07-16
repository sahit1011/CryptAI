"""Schema migrations — the docker-compose/deploy `migrate` step.

Runs Alembic properly (versioned, rollback-able) while adopting databases that were
provisioned by the old `create_all` bootstrap:

  1. `alembic_version` present            -> `alembic upgrade head` (normal path)
  2. tables exist but NO `alembic_version` -> `alembic stamp head` first (the schema was
     created by create_all and matches the baseline), then upgrade
  3. empty database                        -> `alembic upgrade head` builds everything

Rollback: `alembic downgrade -1` (see docs/OPERATIONS.md). Reads POSTGRES_URL from the
environment like the app does.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine, inspect  # noqa: E402


def main() -> int:
    url = os.getenv("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL is not set — cannot migrate", file=sys.stderr)
        return 1
    safe = url.split("@")[-1] if "@" in url else url
    print(f"Migrating schema on {safe} …")

    engine = create_engine(url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
    finally:
        engine.dispose()

    has_version = "alembic_version" in tables
    has_app_tables = bool(tables - {"alembic_version"})

    if not has_version and has_app_tables:
        # Adopt a create_all-provisioned DB: schema already matches the baseline.
        print("Existing schema without alembic_version — stamping baseline (adopt).")
        rc = subprocess.call(["alembic", "stamp", "head"])
        if rc != 0:
            return rc

    rc = subprocess.call(["alembic", "upgrade", "head"])
    if rc == 0:
        print("Migrations up to date.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
