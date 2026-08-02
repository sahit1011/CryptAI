"""ORM models and Alembic migrations must not drift apart.

The classic failure: someone adds a column to a model, forgets the migration, and it
works locally (because `create_all` builds from the models) but breaks in production
(which is built from migrations). This suite builds BOTH and diffs them.

Runs against SQLite in-memory, so it needs no Postgres and no Docker. That does mean
Postgres-specific DDL is not exercised here — this catches structural drift (missing
tables, missing columns, changed types), not dialect quirks.
"""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from src.data.data_models import Base

# Tables introduced by the session/preference/proposal layer (docs/MULTI_TENANCY.md).
SESSION_LAYER_TABLES = [
    "user_preferences",
    "sessions",
    "session_events",
    "proposals",
    "pulse_snapshots",
]

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# The session-layer migration whose downgrade is checked in isolation.
MIGRATION = VERSIONS_DIR / "9c4e7a1b2d03_session_preference_proposal_layer.py"


def _load_migration(path: Path = MIGRATION):
    spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ordered_migrations():
    """Every migration module, topologically ordered base → head by down_revision.

    Applying the FULL chain (not one hardcoded file) means a new migration is picked up
    automatically — the parity check can never silently ignore a later column addition.
    """
    mods = [
        _load_migration(p)
        for p in VERSIONS_DIR.glob("*.py")
        if p.name != "__init__.py"
    ]
    by_down = {getattr(m, "down_revision", None): m for m in mods}
    ordered = []
    cursor = None  # the base revision has down_revision = None
    while cursor in by_down:
        nxt = by_down[cursor]
        ordered.append(nxt)
        cursor = nxt.revision
    assert len(ordered) == len(mods), (
        f"migration chain is broken or branched: ordered {len(ordered)} of {len(mods)}"
    )
    return ordered


def _apply_chain(engine, migrations=None):
    migrations = migrations or _ordered_migrations()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for mig in migrations:
                mig.upgrade()
        conn.commit()


@pytest.fixture(scope="module")
def model_inspector():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return inspect(engine)


@pytest.fixture(scope="module")
def migration_engine():
    engine = create_engine("sqlite://")
    _apply_chain(engine)  # full base->head chain, so new migrations are included
    return engine


@pytest.mark.parametrize("table", SESSION_LAYER_TABLES)
def test_migration_matches_model(table, model_inspector, migration_engine):
    """Every column in the model exists in the migration, with the same type."""
    mig_inspector = inspect(migration_engine)

    assert table in model_inspector.get_table_names(), f"{table} missing from ORM models"
    assert table in mig_inspector.get_table_names(), f"{table} missing from the migration"

    model_cols = {c["name"]: str(c["type"]).upper() for c in model_inspector.get_columns(table)}
    mig_cols = {c["name"]: str(c["type"]).upper() for c in mig_inspector.get_columns(table)}

    assert set(model_cols) == set(mig_cols), (
        f"{table} column drift — "
        f"only in models: {sorted(set(model_cols) - set(mig_cols))}, "
        f"only in migration: {sorted(set(mig_cols) - set(model_cols))}"
    )

    mismatched = {
        name: (model_cols[name], mig_cols[name])
        for name in model_cols
        if model_cols[name] != mig_cols[name]
    }
    assert not mismatched, f"{table} type drift (model, migration): {mismatched}"


def test_downgrade_reverses_cleanly():
    """A migration that cannot be rolled back is not reversible in an incident."""
    engine = create_engine("sqlite://")
    mig = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.upgrade()
        conn.commit()
        assert set(SESSION_LAYER_TABLES).issubset(set(inspect(engine).get_table_names()))

        with Operations.context(ctx):
            mig.downgrade()
        conn.commit()

    left_behind = [t for t in SESSION_LAYER_TABLES if t in inspect(engine).get_table_names()]
    assert not left_behind, f"downgrade left tables behind: {left_behind}"


def test_full_chain_downgrades_cleanly():
    """Every migration in the chain must be reversible, not just the session layer —
    an incident may need to roll back the newest migration first."""
    engine = create_engine("sqlite://")
    chain = _ordered_migrations()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for mig in chain:
                mig.upgrade()
            for mig in reversed(chain):
                mig.downgrade()
        conn.commit()
    # Base is clean: the session-layer tables (created by the chain) are gone again.
    remaining = [t for t in SESSION_LAYER_TABLES if t in inspect(engine).get_table_names()]
    assert not remaining, f"downgrade left tables behind: {remaining}"


def test_pulse_snapshots_has_no_user_id(model_inspector):
    """Tenancy boundary, enforced in the schema.

    pulse_snapshots is SHARED-plane data — market truth, identical for every tenant.
    A user_id column appearing here means the shared/per-user split has been violated
    and per-user data is leaking into the shared plane. See docs/MULTI_TENANCY.md.
    """
    columns = {c["name"] for c in model_inspector.get_columns("pulse_snapshots")}
    assert "user_id" not in columns, (
        "pulse_snapshots gained a user_id — shared-plane boundary violated"
    )


@pytest.mark.parametrize("table", ["user_preferences", "sessions", "session_events", "proposals"])
def test_per_user_tables_are_scoped_and_indexed(table, model_inspector):
    """Every per-user table carries an indexed user_id.

    The backend connects as a privileged role that BYPASSES RLS, so application-layer
    scoping is the only guard against cross-user leakage. A per-user table without a
    user_id cannot be scoped at all.
    """
    columns = {c["name"] for c in model_inspector.get_columns(table)}
    assert "user_id" in columns, f"{table} is per-user but has no user_id to scope by"

    indexed = {col for idx in model_inspector.get_indexes(table) for col in idx["column_names"]}
    assert "user_id" in indexed, (
        f"{table}.user_id is not indexed — every read is scoped by it, so this is a "
        f"full scan on the hottest query path"
    )
