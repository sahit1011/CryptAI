"""add sessions.channel

Per-session trading style (scalp | intraday | swing | position) chosen at start, which
overrides the persistent goal_horizon persona for that session's synthesis. Nullable —
existing sessions have no channel and fall back to the user's default, so no backfill.

Revision ID: b2d3e4f5a6c7
Revises: 9c4e7a1b2d03
Create Date: 2026-08-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "b2d3e4f5a6c7"
down_revision = "9c4e7a1b2d03"
branch_labels = None
depends_on = None


def _has_channel() -> bool:
    return "channel" in {
        c["name"] for c in inspect(op.get_bind()).get_columns("sessions")
    }


def upgrade() -> None:
    # Idempotent: the app's SessionManager._ensure_schema self-heals this column WITHOUT
    # bumping alembic_version, so a DB stamped at the prior revision can already have it.
    # Re-adding would raise duplicate-column and fail the whole migrate step.
    if not _has_channel():
        op.add_column("sessions", sa.Column("channel", sa.String(length=16), nullable=True))


def downgrade() -> None:
    # batch_alter_table so the drop is portable to SQLite (which rebuilds the table),
    # not only Postgres. Guarded so a re-run or a self-heal-only DB does not error.
    if _has_channel():
        with op.batch_alter_table("sessions") as batch:
            batch.drop_column("channel")
