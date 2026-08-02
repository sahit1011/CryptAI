"""
Trade History Manager
Manages trade storage and retrieval using SQLAlchemy
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Boolean, desc, and_
from sqlalchemy.orm import sessionmaker

# Single source of truth for the schema. ``TradeRecord`` below is the sync runtime
# ORM view of the canonical ``trades`` table defined in src.data.data_models.Trade.
# We reuse that ``Base`` (and its MetaData) so Alembic and create_all see exactly
# one authoritative table definition instead of two colliding ones.
from src.data.data_models import Base, Trade


def _redact_db_url(url: str) -> str:
    """Mask the password in a DB URL before logging (never log credentials)."""
    import re
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:****@", url or "")

# TradeRecord is an ALIAS for the canonical Trade model (src.data.data_models.Trade),
# which already holds the union of every column the runtime reads/writes. Previously
# this module re-declared all columns with index=True under extend_existing, which
# registered DUPLICATE Index objects on the shared metadata — so create_all() raised
# DuplicateTable and trade history never initialised. Aliasing yields exactly one
# Table('trades') and one set of indexes. All existing `TradeRecord` usages keep
# working because it is literally the same mapped class.
TradeRecord = Trade

@dataclass
class TradeStats:
    """Aggregate trade statistics"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    total_pnl: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    
    average_rr_ratio: float
    profit_factor: float
    
    average_duration_minutes: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate * 100, 2),
            'total_pnl': round(self.total_pnl, 2),
            'average_win': round(self.average_win, 2),
            'average_loss': round(self.average_loss, 2),
            'largest_win': round(self.largest_win, 2),
            'largest_loss': round(self.largest_loss, 2),
            'average_rr_ratio': round(self.average_rr_ratio, 2),
            'profit_factor': round(self.profit_factor, 2),
            'average_duration_minutes': round(self.average_duration_minutes, 2)
        }

class TradeHistoryManager:
    """
    Trade history management
    
    Stores and retrieves trade records from PostgreSQL/SQLite
    Provides aggregation and analysis capabilities
    """
    
    def __init__(self, database_url: str):
        from src.utils.db import pool_kwargs
        self.engine = create_engine(database_url, **pool_kwargs())
        self._create_schema()

        self.SessionLocal = sessionmaker(bind=self.engine)

        # Ensure schema is up to date
        self._ensure_schema()

        logger.info(f"Trade history manager initialized with DB: {_redact_db_url(database_url)}")

    def _create_schema(self):
        """Create the trades table if absent — resiliently.

        The 'trades' table is mapped by two models (this module + src/data/data_models)
        with extend_existing, so the shared metadata carries DUPLICATE index definitions
        and Base.metadata.create_all() raises DuplicateTable on the second identical
        CREATE INDEX. That previously crashed __init__, leaving trade history permanently
        unavailable. We instead: (1) skip entirely when the table already exists, and
        (2) on a fresh DB create just the table (CreateTable), then add each index
        idempotently, tolerating "already exists". (Root cause to fix later: collapse the
        two TradeRecord definitions into one.)
        """
        from sqlalchemy import inspect
        from sqlalchemy.schema import CreateTable, CreateIndex

        try:
            if inspect(self.engine).has_table('trades'):
                return
            with self.engine.begin() as conn:
                conn.execute(CreateTable(TradeRecord.__table__))
                created = set()
                for index in TradeRecord.__table__.indexes:
                    if index.name in created:
                        continue
                    created.add(index.name)
                    try:
                        conn.execute(CreateIndex(index))
                    except Exception:
                        pass  # duplicate/optional index — safe to skip
        except Exception as e:
            logger.warning(f"trades schema create skipped: {e}")
    
    def _ensure_schema(self):
        """
        Ensure database schema matches the model.
        Adds missing columns if they don't exist.
        """
        from sqlalchemy import inspect, text
        
        inspector = inspect(self.engine)
        
        # Check if trades table exists
        if 'trades' not in inspector.get_table_names():
            logger.info("Trades table doesn't exist, will be created by Base.metadata.create_all")
            return
        
        # Get existing columns
        existing_columns = {col['name'] for col in inspector.get_columns('trades')}
        
        # Define expected columns from the model with their SQL types
        expected_columns = {
            'id': 'SERIAL PRIMARY KEY',
            'trade_id': 'VARCHAR(50) UNIQUE NOT NULL',
            'symbol': 'VARCHAR(20) NOT NULL',
            'direction': 'VARCHAR(10) NOT NULL',
            'strategy_type': 'VARCHAR(20)',
            'entry_price': 'FLOAT NOT NULL',
            'entry_time': 'TIMESTAMP NOT NULL',
            'position_size': 'FLOAT NOT NULL',
            'exit_price': 'FLOAT',
            'exit_time': 'TIMESTAMP',
            'exit_reason': 'VARCHAR(50)',
            'stop_loss': 'FLOAT NOT NULL',
            'take_profit_levels': 'JSON',
            'risk_amount': 'FLOAT NOT NULL',
            'pnl': 'FLOAT',
            'pnl_percentage': 'FLOAT',
            'risk_reward_ratio': 'FLOAT',
            'duration_minutes': 'FLOAT',
            'confidence_score': 'FLOAT DEFAULT 0.0',
            'confluence_count': 'INTEGER DEFAULT 0',
            'market_regime': 'VARCHAR(20)',
            'atr_at_entry': 'FLOAT',
            'volatility_percentile': 'FLOAT',
            'smc_patterns': 'JSON',
            'ict_setups': 'JSON',
            'is_winner': 'BOOLEAN',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'notes': 'VARCHAR(500)'
        }
        
        # Find missing columns
        missing_columns = set(expected_columns.keys()) - existing_columns
        
        if missing_columns:
            logger.warning(f"Missing columns detected in trades table: {missing_columns}")
            
            # Add missing columns
            with self.engine.connect() as conn:
                for col_name in sorted(missing_columns):  # Sort for consistent order
                    try:
                        col_type = expected_columns[col_name]
                        # Remove constraints for ALTER TABLE (can't add NOT NULL to existing table easily)
                        col_type_clean = col_type.replace(' NOT NULL', '').replace(' UNIQUE', '').replace(' PRIMARY KEY', '')
                        
                        sql = f"ALTER TABLE trades ADD COLUMN {col_name} {col_type_clean}"
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info(f"Added column: {col_name} ({col_type_clean})")
                    except Exception as e:
                        logger.error(f"Failed to add column {col_name}: {e}")
                        conn.rollback()
            
            logger.info("Schema migration completed")
        else:
            logger.debug("Database schema is up to date")
    
    def store_trade(
        self,
        trade_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        entry_time: datetime,
        position_size: float,
        stop_loss: float,
        take_profit_levels: List[float],
        risk_amount: float,
        strategy_type: str = "",
        confidence_score: float = 0.0,
        confluence_count: int = 0,
        market_regime: str = "",
        atr_at_entry: float = 0.0,
        smc_patterns: Optional[List[str]] = None,
        ict_setups: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> TradeRecord:
        """Store a new trade record.

        `user_id` attributes the row to its owning tenant. Without it the row is
        invisible to the owner's scoped reads (/api/trades filters by user_id) and
        pools into unscoped service reads — a tenancy attribution bug, not cosmetics.
        None is allowed only for the single-bot path.
        """
        
        session = self.SessionLocal()
        
        try:
            trade = TradeRecord(
                trade_id=trade_id,
                user_id=user_id,
                symbol=symbol,
                direction=direction,
                strategy_type=strategy_type,
                entry_price=entry_price,
                entry_time=entry_time,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit_levels=take_profit_levels,
                risk_amount=risk_amount,
                confidence_score=confidence_score,
                confluence_count=confluence_count,
                market_regime=market_regime,
                atr_at_entry=atr_at_entry,
                smc_patterns=smc_patterns or [],
                ict_setups=ict_setups or []
            )
            
            session.add(trade)
            session.commit()
            session.refresh(trade)
            
            logger.info(f"Trade stored: {trade_id} - {direction} {symbol} @ ${entry_price}")
            
            return trade
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store trade: {e}")
            raise
        finally:
            session.close()
    
    def update_trade_entry(
        self,
        trade_id: str,
        entry_price: float,
        entry_time: datetime
    ) -> TradeRecord:
        """Update trade with actual entry details"""
        
        session = self.SessionLocal()
        
        try:
            trade = session.query(TradeRecord).filter_by(trade_id=trade_id).first()
            
            if not trade:
                raise ValueError(f"Trade not found: {trade_id}")
            
            # Update entry details
            trade.entry_price = entry_price
            trade.entry_time = entry_time
            
            session.commit()
            session.refresh(trade)
            
            logger.info(f"Trade entry updated: {trade_id} @ ${entry_price}")
            
            return trade
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update trade entry: {e}")
            raise
        finally:
            session.close()

    def update_trade_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        notes: Optional[str] = None
    ) -> TradeRecord:
        """Update trade with exit details"""
        
        session = self.SessionLocal()
        
        try:
            trade = session.query(TradeRecord).filter_by(trade_id=trade_id).first()
            
            if not trade:
                raise ValueError(f"Trade not found: {trade_id}")
            
            # Update exit details
            trade.exit_price = exit_price
            trade.exit_time = exit_time
            trade.exit_reason = exit_reason
            
            # Calculate P&L
            if trade.direction == 'LONG':
                trade.pnl = (exit_price - trade.entry_price) * trade.position_size
            else:
                trade.pnl = (trade.entry_price - exit_price) * trade.position_size
            
            trade.pnl_percentage = (trade.pnl / (trade.entry_price * trade.position_size)) * 100
            
            # Calculate actual RR ratio
            if trade.risk_amount > 0:
                if trade.pnl > 0:
                    trade.risk_reward_ratio = abs(trade.pnl) / trade.risk_amount
                else:
                    trade.risk_reward_ratio = -(abs(trade.pnl) / trade.risk_amount)
            else:
                trade.risk_reward_ratio = 0.0
            
            # Duration
            trade.duration_minutes = (exit_time - trade.entry_time).total_seconds() / 60
            
            # Winner/loser
            trade.is_winner = trade.pnl > 0
            
            # Notes
            if notes:
                trade.notes = notes
            
            session.commit()
            session.refresh(trade)
            
            logger.info(
                f"Trade updated: {trade_id} - "
                f"P&L: ${trade.pnl:.2f} ({trade.pnl_percentage:.2f}%)"
            )
            
            return trade
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update trade: {e}")
            raise
        finally:
            session.close()
    
    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get trade by ID"""
        session = self.SessionLocal()
        try:
            return session.query(TradeRecord).filter_by(trade_id=trade_id).first()
        finally:
            session.close()
    
    def get_recent_trades(
        self,
        limit: int = 100,
        symbol: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[TradeRecord]:
        """Get recent trades, optionally scoped to a single tenant.

        When `user_id` is provided, only that user's trades are returned — the
        multi-tenancy scoping primitive. When None (single-tenant / legacy), all
        trades are returned, preserving existing behaviour.
        """
        session = self.SessionLocal()
        try:
            query = session.query(TradeRecord).order_by(desc(TradeRecord.entry_time))

            if symbol:
                query = query.filter_by(symbol=symbol)
            if user_id:
                query = query.filter_by(user_id=user_id)

            return query.limit(limit).all()
        finally:
            session.close()
    
    def get_strategy_performance(self) -> Dict[str, TradeStats]:
        """Get performance stats grouped by strategy type"""
        session = self.SessionLocal()
        try:
            # Get all strategy types
            strategies = session.query(TradeRecord.strategy_type).distinct().all()
            strategies = [s[0] for s in strategies if s[0]]
            
            performance = {}
            for strategy in strategies:
                stats = self.calculate_stats(strategy_type=strategy)
                performance[strategy] = stats
                
            return performance
        finally:
            session.close()
    
    def calculate_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
        strategy_type: Optional[str] = None
    ) -> TradeStats:
        """Calculate aggregate statistics"""
        session = self.SessionLocal()
        
        try:
            # Build query
            query = session.query(TradeRecord).filter(
                TradeRecord.exit_time.isnot(None)
            )
            
            if start_date:
                query = query.filter(TradeRecord.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeRecord.entry_time <= end_date)
            if symbol:
                query = query.filter_by(symbol=symbol)
            if strategy_type:
                query = query.filter_by(strategy_type=strategy_type)
            
            trades = query.all()
            
            if not trades:
                return TradeStats(
                    total_trades=0, winning_trades=0, losing_trades=0,
                    win_rate=0.0, total_pnl=0.0, average_win=0.0,
                    average_loss=0.0, largest_win=0.0, largest_loss=0.0,
                    average_rr_ratio=0.0, profit_factor=0.0,
                    average_duration_minutes=0.0
                )
            
            # Calculate metrics
            total_trades = len(trades)
            winners = [t for t in trades if t.is_winner]
            losers = [t for t in trades if not t.is_winner]
            
            winning_trades = len(winners)
            losing_trades = len(losers)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
            
            wins = [t.pnl for t in winners if t.pnl is not None]
            losses = [t.pnl for t in losers if t.pnl is not None]
            
            average_win = sum(wins) / len(wins) if wins else 0
            average_loss = sum(losses) / len(losses) if losses else 0
            
            largest_win = max(wins) if wins else 0
            largest_loss = min(losses) if losses else 0
            
            rrs = [t.risk_reward_ratio for t in trades if t.risk_reward_ratio is not None]
            average_rr = sum(rrs) / len(rrs) if rrs else 0
            
            gross_profit = sum(wins) if wins else 0
            gross_loss = abs(sum(losses)) if losses else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            durations = [t.duration_minutes for t in trades if t.duration_minutes is not None]
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            return TradeStats(
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                total_pnl=total_pnl,
                average_win=average_win,
                average_loss=average_loss,
                largest_win=largest_win,
                largest_loss=largest_loss,
                average_rr_ratio=average_rr,
                profit_factor=profit_factor,
                average_duration_minutes=avg_duration
            )
            
        finally:
            session.close()
