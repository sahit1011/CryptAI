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

revision = "b2d3e4f5a6c7"
down_revision = "9c4e7a1b2d03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("channel", sa.String(length=16), nullable=True))


def downgrade() -> None:
    # batch_alter_table so the drop is portable to SQLite (which rebuilds the table),
    # not only Postgres. No-op-safe if the column is already gone.
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("channel")
