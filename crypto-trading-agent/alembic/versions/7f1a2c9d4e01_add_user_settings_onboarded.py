"""add user_settings.onboarded

First-run onboarding flag: drives the post-login redirect to /onboarding. Existing
users are backfilled as onboarded=true (they've already been using the dashboard);
only NEW signups go through the wizard.

Revision ID: 7f1a2c9d4e01
Revises: 2bd363131001
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op

revision = "7f1a2c9d4e01"
down_revision = "2bd363131001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Existing rows predate onboarding — treat them as already onboarded.
    op.execute("UPDATE user_settings SET onboarded = TRUE")


def downgrade() -> None:
    op.drop_column("user_settings", "onboarded")
