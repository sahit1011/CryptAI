"""Initial database schema

Revision ID: 1330a79ae792
Revises:
Create Date: 2025-11-06 22:25:34.120411

Creates the full authoritative schema derived from ``src.data.data_models.Base``
(the single source of truth). The ``trades`` table is the unified union of the
historical async-ORM (``data_models.Trade``) and sync-runtime
(``trade_history_manager.TradeRecord``) definitions, which both map to this one
physical table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1330a79ae792'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### canonical schema from src.data.data_models.Base ###

    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(length=50), nullable=False),
        # Trade details
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('strategy_type', sa.String(length=20), nullable=True),
        # Entry
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('entry_time', sa.DateTime(), nullable=False),
        sa.Column('position_size', sa.Float(), nullable=False),
        # Exit
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_time', sa.DateTime(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=False),
        sa.Column('take_profit', sa.JSON(), nullable=True),
        sa.Column('take_profit_levels', sa.JSON(), nullable=True),
        # Risk management
        sa.Column('risk_amount', sa.Float(), nullable=True),
        # Performance
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('pnl_percentage', sa.Float(), nullable=True),
        sa.Column('r_multiple', sa.Float(), nullable=True),
        sa.Column('risk_reward_ratio', sa.Float(), nullable=True),
        sa.Column('duration_minutes', sa.Float(), nullable=True),
        # Status
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('exit_reason', sa.String(length=50), nullable=True),
        # Setup quality
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('confluence_count', sa.Integer(), nullable=True),
        # Market conditions
        sa.Column('market_regime', sa.String(length=50), nullable=True),
        sa.Column('atr_at_entry', sa.Float(), nullable=True),
        sa.Column('volatility_percentile', sa.Float(), nullable=True),
        # Analysis context
        sa.Column('analysis_snapshot', sa.JSON(), nullable=True),
        sa.Column('confluences', sa.JSON(), nullable=True),
        sa.Column('smc_patterns', sa.JSON(), nullable=True),
        sa.Column('ict_setups', sa.JSON(), nullable=True),
        # Outcome flags
        sa.Column('is_winner', sa.Boolean(), nullable=True),
        # Orders
        sa.Column('entry_order_id', sa.String(length=50), nullable=True),
        sa.Column('sl_order_id', sa.String(length=50), nullable=True),
        sa.Column('tp_order_ids', sa.JSON(), nullable=True),
        # Notes
        sa.Column('notes', sa.String(length=500), nullable=True),
        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_id'),
    )
    op.create_index(op.f('ix_trades_trade_id'), 'trades', ['trade_id'], unique=True)
    op.create_index(op.f('ix_trades_symbol'), 'trades', ['symbol'], unique=False)
    op.create_index(op.f('ix_trades_strategy_type'), 'trades', ['strategy_type'], unique=False)
    op.create_index(op.f('ix_trades_entry_time'), 'trades', ['entry_time'], unique=False)
    op.create_index(op.f('ix_trades_exit_time'), 'trades', ['exit_time'], unique=False)
    op.create_index('idx_symbol_entry_time', 'trades', ['symbol', 'entry_time'], unique=False)
    op.create_index('idx_status_strategy', 'trades', ['status', 'strategy_type'], unique=False)

    op.create_table(
        'trade_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(length=50), nullable=False),
        sa.Column('order_id', sa.String(length=50), nullable=False),
        sa.Column('order_type', sa.String(length=20), nullable=True),
        sa.Column('side', sa.String(length=10), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('filled_quantity', sa.Float(), nullable=True),
        sa.Column('average_price', sa.Float(), nullable=True),
        sa.Column('execution_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trade_id'], ['trades.trade_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
    )

    op.create_table(
        'market_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.Column('rsi', sa.Float(), nullable=True),
        sa.Column('macd', sa.Float(), nullable=True),
        sa.Column('macd_signal', sa.Float(), nullable=True),
        sa.Column('bb_upper', sa.Float(), nullable=True),
        sa.Column('bb_lower', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_data_symbol'), 'market_data', ['symbol'], unique=False)
    op.create_index(op.f('ix_market_data_timestamp'), 'market_data', ['timestamp'], unique=False)
    op.create_index(
        'idx_symbol_timeframe_timestamp',
        'market_data',
        ['symbol', 'timeframe', 'timestamp'],
        unique=True,
    )

    op.create_table(
        'performance_metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('winning_trades', sa.Integer(), nullable=True),
        sa.Column('losing_trades', sa.Integer(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('daily_pnl', sa.Float(), nullable=True),
        sa.Column('cumulative_pnl', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('profit_factor', sa.Float(), nullable=True),
        sa.Column('scalp_trades', sa.Integer(), nullable=True),
        sa.Column('day_trades', sa.Integer(), nullable=True),
        sa.Column('swing_trades', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date'),
    )
    op.create_index(op.f('ix_performance_metrics_date'), 'performance_metrics', ['date'], unique=True)

    op.create_table(
        'agent_states',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_name', sa.String(length=50), nullable=False),
        sa.Column('state', sa.String(length=20), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('state_data', sa.JSON(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('last_error_time', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_name'),
    )

    op.create_table(
        'system_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('level', sa.String(length=10), nullable=False),
        sa.Column('agent', sa.String(length=50), nullable=True),
        sa.Column('message', sa.String(length=1000), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_system_logs_timestamp'), 'system_logs', ['timestamp'], unique=False)
    op.create_index('idx_timestamp_level', 'system_logs', ['timestamp', 'level'], unique=False)

    # ### end commands ###


def downgrade() -> None:
    # ### reverse of upgrade(): drop in dependency-safe order ###
    op.drop_index('idx_timestamp_level', table_name='system_logs')
    op.drop_index(op.f('ix_system_logs_timestamp'), table_name='system_logs')
    op.drop_table('system_logs')

    op.drop_table('agent_states')

    op.drop_index(op.f('ix_performance_metrics_date'), table_name='performance_metrics')
    op.drop_table('performance_metrics')

    op.drop_index('idx_symbol_timeframe_timestamp', table_name='market_data')
    op.drop_index(op.f('ix_market_data_timestamp'), table_name='market_data')
    op.drop_index(op.f('ix_market_data_symbol'), table_name='market_data')
    op.drop_table('market_data')

    # trade_executions has a FK to trades; drop it before trades.
    op.drop_table('trade_executions')

    op.drop_index('idx_status_strategy', table_name='trades')
    op.drop_index('idx_symbol_entry_time', table_name='trades')
    op.drop_index(op.f('ix_trades_exit_time'), table_name='trades')
    op.drop_index(op.f('ix_trades_entry_time'), table_name='trades')
    op.drop_index(op.f('ix_trades_strategy_type'), table_name='trades')
    op.drop_index(op.f('ix_trades_symbol'), table_name='trades')
    op.drop_index(op.f('ix_trades_trade_id'), table_name='trades')
    op.drop_table('trades')
    # ### end commands ###
