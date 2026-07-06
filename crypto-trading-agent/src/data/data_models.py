"""
Database models for trading system
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

Base = declarative_base()

class Trade(Base):
    """Canonical trade records table (single source of truth for the ``trades`` table).

    NOTE: This model and ``src.memory.trade_history_manager.TradeRecord`` map to the
    SAME physical ``trades`` table. Historically two divergent definitions existed
    (the async ORM path in ``state_manager`` used this model; the sync runtime path
    used ``TradeRecord``), and runtime code reads/writes columns from BOTH sets
    (e.g. ``state_manager`` reads ``is_winner``; ``TradeRecord`` writes
    ``take_profit_levels``/``risk_amount``). The table must therefore be the UNION
    of both column sets. This model now holds that union and is the authoritative
    definition Alembic autogenerates from. ``TradeRecord`` binds to this same
    ``Base.metadata`` with ``extend_existing`` so only one ``Table('trades')`` exists.
    All added columns are nullable/additive to stay backward compatible.
    """
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), unique=True, nullable=False, index=True)

    # Multi-tenancy: the Supabase auth user (auth.users.id UUID) that owns this trade.
    # Nullable for backward compatibility with single-tenant/legacy rows; queries scope
    # by this when a user context is supplied. Enforcement (RLS / per-user isolation) is
    # layered on top — see docs/MULTI_TENANCY.md.
    user_id = Column(String(64), index=True, nullable=True)

    # Trade details
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG/SHORT
    strategy_type = Column(String(20), index=True)  # SCALP/DAY_TRADE/SWING

    # Entry
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, index=True)
    position_size = Column(Float, nullable=False)

    # Exit
    exit_price = Column(Float)
    exit_time = Column(DateTime, index=True)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(JSON)  # List of TP levels (async ORM path)
    take_profit_levels = Column(JSON)  # List of TP levels (runtime TradeRecord path)

    # Risk management (runtime TradeRecord path)
    risk_amount = Column(Float)

    # Performance
    pnl = Column(Float)
    pnl_percentage = Column(Float)
    r_multiple = Column(Float)  # Risk-reward multiple achieved (async ORM path)
    risk_reward_ratio = Column(Float)  # Realized RR (runtime TradeRecord path)
    duration_minutes = Column(Float)

    # Status
    status = Column(String(20), default='OPEN')  # OPEN/CLOSED/CANCELLED
    exit_reason = Column(String(50))  # TP_HIT/SL_HIT/MANUAL/INVALIDATED

    # Setup quality
    confidence_score = Column(Float)
    confluence_count = Column(Integer, default=0)

    # Market conditions (runtime TradeRecord path)
    market_regime = Column(String(50))  # trending/ranging/volatile
    atr_at_entry = Column(Float)
    volatility_percentile = Column(Float)

    # Analysis context
    analysis_snapshot = Column(JSON)  # Full analysis at trade time
    confluences = Column(JSON)  # List of confluences
    smc_patterns = Column(JSON)  # SMC patterns present (runtime TradeRecord path)
    ict_setups = Column(JSON)  # ICT setups (runtime TradeRecord path)

    # Outcome flags
    is_winner = Column(Boolean)

    # Orders
    entry_order_id = Column(String(50))
    sl_order_id = Column(String(50))
    tp_order_ids = Column(JSON)

    # Notes / lessons learned
    notes = Column(String(500))

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    executions = relationship("TradeExecution", back_populates="trade")

    __table_args__ = (
        Index('idx_symbol_entry_time', 'symbol', 'entry_time'),
        Index('idx_status_strategy', 'status', 'strategy_type'),
    )

class TradeExecution(Base):
    """Order execution records"""
    __tablename__ = 'trade_executions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), ForeignKey('trades.trade_id'), nullable=False)

    order_id = Column(String(50), unique=True, nullable=False)
    order_type = Column(String(20))  # ENTRY/SL/TP1/TP2/TP3
    side = Column(String(10))  # BUY/SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)

    status = Column(String(20))  # PENDING/FILLED/CANCELLED
    filled_quantity = Column(Float, default=0)
    average_price = Column(Float)

    execution_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    trade = relationship("Trade", back_populates="executions")

class MarketData(Base):
    """Historical market data cache"""
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)  # 5m/15m/1h/4h/1d

    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    # Technical indicators (cached)
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    bb_upper = Column(Float)
    bb_lower = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_symbol_timeframe_timestamp', 'symbol', 'timeframe', 'timestamp', unique=True),
    )

class PerformanceMetrics(Base):
    """Aggregated performance metrics"""
    __tablename__ = 'performance_metrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)

    # Daily metrics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)

    # P&L
    daily_pnl = Column(Float, default=0)
    cumulative_pnl = Column(Float, default=0)

    # Risk metrics
    max_drawdown = Column(Float, default=0)
    sharpe_ratio = Column(Float)
    profit_factor = Column(Float)

    # Strategy breakdown
    scalp_trades = Column(Integer, default=0)
    day_trades = Column(Integer, default=0)
    swing_trades = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

class AgentState(Base):
    """Agent state persistence"""
    __tablename__ = 'agent_states'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), unique=True, nullable=False)

    state = Column(String(20))  # IDLE/PROCESSING/ERROR
    last_heartbeat = Column(DateTime)

    # State data
    state_data = Column(JSON)  # Agent-specific state

    # Error tracking
    error_count = Column(Integer, default=0)
    last_error = Column(String(500))
    last_error_time = Column(DateTime)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemLog(Base):
    """System-wide logging"""
    __tablename__ = 'system_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    level = Column(String(10), nullable=False)  # INFO/WARNING/ERROR/CRITICAL
    agent = Column(String(50))
    message = Column(String(1000))
    context = Column(JSON)

    __table_args__ = (
        Index('idx_timestamp_level', 'timestamp', 'level'),
    )

# Pydantic models for API/validation
class TradeSetup(BaseModel):
    """Trade setup schema"""
    symbol: str
    direction: str  # LONG/SHORT
    strategy_type: str
    entry_price: float
    stop_loss: float
    take_profit: List[float]
    position_size: Optional[float] = None
    confidence: float
    risk_reward: float
    reasoning: dict

class MarketAnalysis(BaseModel):
    """Market analysis result schema"""
    timestamp: datetime
    symbol: str
    market_structure: dict
    key_levels: dict
    smc_confluences: List[dict]
    ict_setup: dict
    trade_opportunities: List[dict]
    reasoning: str

class RiskParameters(BaseModel):
    """Risk management parameters"""
    account_balance: float
    max_risk_per_trade: float = 0.02
    max_portfolio_heat: float = 0.06
    max_daily_loss: float = 0.05
    max_concurrent_positions: int = 3
    min_risk_reward: float = 2.0