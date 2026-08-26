"""add pulse_snapshots.venue

The signal engine now falls back from Binance to Bybit when a shared-IP 418 ban
blocks the primary venue (see signal-engine/src/venue.rs — measured 2026-08-25, a
ban cost 1h42m of signal plane). Two venues can therefore source the scores in this
table, and every calibration conclusion drawn from it would otherwise pool them as
if they were one instrument.

Nullable on purpose: rows written before the fallback existed came from Binance, but
recording NULL says "unlabelled" rather than asserting a provenance nobody verified.
Indexed because the first question of any calibration query becomes "which venue?".

Revision ID: f6b7c8d9e0a1
Revises: e5a6b7c8d9f0
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "f6b7c8d9e0a1"
down_revision = "e5a6b7c8d9f0"
branch_labels = None
depends_on = None

COLUMN = "venue"


def _has_column() -> bool:
    return COLUMN in {c["name"] for c in inspect(op.get_bind()).get_columns("pulse_snapshots")}


def upgrade() -> None:
    if not _has_column():
        op.add_column("pulse_snapshots", sa.Column(COLUMN, sa.String(length=20), nullable=True))
        op.create_index("ix_pulse_snapshots_venue", "pulse_snapshots", [COLUMN])


def downgrade() -> None:
    if _has_column():
        op.drop_index("ix_pulse_snapshots_venue", table_name="pulse_snapshots")
        with op.batch_alter_table("pulse_snapshots") as batch:
            batch.drop_column(COLUMN)
