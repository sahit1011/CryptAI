"""add trades.leverage + backfill trades.status

R2.1 rehydration prerequisites (see the four laws — honesty + money):

1. `leverage` — the leverage a position was opened at was persisted NOWHERE; two
   API read paths fabricated `10` for every row. Nullable Float: legacy rows stay
   NULL ("not recorded"), which readers must surface as unknown rather than invent.
   Float (not Integer) matches the table's existing numeric convention; the
   workspace integer-minor-units rule conflict is already documented in the M0
   findings ("money precision debt") and is fixed table-wide, not per column.

2. `status` backfill — the column has existed since the baseline with
   default='OPEN' but NOTHING ever wrote it on exit, so every closed row still
   reads OPEN and the indexed idx_status_strategy lies. update_trade_exit now
   writes CLOSED going forward; this one-time UPDATE makes historical rows
   truthful so `status` can eventually be trusted. Rehydration itself still keys
   on `exit_time IS NULL` (robust either way).

Idempotent: column add is inspected first; the backfill only touches rows that
are provably closed (exit_time set) and still marked OPEN.

Revision ID: e5a6b7c8d9f0
Revises: d4f5a6b7c8e9
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e5a6b7c8d9f0"
down_revision = "d4f5a6b7c8e9"
branch_labels = None
depends_on = None

COLUMN = "leverage"


def _has_column() -> bool:
    return COLUMN in {c["name"] for c in inspect(op.get_bind()).get_columns("trades")}


def upgrade() -> None:
    if not _has_column():
        op.add_column("trades", sa.Column(COLUMN, sa.Float(), nullable=True))
    op.execute(
        "UPDATE trades SET status = 'CLOSED' "
        "WHERE exit_time IS NOT NULL AND (status IS NULL OR status = 'OPEN')"
    )


def downgrade() -> None:
    # The status backfill is a truth repair, not schema — deliberately not reverted.
    if _has_column():
        with op.batch_alter_table("trades") as batch:
            batch.drop_column(COLUMN)
