"""session / preference / proposal layer

Implements the tenancy split decided 2026-08-02 (see docs/MULTI_TENANCY.md):

  PER-USER plane : user_preferences, sessions, session_events, proposals
  SHARED plane   : pulse_snapshots

pulse_snapshots has NO user_id by design — it is market truth, identical for every
tenant, and exists so the tradability score is falsifiable against forward returns.

Purely additive: five new tables, no existing table is touched, so this is safe to
apply to the live database ahead of the code that uses it.

Revision ID: 9c4e7a1b2d03
Revises: 7f1a2c9d4e01
Create Date: 2026-08-02
"""
import sqlalchemy as sa
from alembic import op

revision = "9c4e7a1b2d03"
down_revision = "7f1a2c9d4e01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------- user_preferences ----------------
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("trading_capital", sa.Float(), nullable=False, server_default="10000.0"),
        sa.Column("capital_currency", sa.String(8), nullable=False, server_default="USDT"),
        sa.Column("risk_appetite", sa.String(20), nullable=False, server_default="moderate"),
        sa.Column("max_risk_per_trade_pct", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("max_concurrent_positions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_daily_trades", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_leverage", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("monthly_pnl_target_pct", sa.Float()),
        sa.Column("goal_horizon", sa.String(20), server_default="swing"),
        sa.Column("goal_notes", sa.String(500)),
        sa.Column("symbol_universe", sa.JSON()),
        sa.Column("allowed_strategies", sa.JSON()),
        sa.Column("min_risk_reward", sa.Float(), nullable=False, server_default="1.5"),
        sa.Column("min_confidence", sa.Float(), nullable=False, server_default="0.6"),
        sa.Column("avoid_high_funding", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)

    # ---------------- sessions ----------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="scanning"),
        sa.Column("quota_seconds_granted", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("metered_seconds_accrued", sa.Integer(), nullable=False, server_default="0"),
        # NULL except while actively metering. Never store a countdown.
        sa.Column("clock_started_at", sa.DateTime()),
        sa.Column("llm_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_cost_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_cost_cap_micros", sa.Integer(), nullable=False, server_default="500000"),
        sa.Column("trading_day", sa.DateTime(), nullable=False),
        sa.Column("cycles_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime()),
        sa.Column("end_reason", sa.String(40)),
    )
    op.create_index("ix_sessions_session_id", "sessions", ["session_id"], unique=True)
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])
    op.create_index("ix_sessions_trading_day", "sessions", ["trading_day"])
    op.create_index("idx_session_user_day", "sessions", ["user_id", "trading_day"])
    op.create_index("idx_session_user_status", "sessions", ["user_id", "status"])

    # ---------------- session_events ----------------
    op.create_table(
        "session_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24)),
        sa.Column("agent", sa.String(40)),
        sa.Column("message", sa.String(1000)),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_session_events_session_id", "session_events", ["session_id"])
    op.create_index("ix_session_events_user_id", "session_events", ["user_id"])
    op.create_index("ix_session_events_created_at", "session_events", ["created_at"])
    op.create_index(
        "idx_session_event_session_time", "session_events", ["session_id", "created_at"]
    )

    # ---------------- proposals ----------------
    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.String(50), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit_levels", sa.JSON()),
        sa.Column("position_size", sa.Float()),
        sa.Column("risk_amount", sa.Float()),
        sa.Column("risk_currency", sa.String(8), nullable=False, server_default="USDT"),
        sa.Column("risk_reward_ratio", sa.Float()),
        sa.Column("leverage", sa.Float()),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("thesis", sa.String(4000)),
        sa.Column("strategy_type", sa.String(30)),
        sa.Column("pulse_ts", sa.DateTime()),
        sa.Column("market_regime", sa.String(30)),
        sa.Column("tradability_score", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("invalidation_price", sa.Float()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime()),
        sa.Column("trade_id", sa.String(50)),
    )
    op.create_index("ix_proposals_proposal_id", "proposals", ["proposal_id"], unique=True)
    op.create_index("ix_proposals_user_id", "proposals", ["user_id"])
    op.create_index("ix_proposals_session_id", "proposals", ["session_id"])
    op.create_index("ix_proposals_status", "proposals", ["status"])
    op.create_index("ix_proposals_expires_at", "proposals", ["expires_at"])
    op.create_index("ix_proposals_created_at", "proposals", ["created_at"])
    op.create_index("ix_proposals_trade_id", "proposals", ["trade_id"])
    op.create_index("idx_proposal_user_status", "proposals", ["user_id", "status"])

    # ---------------- pulse_snapshots (SHARED — no user_id) ----------------
    op.create_table(
        "pulse_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("pulse_ts", sa.DateTime(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("regime", sa.String(30), nullable=False),
        sa.Column("tradability", sa.Integer(), nullable=False),
        sa.Column("vetoes", sa.JSON()),
        sa.Column("factors", sa.JSON()),
        sa.Column("context", sa.JSON()),
        sa.Column("reference_price", sa.Float(), nullable=False),
        sa.Column("fwd_return_15m", sa.Float()),
        sa.Column("fwd_return_1h", sa.Float()),
        sa.Column("fwd_return_4h", sa.Float()),
        sa.Column("max_favorable_1h", sa.Float()),
        sa.Column("max_adverse_1h", sa.Float()),
        sa.Column("evaluated_at", sa.DateTime()),
    )
    op.create_index("ix_pulse_snapshots_symbol", "pulse_snapshots", ["symbol"])
    op.create_index("ix_pulse_snapshots_pulse_ts", "pulse_snapshots", ["pulse_ts"])
    op.create_index("ix_pulse_snapshots_tradability", "pulse_snapshots", ["tradability"])
    op.create_index("idx_pulse_symbol_ts", "pulse_snapshots", ["symbol", "pulse_ts"])
    op.create_index("idx_pulse_score_ts", "pulse_snapshots", ["tradability", "pulse_ts"])


def downgrade() -> None:
    # Reverse creation order. Indexes drop with their tables.
    op.drop_table("pulse_snapshots")
    op.drop_table("proposals")
    op.drop_table("session_events")
    op.drop_table("sessions")
    op.drop_table("user_preferences")
