"""add sessions.last_cycle_at

Heartbeat timestamp for a scanning session. NULL means no cycle has reported yet, which
the UI treats differently from "reported a while ago": a session that merely exists is
not evidence the agents are working.

Additive and nullable, so it is safe to apply ahead of the code that writes it — existing
rows read as "never reported", which is the honest answer for sessions that predate the
column.

Revision ID: c3e4f5a6b7d8
Revises: b2d3e4f5a6c7
Create Date: 2026-08-02
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e4f5a6b7d8"
down_revision = "b2d3e4f5a6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_cycle_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "last_cycle_at")
