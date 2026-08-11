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

class ExchangeCredential(Base):
    """Per-user exchange API credentials — encrypted at rest.

    Multi-tenancy: each user brings their own exchange (e.g. BingX testnet) keys. The
    key and secret are stored ONLY as Fernet ciphertext (see src.security.credential_vault);
    plaintext never touches the database. One active credential per (user_id, exchange).
    """
    __tablename__ = 'exchange_credentials'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)     # Supabase auth user UUID
    exchange = Column(String(20), nullable=False, default='bingx')
    label = Column(String(80))                                   # user-facing nickname
    api_key_enc = Column(String(512), nullable=False)            # Fernet ciphertext
    api_secret_enc = Column(String(1024), nullable=False)        # Fernet ciphertext
    is_testnet = Column(Boolean, default=True, nullable=False)   # testnet-only until live-gated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_exchange_cred_user', 'user_id', 'exchange', unique=True),
    )

class UserSettings(Base):
    """Per-user trading preferences (multi-tenant).

    trading_mode drives what the daemon does for this user each cycle:
      off    - ignore this user (no booking)
      paper  - book to their isolated paper engine (default; safe, no exchange needed)
      manual - surface suggestions only; the user places orders via /api/execute-setup
      auto   - the agents place orders on the user's connected exchange (testnet-gated)
    active_exchange selects which connected exchange to route real orders through.
    """
    __tablename__ = 'user_settings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, unique=True)  # Supabase UUID
    trading_mode = Column(String(10), nullable=False, default='paper')
    active_exchange = Column(String(20), nullable=False, default='bingx')
    # First-run onboarding completed? Drives the post-login redirect to /onboarding.
    onboarded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


# ---------------------------------------------------------------------------
# Session / preference / proposal layer  (see docs/MULTI_TENANCY.md)
#
# These five tables implement the tenancy split decided 2026-08-02:
#   user_preferences · sessions · session_events · proposals   -> PER-USER plane
#   pulse_snapshots                                            -> SHARED plane
#
# pulse_snapshots deliberately has NO user_id. That asymmetry is the tenancy
# boundary made visible in the schema: if a query against it filters by user,
# something has gone wrong architecturally.
#
# MONEY PRECISION DEBT: these tables use Float for prices and amounts to match
# the existing `trades` / `trade_executions` columns they join against. The
# workspace rule is integer minor units. Mixing Numeric here with Float there
# would create conversion bugs at the boundary, so the correct fix is one
# wholesale migration across ALL money columns, not a piecemeal start. Tracked,
# not forgotten. `currency` columns are added now since INR settlement on the
# Indian venues is additive and needed regardless.
# ---------------------------------------------------------------------------

class UserPreferences(Base):
    """A user's trading persona — what their agent team optimises for.

    Distinct from ``UserSettings``, which holds operational flags (mode, exchange,
    onboarded) read by the daemon every cycle. Preferences are the richer, faster-
    evolving set read once per SESSION to parameterise synthesis, sizing, and ranking.
    Keeping them apart means preference migrations never touch the hot settings table.
    Relationship is 1:1 with a user; absence means "use documented defaults".
    """
    __tablename__ = 'user_preferences'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, unique=True)  # Supabase UUID

    # Capital & risk appetite
    trading_capital = Column(Float, nullable=False, default=10000.0)
    capital_currency = Column(String(8), nullable=False, default='USDT')
    risk_appetite = Column(String(20), nullable=False, default='moderate')  # conservative/moderate/aggressive
    max_risk_per_trade_pct = Column(Float, nullable=False, default=1.0)     # percent of capital
    max_concurrent_positions = Column(Integer, nullable=False, default=1)
    max_daily_trades = Column(Integer, nullable=False, default=3)
    max_leverage = Column(Float, nullable=False, default=3.0)

    # Goals — these drive the Ranker, not the risk engine. The risk engine may only
    # ever SHRINK exposure; a stretch PnL target must never widen a limit above.
    monthly_pnl_target_pct = Column(Float)
    goal_horizon = Column(String(20), default='swing')      # scalp/intraday/swing/position
    goal_notes = Column(String(500))                        # free text, fed to the Ranker

    # Universe & strategy scope
    symbol_universe = Column(JSON)          # ["BTCUSDT", ...]; null => platform default
    allowed_strategies = Column(JSON)       # ["smc_ob", "fvg_fill", ...]; null => all
    min_risk_reward = Column(Float, nullable=False, default=1.5)
    min_confidence = Column(Float, nullable=False, default=0.6)
    avoid_high_funding = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Session(Base):
    """A metered analysis session — the unit the free-tier 30 min/day is spent from.

    DURABLE CLOCK: never store a countdown. Elapsed time is always derived as
    ``metered_seconds_accrued + (now - clock_started_at if clock_started_at else 0)``.
    ``clock_started_at`` is set while SCANNING and NULLED whenever the clock pauses, so a
    process restart mid-session loses at most the in-flight segment rather than the whole
    session, and can never silently grant unlimited time.

    The clock PAUSES at ``setup_proposed`` (decided 2026-08-02): a user is not charged for
    deliberating. It resumes only if they reject and ask for more scanning.

    MONITORING IS NEVER METERED. A session may end with quota exhausted while positions
    stay open and monitored — that is a money-safety property, not a billing loophole.
    """
    __tablename__ = 'sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)

    # State machine: idle | scanning | setup_proposed | awaiting_approval |
    #                executing | ended
    status = Column(String(24), nullable=False, default='scanning', index=True)

    # The trading style chosen for THIS session (scalp | intraday | swing | position),
    # overriding the persistent goal_horizon persona for synthesis. Nullable: a legacy or
    # unspecified session falls back to the user's default goal_horizon.
    channel = Column(String(16))

    # Durable metered clock
    quota_seconds_granted = Column(Integer, nullable=False, default=1800)  # free tier: 30 min
    metered_seconds_accrued = Column(Integer, nullable=False, default=0)
    clock_started_at = Column(DateTime)          # non-null ONLY while actively metering

    # Cost safety net — the minute quota is the product, this is the hard ceiling.
    llm_tokens_used = Column(Integer, nullable=False, default=0)
    llm_cost_micros = Column(Integer, nullable=False, default=0)   # micro-USD, integer
    llm_cost_cap_micros = Column(Integer, nullable=False, default=500_000)  # $0.50/session

    # Daily quota rollup. UTC date so the reset boundary is unambiguous; the UI renders
    # it in the user's local timezone.
    trading_day = Column(DateTime, nullable=False, index=True)

    cycles_completed = Column(Integer, nullable=False, default=0)
    # When a scan cycle last reported. NULL means nothing has reported yet this session,
    # which is different from "reported a while ago" — the UI must not claim the agents
    # are working on the strength of a session merely existing.
    last_cycle_at = Column(DateTime)

    # Metered seconds handed back after the fact — currently only when analysis capacity
    # died mid-scan and the user would otherwise have been charged for a dead engine.
    # Already deducted from metered_seconds_accrued; this is the audit trail, not a
    # second balance, so the receipt can say WHY the numbers moved.
    seconds_refunded = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime)
    end_reason = Column(String(40))   # quota_exhausted | user_ended | cost_cap | error | trade_opened

    __table_args__ = (
        Index('idx_session_user_day', 'user_id', 'trading_day'),
        Index('idx_session_user_status', 'user_id', 'status'),
    )


class SessionEvent(Base):
    """Append-only audit trail of session state transitions and agent activity.

    Doubles as the user-facing "agent feed" and as the forensic record for any dispute
    about why a trade was proposed or placed. Append-only: never UPDATE or DELETE a row.
    """
    __tablename__ = 'session_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)

    event_type = Column(String(40), nullable=False)   # state_change | agent_step | proposal | error
    from_status = Column(String(24))
    to_status = Column(String(24))
    agent = Column(String(40))                        # which agent emitted this
    message = Column(String(1000))
    payload = Column(JSON)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_session_event_session_time', 'session_id', 'created_at'),
    )


class Proposal(Base):
    """A trade setup surfaced to ONE user, with an explicit shelf life.

    Crypto moves: a setup proposed at price X is not the same trade at X±0.5%. Every
    proposal therefore carries ``expires_at`` AND ``invalidation_price``, and MUST be
    re-validated at approval time (re-check price, spread, and risk limits before the
    order is sent). Approving a stale proposal must refuse or re-size — never blind-fill.

    ``pulse_ts`` records which shared-plane pulse this was synthesised from, so any
    proposal can be traced back to the exact market facts that produced it.
    """
    __tablename__ = 'proposals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(50), nullable=False, index=True)

    symbol = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)          # LONG/SHORT
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit_levels = Column(JSON)                       # [{"price": .., "size": ..}]

    position_size = Column(Float)
    risk_amount = Column(Float)
    risk_currency = Column(String(8), nullable=False, default='USDT')
    risk_reward_ratio = Column(Float)
    leverage = Column(Float)

    # Why this trade, for this user
    confidence_score = Column(Float)
    thesis = Column(String(4000))                           # LLM narrative w/ invalidation
    strategy_type = Column(String(30))

    # Traceability back to the shared plane
    pulse_ts = Column(DateTime)
    market_regime = Column(String(30))
    tradability_score = Column(Integer)

    # Shelf life
    status = Column(String(20), nullable=False, default='proposed', index=True)
    # proposed | approved | rejected | expired | invalidated | executed | failed
    expires_at = Column(DateTime, nullable=False, index=True)
    invalidation_price = Column(Float)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    decided_at = Column(DateTime)
    trade_id = Column(String(50), index=True)               # set once executed

    __table_args__ = (
        Index('idx_proposal_user_status', 'user_id', 'status'),
    )


class PulseSnapshot(Base):
    """SHARED-PLANE calibration log — every tradability score the signal engine emits.

    NO user_id BY DESIGN. This is market truth, identical for every tenant.

    Purpose is falsifiability. Forward-return columns are backfilled by the calibration
    job so we can answer the only question that matters about a confidence score: do
    high-score windows actually produce better risk-adjusted forward returns than low-score
    ones? If they do not, the score is decoration and the weights must change. A scorer
    shipped without this table is a scorer nobody can check.
    """
    __tablename__ = 'pulse_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    pulse_ts = Column(DateTime, nullable=False, index=True)
    schema_version = Column(Integer, nullable=False, default=1)

    regime = Column(String(30), nullable=False)
    tradability = Column(Integer, nullable=False, index=True)
    vetoes = Column(JSON)          # [] when clean; non-empty forces tradability 0
    factors = Column(JSON)         # {trend_alignment: .., volatility_band: .., ...}
    context = Column(JSON)         # {atr_pct: .., funding_rate: .., spread_bps: .., ...}

    reference_price = Column(Float, nullable=False)   # price at pulse_ts, for fwd returns

    # Backfilled by the calibration job — null until the window has elapsed.
    fwd_return_15m = Column(Float)
    fwd_return_1h = Column(Float)
    fwd_return_4h = Column(Float)
    max_favorable_1h = Column(Float)    # MFE, for R-multiple realism
    max_adverse_1h = Column(Float)      # MAE, ditto
    evaluated_at = Column(DateTime)

    __table_args__ = (
        Index('idx_pulse_symbol_ts', 'symbol', 'pulse_ts'),
        Index('idx_pulse_score_ts', 'tradability', 'pulse_ts'),
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