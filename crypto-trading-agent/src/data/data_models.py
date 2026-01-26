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
    """Trade records table"""
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(50), unique=True, nullable=False, index=True)

    # Trade details
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG/SHORT
    strategy_type = Column(String(20))  # SCALP/DAY_TRADE/SWING

    # Entry
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, index=True)
    position_size = Column(Float, nullable=False)

    # Exit
    exit_price = Column(Float)
    exit_time = Column(DateTime)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(JSON)  # List of TP levels

    # Performance
    pnl = Column(Float)
    pnl_percentage = Column(Float)
    r_multiple = Column(Float)  # Risk-reward multiple achieved
    duration_minutes = Column(Integer)

    # Status
    status = Column(String(20), default='OPEN')  # OPEN/CLOSED/CANCELLED
    exit_reason = Column(String(50))  # TP_HIT/SL_HIT/MANUAL/INVALIDATED

    # Analysis context
    analysis_snapshot = Column(JSON)  # Full analysis at trade time
    confluences = Column(JSON)  # List of confluences
    confidence_score = Column(Float)

    # Orders
    entry_order_id = Column(String(50))
    sl_order_id = Column(String(50))
    tp_order_ids = Column(JSON)

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