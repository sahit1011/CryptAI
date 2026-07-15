"""Idempotent schema bootstrap for the trading DB — run once before the app services.

This is what the docker-compose `migrate` service runs. It creates the schema from the
LIVE SQLAlchemy models (create_all, checkfirst), which is the codebase's actual source
of truth: the managers already call create_all on init. The old `alembic upgrade head`
had drifted from the models (its single migration predates `trades.user_id` and the
`exchange_credentials` table), so a fresh DB came up with a schema the app couldn't use.

Reads POSTGRES_URL from the environment (same var the app uses). Safe to re-run:
create_all only creates missing tables, so it's a no-op against an already-provisioned
DB (e.g. the Supabase project, whose schema is already in place).
"""
import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine

# Importing these registers EVERY ORM model on the shared Base.metadata: trades,
# exchange_credentials, agent_states, market_data, performance_metrics, system_logs, …
import src.data.data_models  # noqa: F401  (registers Trade, ExchangeCredential, AgentState, …)
import src.security.credential_vault  # noqa: F401
from src.data.data_models import Base


def main() -> int:
    url = os.getenv("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL is not set — cannot bootstrap schema", file=sys.stderr)
        return 1
    safe = url.split("@")[-1] if "@" in url else url
    print(f"Bootstrapping schema on {safe} …")

    # Create the WHOLE schema from the live models (checkfirst=True → idempotent, a
    # no-op against an already-provisioned DB like the Supabase project). This is the
    # codebase's real source of truth (the app calls create_all on init); it covers
    # agent_states + everything the agents/state-manager write to, not just trades.
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    tables = sorted(Base.metadata.tables.keys())
    print(f"Schema bootstrap complete ({len(tables)} tables): {', '.join(tables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
