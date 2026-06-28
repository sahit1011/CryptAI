#!/usr/bin/env python3
"""
Initialize the trading-system database.

This is now a thin wrapper around Alembic, which owns the schema. It no longer
contains any divergent raw-SQL DDL. The authoritative schema lives in
``src.data.data_models`` (the single SQLAlchemy MetaData source of truth) and is
applied by the Alembic migrations under ``alembic/versions``.

Primary path:   ``alembic upgrade head`` (creates/updates all tables + stamps the
                schema version so future migrations apply cleanly).
Fallback path:  if Alembic is unavailable, create all tables directly from the
                single-source metadata (``Base.metadata.create_all``). This does
                NOT record a migration version, so prefer the Alembic path.
"""

import sys
import subprocess
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.panel import Panel

try:
    from loguru import logger
except Exception:  # pragma: no cover - loguru should be present in deployment
    import logging

    logger = logging.getLogger("init_database")

console = Console()


def _resolve_database_url() -> str:
    """Resolve the database URL from the application config (single source)."""
    from src.utils.config import get_config

    return get_config().database.postgres_url


def upgrade_with_alembic() -> bool:
    """Apply the schema by running ``alembic upgrade head``.

    Returns True on success, False if Alembic could not be invoked. Any migration
    failure (non-zero exit) is raised so the operator sees it.
    """
    alembic_ini = PROJECT_ROOT / "alembic.ini"
    if not alembic_ini.exists():
        console.print("[yellow]alembic.ini not found - cannot use Alembic path[/yellow]")
        return False

    console.print("\n[bold]Applying schema via Alembic (upgrade head)...[/bold]")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        console.print("[yellow]Alembic is not installed - falling back[/yellow]")
        return False

    if result.stdout:
        console.print(result.stdout.strip())
    if result.returncode != 0:
        console.print("[bold red]Alembic upgrade failed:[/bold red]")
        console.print(result.stderr.strip())
        raise RuntimeError(f"alembic upgrade head exited {result.returncode}")

    console.print("[bold green]Alembic migrations applied (schema at head).[/bold green]")
    return True


def create_all_from_metadata() -> None:
    """Fallback: create all tables directly from the single-source metadata.

    Uses ``src.data.data_models.Base`` (importing trade_history_manager so the
    runtime ORM mapping is registered on the same metadata).
    """
    from sqlalchemy import create_engine

    from src.data.data_models import Base
    import src.memory.trade_history_manager  # noqa: F401  (registers TradeRecord)

    database_url = _resolve_database_url()
    console.print("\n[bold]Creating tables from SQLAlchemy metadata (fallback)...[/bold]")
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    console.print(f"[bold green]Tables ensured:[/bold green] {table_names}")


def init_database() -> None:
    """Initialize the database, preferring Alembic and falling back to metadata."""
    console.print(
        Panel.fit(
            "[bold cyan]Initializing Trading Database[/bold cyan]\n"
            "Schema source of truth: src.data.data_models (Alembic-managed)"
        )
    )

    try:
        if upgrade_with_alembic():
            return
        # Alembic unavailable -> fall back to direct metadata creation.
        create_all_from_metadata()
    except Exception as e:
        console.print("\n[bold red]Error initializing database:[/bold red]")
        console.print(f"  {e}")
        logger.error(f"Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    init_database()
