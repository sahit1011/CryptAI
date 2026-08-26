"""add sessions.seconds_refunded

Metered seconds handed back after the fact — currently only when analysis capacity died
mid-scan. Already deducted from metered_seconds_accrued; this column is the audit trail
so a receipt can explain why the balance moved.

NOT NULL DEFAULT 0 rather than nullable: every reader treats it as an int, and a NULL
would surface on an old session's receipt as a refund of "unknown".

Idempotent in both directions, matching SessionManager._ensure_schema, which adds the
same column without bumping alembic_version — on Render there is no migrate step, so the
self-heal is what actually creates it in production and this migration must be able to
run afterwards without hitting duplicate-column.

Revision ID: d4f5a6b7c8e9
Revises: c3e4f5a6b7d8
Create Date: 2026-08-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "d4f5a6b7c8e9"
down_revision = "c3e4f5a6b7d8"
branch_labels = None
depends_on = None

COLUMN = "seconds_refunded"


def _has_column() -> bool:
    return COLUMN in {c["name"] for c in inspect(op.get_bind()).get_columns("sessions")}


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            "sessions",
            sa.Column(COLUMN, sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    # batch_alter_table so the drop is portable to SQLite, which rebuilds the table.
    if _has_column():
        with op.batch_alter_table("sessions") as batch:
            batch.drop_column(COLUMN)
