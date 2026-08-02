"""
Portfolio State Tracker
Maintains real-time view of portfolio positions and risk exposure
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import json
from pathlib import Path
from src.utils.pipeline_logger import PipelineLogger

# Create pipeline logger instance
plog = PipelineLogger()


@dataclass
class Position:
    """Represents a single open position"""
    position_id: str
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    current_price: float
    position_size: float
    stop_loss: float
    take_profit_levels: List[float]

    # Risk metrics
    risk_amount: float  # Dollars at risk (entry to SL)
    unrealized_pnl: float  # Current P&L
    risk_percentage: float  # % of account at risk

    # Metadata
    opened_at: datetime
    strategy_type: str  # 'SCALP', 'DAY_TRADE', 'SWING'
    confidence_score: float

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate current unrealized P&L"""
        if self.direction == 'LONG':
            return (current_price - self.entry_price) * self.position_size
        else:
            return (self.entry_price - current_price) * self.position_size

    def is_profitable(self) -> bool:
        """Check if position is in profit"""
        return self.unrealized_pnl > 0

    def hit_stop_loss(self, current_price: float) -> bool:
        """Check if stop-loss is hit"""
        if self.direction == 'LONG':
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def to_dict(self) -> Dict[str, Any]:
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'position_size': self.position_size,
            'stop_loss': self.stop_loss,
            'take_profit_levels': self.take_profit_levels,
            'risk_amount': round(self.risk_amount, 2),
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'risk_percentage': round(self.risk_percentage * 100, 2),
            'opened_at': self.opened_at.isoformat(),
            'strategy_type': self.strategy_type,
            'confidence_score': self.confidence_score
        }


@dataclass
class PortfolioSnapshot:
    """Complete portfolio state at a point in time"""
    timestamp: datetime
    account_balance: float
    total_equity: float  # Balance + unrealized P&L

    open_positions: List[Position] = field(default_factory=list)

    # Portfolio-level metrics
    total_unrealized_pnl: float = 0.0
    total_risk_amount: float = 0.0
    portfolio_heat: float = 0.0  # Total exposure as % of equity

    # Daily metrics
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0
    daily_start_equity: float = 0.0  # equity at the start of the trading day

    # Drawdown tracking
    peak_equity: float = 0.0
    current_drawdown: float = 0.0  # % from peak
    current_drawdown_dollars: float = 0.0

    # Streak tracking
    win_streak: int = 0
    loss_streak: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'account_balance': round(self.account_balance, 2),
            'total_equity': round(self.total_equity, 2),
            'open_positions': len(self.open_positions),
            'positions': [pos.to_dict() for pos in self.open_positions],
            'total_unrealized_pnl': round(self.total_unrealized_pnl, 2),
            'total_risk_amount': round(self.total_risk_amount, 2),
            'portfolio_heat': round(self.portfolio_heat * 100, 2),
            'daily_pnl': round(self.daily_pnl, 2),
            'daily_trades': self.daily_trades,
            'daily_win_rate': round(
                self.daily_wins / max(self.daily_trades, 1) * 100, 1
            ),
            'peak_equity': round(self.peak_equity, 2),
            'current_drawdown': round(self.current_drawdown * 100, 2),
            'current_drawdown_dollars': round(self.current_drawdown_dollars, 2),
            'win_streak': self.win_streak,
            'loss_streak': self.loss_streak
        }

    def to_risk_dict(self) -> Dict[str, Any]:
        """Return risk metrics in RAW FRACTION units for the circuit breaker.

        to_dict() multiplies heat/drawdown by 100 for human display; feeding that to
        the circuit breaker (which compares against fractions like 0.08 / 0.20) made it
        trip on ~0.08% heat and halt all trading. This method keeps fractions and also
        exposes daily_start_equity so the daily-loss check uses real equity instead of
        the hardcoded $10k fallback.
        """
        return {
            'portfolio_heat': self.portfolio_heat,          # fraction (0.06 == 6%)
            'current_drawdown': self.current_drawdown,      # fraction (0.20 == 20%)
            'daily_pnl': self.daily_pnl,
            'daily_start_equity': self.daily_start_equity,
            'total_equity': self.total_equity,
            'loss_streak': self.loss_streak,
            'win_streak': self.win_streak,
        }


class PortfolioStateTracker:
    """
    Tracks real-time portfolio state and risk exposure

    Responsibilities:
    - Maintain list of open positions
    - Calculate portfolio-level risk metrics
    - Track daily/weekly performance
    - Monitor drawdowns
    - Provide risk exposure data
    """

    # Fixed filename for the "latest known good" snapshot. This is the file that
    # reconcile_on_startup() loads after a restart, so it must be stable (not
    # timestamped). Timestamped snapshots are still written for history/auditing.
    LATEST_SNAPSHOT_FILENAME = "portfolio_latest.json"

    def __init__(
        self,
        initial_balance: float = 10000.0,
        state_manager: Optional[Any] = None,
        snapshot_dir: Optional[str] = None,
        exchange: Optional[Any] = None
    ):
        self.initial_balance = initial_balance
        self.account_balance = initial_balance
        self.state_manager = state_manager
        # Optional exchange client used by reconcile_on_startup() in LIVE mode to
        # query the broker's authoritative open positions. May be set later via
        # set_exchange(). When None, reconciliation falls back to snapshot-only.
        self.exchange = exchange

        # Active positions
        self.positions: Dict[str, Position] = {}

        # Performance tracking
        self.peak_equity = initial_balance
        self.daily_start_equity = initial_balance
        self.daily_start_date = datetime.now().date()
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0

        # Streak tracking
        self.win_streak = 0
        self.loss_streak = 0
        self.last_trade_result = None

        # Historical snapshots (for analysis)
        self.hourly_snapshots: List[PortfolioSnapshot] = []

        # Circuit breaker state
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        self.circuit_breaker_triggered_at: Optional[datetime] = None

        # Correlation tracking
        self.correlated_pairs = [
            ['BTCUSDT', 'ETHUSDT'],
            ['BTCUSDT', 'BNBUSDT'],
            ['ETHUSDT', 'BNBUSDT'],
        ]

        # Snapshot persistence
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else Path("data/snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._lock = asyncio.Lock()

        plog.info(
            f"Portfolio tracker initialized with ${initial_balance:,.2f}",
            agent="risk_agent",
            phase="initialization"
        )

    def _total_equity_unlocked(self) -> float:
        """Total equity (balance + unrealized P&L).

        The caller MUST already hold self._lock. Methods that already hold the lock
        must use this instead of get_current_snapshot() (which re-acquires the
        non-reentrant lock and would deadlock).
        """
        return self.account_balance + sum(
            pos.unrealized_pnl for pos in self.positions.values()
        )

    def _maybe_roll_daily_unlocked(self) -> None:
        """Reset daily counters when the calendar day has rolled over.

        Caller MUST hold self._lock. Without this the daily-loss circuit breaker's
        baseline (daily_start_equity) never resets, so daily_pnl drifts from the
        account's inception balance instead of the start of the current day.
        """
        today = datetime.now().date()
        if today != self.daily_start_date:
            self.daily_start_date = today
            self.daily_start_equity = self._total_equity_unlocked()
            self.daily_trades = 0
            self.daily_wins = 0
            self.daily_losses = 0

    async def add_position(
        self,
        position_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        position_size: float,
        stop_loss: float,
        take_profit_levels: List[float],
        risk_amount: float,
        strategy_type: str = 'DAY_TRADE',
        confidence_score: float = 0.75
    ) -> Position:
        """
        Add a new open position
        """
        async with self._lock:
            position = Position(
                position_id=position_id,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                current_price=entry_price,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit_levels=take_profit_levels,
                risk_amount=risk_amount,
                unrealized_pnl=0.0,
                risk_percentage=risk_amount / self.account_balance,
                opened_at=datetime.now(),
                strategy_type=strategy_type,
                confidence_score=confidence_score
            )

            self.positions[position_id] = position
            plog.debug(
                f"Added position {position_id}: {direction} {symbol} @ ${entry_price:,.2f}",
                agent="risk_agent",
                phase="position_tracking"
            )

        # Persist OUTSIDE the lock: save_snapshot()/get_current_snapshot() re-acquire
        # self._lock, which is a non-reentrant asyncio.Lock, so calling them while
        # holding it would deadlock.
        await self._persist()

        return position

    async def update_position_price(
        self, position_id: str, current_price: float
    ):
        """Update position with current market price"""
        async with self._lock:
            if position_id not in self.positions:
                plog.warning(
                    f"Position {position_id} not found",
                    agent="risk_agent",
                    phase="position_tracking"
                )
                return

            position = self.positions[position_id]
            position.current_price = current_price
            position.unrealized_pnl = position.calculate_pnl(current_price)

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = 'manual'
    ) -> Dict[str, Any]:
        """
        Close a position and record P&L
        """
        async with self._lock:
            if position_id not in self.positions:
                plog.warning(
                    f"Position {position_id} not found",
                    agent="risk_agent",
                    phase="position_tracking"
                )
                return {}

            position = self.positions[position_id]

            # Calculate final P&L
            final_pnl = position.calculate_pnl(exit_price)

            # Update account balance
            self.account_balance += final_pnl

            # Update daily stats
            self.daily_trades += 1
            if final_pnl > 0:
                self.daily_wins += 1
                self.win_streak += 1
                self.loss_streak = 0
            else:
                self.daily_losses += 1
                self.loss_streak += 1
                self.win_streak = 0

            # Update peak equity
            if self.account_balance > self.peak_equity:
                self.peak_equity = self.account_balance

            # Remove position
            del self.positions[position_id]

            result = {
                'position_id': position_id,
                'symbol': position.symbol,
                'direction': position.direction,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'pnl': round(final_pnl, 2),
                # Guarded: a zero risk_amount (possible for hand-sized tickets before
                # sizing was derived upstream) must not turn a close into a crash that
                # skips the _persist() below.
                'pnl_percentage': round(
                    (final_pnl / position.risk_amount) * 100, 2
                ) if position.risk_amount > 0 else 0.0,
                'duration': (
                    datetime.now() - position.opened_at
                ).total_seconds(),
                'reason': reason,
                'new_balance': round(self.account_balance, 2)
            }

            plog.info(
                f"Closed position {position_id}: P&L ${final_pnl:,.2f} "
                f"({result['pnl_percentage']}%) - {reason}",
                agent="risk_agent",
                phase="position_tracking"
            )

        # Persist OUTSIDE the lock (see note in add_position).
        await self._persist()

        return result

    async def get_current_snapshot(self) -> PortfolioSnapshot:
        """
        Get current portfolio snapshot with all metrics
        """
        async with self._lock:
            # Roll daily counters if the calendar day changed, so the daily-loss
            # circuit breaker measures against today's opening equity.
            self._maybe_roll_daily_unlocked()

            # Update all positions with latest prices
            total_unrealized = sum(
                pos.unrealized_pnl for pos in self.positions.values()
            )
            total_risk = sum(
                pos.risk_amount for pos in self.positions.values()
            )

            total_equity = self.account_balance + total_unrealized

            # Calculate portfolio heat
            portfolio_heat = (
                total_risk / total_equity if total_equity > 0 else 0
            )

            # Calculate drawdown
            current_drawdown = (
                (self.peak_equity - total_equity) / self.peak_equity
                if self.peak_equity > 0
                else 0
            )
            current_drawdown_dollars = self.peak_equity - total_equity

            # Daily P&L
            daily_pnl = total_equity - self.daily_start_equity

            snapshot = PortfolioSnapshot(
                timestamp=datetime.now(),
                account_balance=self.account_balance,
                total_equity=total_equity,
                open_positions=list(self.positions.values()),
                total_unrealized_pnl=total_unrealized,
                total_risk_amount=total_risk,
                portfolio_heat=portfolio_heat,
                daily_pnl=daily_pnl,
                daily_trades=self.daily_trades,
                daily_wins=self.daily_wins,
                daily_losses=self.daily_losses,
                peak_equity=self.peak_equity,
                current_drawdown=current_drawdown,
                current_drawdown_dollars=current_drawdown_dollars,
                win_streak=self.win_streak,
                loss_streak=self.loss_streak,
                daily_start_equity=self.daily_start_equity
            )

            return snapshot

    async def get_position_count(self) -> int:
        """Get number of open positions"""
        async with self._lock:
            return len(self.positions)

    async def get_total_exposure(self) -> float:
        """Get total portfolio heat (exposure as % of equity)"""
        snapshot = await self.get_current_snapshot()
        return snapshot.portfolio_heat

    async def get_available_risk_capacity(
        self, max_portfolio_heat: float = 0.06
    ) -> float:
        """
        Calculate available risk capacity

        Returns:
            Remaining % of equity that can be risked
        """
        current_heat = await self.get_total_exposure()
        available = max(0, max_portfolio_heat - current_heat)
        return available

    async def can_add_risk(
        self, new_risk_amount: float, max_heat: float = 0.06
    ) -> bool:
        """
        Check if we can add more risk without exceeding max heat
        """
        snapshot = await self.get_current_snapshot()
        new_risk_pct = new_risk_amount / snapshot.total_equity
        projected_heat = snapshot.portfolio_heat + new_risk_pct

        can_add = projected_heat <= max_heat

        if not can_add:
            plog.warning(
                f"Cannot add risk: Current {snapshot.portfolio_heat*100:.2f}% "
                f"+ New {new_risk_pct*100:.2f}% = {projected_heat*100:.2f}% "
                f"exceeds max {max_heat*100:.2f}%",
                agent="risk_agent",
                phase="risk_capacity_check"
            )

        return can_add

    async def reset_daily_stats(self):
        """Reset daily statistics (call at start of each day).

        Daily reset also happens automatically on the day boundary inside
        get_current_snapshot(); this remains for explicit/manual resets.
        """
        async with self._lock:
            # Use the unlocked helper — get_current_snapshot() would re-acquire the
            # lock we already hold and deadlock.
            self.daily_start_equity = self._total_equity_unlocked()
            self.daily_start_date = datetime.now().date()
            self.daily_trades = 0
            self.daily_wins = 0
            self.daily_losses = 0

            plog.info(
                "Daily stats reset",
                agent="risk_agent",
                phase="daily_reset"
            )

    async def add_snapshot(self, snapshot: PortfolioSnapshot):
        """Add hourly snapshot to history"""
        async with self._lock:
            self.hourly_snapshots.append(snapshot)
            # Keep only last 168 snapshots (1 week if hourly)
            if len(self.hourly_snapshots) > 168:
                self.hourly_snapshots.pop(0)

    async def get_snapshots(
        self, limit: int = 24
    ) -> List[PortfolioSnapshot]:
        """Get recent snapshots"""
        async with self._lock:
            return self.hourly_snapshots[-limit:]

    async def get_positions_list(self) -> List[Dict[str, Any]]:
        """Get list of all open positions as dictionaries"""
        async with self._lock:
            return [pos.to_dict() for pos in self.positions.values()]

    async def check_position_exists(self, position_id: str) -> bool:
        """Check if position exists"""
        async with self._lock:
            return position_id in self.positions

    async def get_position(self, position_id: str) -> Optional[Position]:
        """Get specific position"""
        async with self._lock:
            return self.positions.get(position_id)

    async def get_positions_by_symbol(self, symbol: str) -> List[Position]:
        """Get all positions for a specific symbol"""
        async with self._lock:
            return [
                pos for pos in self.positions.values()
                if pos.symbol == symbol
            ]

    async def get_total_position_size(self, symbol: str) -> float:
        """Get total position size for a symbol"""
        positions = await self.get_positions_by_symbol(symbol)
        return sum(pos.position_size for pos in positions)

    async def calculate_symbol_heat(self, symbol: str) -> float:
        """Calculate total heat (risk exposure) for a symbol"""
        snapshot = await self.get_current_snapshot()
        positions = await self.get_positions_by_symbol(symbol)
        total_symbol_risk = sum(pos.risk_amount for pos in positions)

        return (
            total_symbol_risk / snapshot.total_equity
            if snapshot.total_equity > 0
            else 0
        )

    async def get_winning_positions(self) -> List[Position]:
        """Get all profitable positions"""
        async with self._lock:
            return [
                pos for pos in self.positions.values()
                if pos.is_profitable()
            ]

    async def get_losing_positions(self) -> List[Position]:
        """Get all losing positions"""
        async with self._lock:
            return [
                pos for pos in self.positions.values()
                if not pos.is_profitable()
            ]

    async def calculate_win_rate(self) -> float:
        """Calculate current win rate"""
        if self.daily_trades == 0:
            return 0.0
        return self.daily_wins / self.daily_trades

    async def check_correlation(
        self,
        new_symbol: str,
        new_direction: str = 'LONG'
    ) -> Dict[str, Any]:
        """
        Enhanced correlation analysis for new position
        
        Returns:
            {
                'has_correlation': bool,
                'correlated_positions': List[Dict],
                'total_correlated_exposure': float,
                'correlation_risk_score': float,  # 0-1
                'recommended_size_adjustment': float  # multiplier
            }
        """
        async with self._lock:
            correlated_positions = []
            total_exposure = 0.0
            
            for pos_id, position in self.positions.items():
                # Check if symbols are in same correlation group
                is_correlated = False
                for pair in self.correlated_pairs:
                    if new_symbol in pair and position.symbol in pair:
                        is_correlated = True
                        break
                
                if is_correlated:
                    # Check if same direction (higher correlation risk)
                    same_direction = position.direction == new_direction
                    
                    correlated_positions.append({
                        'position_id': pos_id,
                        'symbol': position.symbol,
                        'direction': position.direction,
                        'risk_amount': position.risk_amount,
                        'same_direction': same_direction
                    })
                    
                    # Weight same direction higher
                    weight = 1.0 if same_direction else 0.5
                    total_exposure += position.risk_amount * weight
            
            # Calculate correlation risk score (0-1). Use the unlocked equity helper —
            # calling get_current_snapshot() here would re-acquire self._lock (which we
            # already hold) and deadlock, so this check always timed out after 5s and
            # the correlation limit was never actually enforced.
            total_equity = self._total_equity_unlocked()
            correlation_pct = total_exposure / total_equity if total_equity > 0 else 0
            
            # Risk score: 0 = no correlation, 1 = high correlation
            risk_score = min(correlation_pct / 0.04, 1.0)  # 4% = max acceptable
            
            # Recommend size adjustment (reduce if high correlation)
            # 0% correlation = 1.0x, 4%+ correlation = 0.5x
            size_adjustment = max(1.0 - (risk_score * 0.5), 0.5)
            
            return {
                'has_correlation': len(correlated_positions) > 0,
                'correlated_positions': correlated_positions,
                'total_correlated_exposure': round(total_exposure, 2),
                'correlation_risk_score': round(risk_score, 2),
                'recommended_size_adjustment': round(size_adjustment, 2),
                'correlation_message': (
                    f"Found {len(correlated_positions)} correlated position(s). "
                    f"Total exposure: ${total_exposure:.2f} ({correlation_pct*100:.1f}%). "
                    f"Recommend {size_adjustment:.0%} size."
                    if correlated_positions
                    else "No correlation detected"
                )
            }
    
    async def activate_circuit_breaker(self, reason: str):
        """Activate circuit breaker to halt trading"""
        async with self._lock:
            self.circuit_breaker_active = True
            self.circuit_breaker_reason = reason
            self.circuit_breaker_triggered_at = datetime.now()
            
            plog.error(
                f"🚨 CIRCUIT BREAKER ACTIVATED: {reason}",
                agent="risk_agent",
                phase="circuit_breaker"
            )

        # Persist OUTSIDE the lock so the circuit-breaker state survives a restart.
        await self._persist()

    async def deactivate_circuit_breaker(self, manual: bool = False):
        """Deactivate circuit breaker"""
        async with self._lock:
            if not self.circuit_breaker_active:
                return
            
            self.circuit_breaker_active = False
            reset_type = "manual" if manual else "automatic"
            
            plog.info(
                f"Circuit breaker deactivated ({reset_type})",
                agent="risk_agent",
                phase="circuit_breaker"
            )

            self.circuit_breaker_reason = ""
            self.circuit_breaker_triggered_at = None

        # Persist OUTSIDE the lock so the cleared circuit-breaker state survives a restart.
        await self._persist()
    
    async def is_circuit_breaker_active(self) -> Tuple[bool, str]:
        """Check if circuit breaker is active"""
        async with self._lock:
            return self.circuit_breaker_active, self.circuit_breaker_reason
    
    async def save_snapshot(self, filename: Optional[str] = None) -> str:
        """
        Save current portfolio snapshot to file
        
        Returns:
            Path to saved snapshot file
        """
        snapshot = await self.get_current_snapshot()
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"portfolio_snapshot_{timestamp}.json"
        
        filepath = self.snapshot_dir / filename
        
        snapshot_data = {
            'snapshot': snapshot.to_dict(),
            'tracker_state': self.to_dict(),
            'circuit_breaker': {
                'active': self.circuit_breaker_active,
                'reason': self.circuit_breaker_reason,
                'triggered_at': (
                    self.circuit_breaker_triggered_at.isoformat()
                    if self.circuit_breaker_triggered_at
                    else None
                )
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(snapshot_data, f, indent=2, default=str)
        
        plog.debug(
            f"Saved portfolio snapshot to {filepath}",
            agent="risk_agent",
            phase="snapshot_persistence"
        )
        
        return str(filepath)
    
    async def load_snapshot(self, filepath: str) -> bool:
        """
        Load portfolio snapshot from file
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Restore tracker state
            tracker_state = data.get('tracker_state', {})
            self.account_balance = tracker_state.get('account_balance', self.initial_balance)
            self.peak_equity = tracker_state.get('peak_equity', self.initial_balance)
            self.daily_start_equity = tracker_state.get('daily_start_equity', self.initial_balance)
            self.daily_trades = tracker_state.get('daily_trades', 0)
            self.daily_wins = tracker_state.get('daily_wins', 0)
            self.daily_losses = tracker_state.get('daily_losses', 0)
            self.win_streak = tracker_state.get('win_streak', 0)
            self.loss_streak = tracker_state.get('loss_streak', 0)
            
            # Restore circuit breaker state
            cb_state = data.get('circuit_breaker', {})
            self.circuit_breaker_active = cb_state.get('active', False)
            self.circuit_breaker_reason = cb_state.get('reason', '')
            triggered_at_str = cb_state.get('triggered_at')
            if triggered_at_str:
                self.circuit_breaker_triggered_at = datetime.fromisoformat(triggered_at_str)

            # Restore open positions so risk counters (count/heat) survive a restart.
            # Previously only scalar counters were restored and positions were lost,
            # which left heat/open-position limits at zero after a restart.
            self.positions = {}
            for pos_dict in data.get('snapshot', {}).get('positions', []):
                try:
                    position = self._position_from_dict(pos_dict)
                    self.positions[position.position_id] = position
                except Exception as pos_err:  # never let one bad row drop the whole load
                    plog.warning(
                        f"Skipping un-restorable position {pos_dict.get('position_id')}: {pos_err}",
                        agent="risk_agent",
                        phase="snapshot_persistence"
                    )

            plog.info(
                f"Loaded portfolio snapshot from {filepath} "
                f"({len(self.positions)} open position(s))",
                agent="risk_agent",
                phase="snapshot_persistence"
            )

            return True
            
        except Exception as e:
            plog.error(
                f"Failed to load snapshot from {filepath}: {e}",
                exception=e,
                agent="risk_agent",
                phase="snapshot_persistence"
            )
            return False

    @staticmethod
    def _position_from_dict(pos_dict: Dict[str, Any]) -> Position:
        """
        Rebuild a Position from its to_dict() representation.

        Note: Position.to_dict() stores risk_percentage already multiplied by 100,
        so we divide it back here to keep the internal fraction convention.
        """
        return Position(
            position_id=pos_dict['position_id'],
            symbol=pos_dict['symbol'],
            direction=pos_dict['direction'],
            entry_price=float(pos_dict['entry_price']),
            current_price=float(pos_dict.get('current_price', pos_dict['entry_price'])),
            position_size=float(pos_dict['position_size']),
            stop_loss=float(pos_dict.get('stop_loss', 0.0)),
            take_profit_levels=list(pos_dict.get('take_profit_levels', []) or []),
            risk_amount=float(pos_dict.get('risk_amount', 0.0)),
            unrealized_pnl=float(pos_dict.get('unrealized_pnl', 0.0)),
            risk_percentage=float(pos_dict.get('risk_percentage', 0.0)) / 100.0,
            opened_at=datetime.fromisoformat(pos_dict['opened_at'])
            if pos_dict.get('opened_at') else datetime.now(),
            strategy_type=pos_dict.get('strategy_type', 'DAY_TRADE'),
            confidence_score=float(pos_dict.get('confidence_score', 0.75))
        )

    def set_exchange(self, exchange: Any) -> None:
        """
        Attach the live exchange client used by reconcile_on_startup().

        Wiring is intentionally late-bound: the tracker is created by the risk
        agent, while the exchange client lives on the execution agent, so the
        orchestrator (or execution agent) can inject it before startup.
        """
        self.exchange = exchange

    async def _persist(self) -> None:
        """
        Lightweight persistence hook called after every state-changing mutation.

        Writes the authoritative "latest" snapshot to a stable filename so it can
        be reloaded on the next startup. Best-effort: persistence failures must
        never propagate into the trading hot path (a failed disk write should not
        crash an order/close), so all exceptions are swallowed and logged.

        Must be called OUTSIDE self._lock because save_snapshot() re-acquires it.
        """
        try:
            await self.save_snapshot(filename=self.LATEST_SNAPSHOT_FILENAME)
        except Exception as e:
            plog.warning(
                f"Failed to persist portfolio snapshot: {e}",
                agent="risk_agent",
                phase="snapshot_persistence"
            )

    async def reconcile_on_startup(self, live_mode: bool = False) -> Dict[str, Any]:
        """
        Rebuild authoritative risk/portfolio state after a restart.

        Steps:
          1. Load the last persisted snapshot (restores balance, daily counters,
             drawdown, circuit-breaker state, and the snapshot's open positions).
          2. In LIVE mode only, query the exchange's actual open positions and
             treat THEM as authoritative for open-position/heat state, logging any
             drift between the snapshot and the exchange (ghost or missing
             positions). Paper mode skips the exchange call entirely.

        This is deliberately resilient: any failure is logged and swallowed so it
        can never crash agent startup. Returns a summary dict for callers/tests.

        Args:
            live_mode: When True, query the exchange for authoritative positions.
                       When False (paper), only the snapshot is loaded.
        """
        summary: Dict[str, Any] = {
            'snapshot_loaded': False,
            'live_mode': live_mode,
            'exchange_queried': False,
            'snapshot_positions': 0,
            'exchange_positions': 0,
            'ghost_positions': [],     # in snapshot but not on exchange
            'missing_positions': [],   # on exchange but not in snapshot
            'drift_detected': False,
            'error': None,
        }

        try:
            # 1. Load the last persisted snapshot, if one exists.
            latest_path = self.snapshot_dir / self.LATEST_SNAPSHOT_FILENAME
            if latest_path.exists():
                summary['snapshot_loaded'] = await self.load_snapshot(str(latest_path))
            else:
                plog.info(
                    "No prior portfolio snapshot found; starting from a clean state",
                    agent="risk_agent",
                    phase="reconciliation"
                )

            summary['snapshot_positions'] = len(self.positions)

            # 2. Paper mode: snapshot is the source of truth, no exchange call.
            if not live_mode:
                plog.info(
                    f"Reconciliation (paper): restored {len(self.positions)} "
                    f"position(s) from snapshot",
                    agent="risk_agent",
                    phase="reconciliation"
                )
                return summary

            # LIVE mode: the exchange is the authority for open positions.
            if self.exchange is None:
                plog.warning(
                    "LIVE reconciliation requested but no exchange is attached; "
                    "falling back to snapshot-only state",
                    agent="risk_agent",
                    phase="reconciliation"
                )
                return summary

            exchange_positions = await self.exchange.get_open_positions()
            summary['exchange_queried'] = True
            summary['exchange_positions'] = len(exchange_positions)

            # Index live positions by symbol for drift comparison. (The tracker
            # keys positions by an internal position_id; the exchange reports by
            # symbol, so symbol is the only stable join key across the boundary.)
            live_by_symbol = {ep.symbol: ep for ep in exchange_positions}
            snapshot_symbols = {pos.symbol for pos in self.positions.values()}

            # Ghost positions: tracked locally but absent on the exchange.
            summary['ghost_positions'] = sorted(
                snapshot_symbols - set(live_by_symbol.keys())
            )
            # Missing positions: live on the exchange but not in our snapshot.
            summary['missing_positions'] = sorted(
                set(live_by_symbol.keys()) - snapshot_symbols
            )
            summary['drift_detected'] = bool(
                summary['ghost_positions'] or summary['missing_positions']
            )

            if summary['drift_detected']:
                plog.warning(
                    "Position drift detected during reconciliation | "
                    f"ghosts (in state, not on exchange)={summary['ghost_positions']} | "
                    f"missing (on exchange, not in state)={summary['missing_positions']}",
                    agent="risk_agent",
                    phase="reconciliation"
                )

            # Rebuild authoritative open-position state from the exchange so that
            # open-position count and portfolio heat reflect reality, not stale
            # memory. We preserve risk metadata (stop_loss, risk_amount, etc.)
            # from the snapshot where the symbol matches; otherwise we synthesize
            # a conservative entry from the exchange data.
            rebuilt: Dict[str, Position] = {}
            existing_by_symbol = {pos.symbol: pos for pos in self.positions.values()}

            async with self._lock:
                for ep in exchange_positions:
                    prior = existing_by_symbol.get(ep.symbol)
                    if prior is not None:
                        # Keep risk metadata; refresh live price/PnL from exchange.
                        prior.current_price = ep.mark_price
                        prior.unrealized_pnl = ep.unrealized_pnl
                        rebuilt[prior.position_id] = prior
                    else:
                        # Exchange position with no local record (missing). Create a
                        # tracked position with conservative defaults so it counts
                        # toward heat/limits and is not left dangling.
                        position_id = f"reconciled_{ep.symbol}"
                        rebuilt[position_id] = Position(
                            position_id=position_id,
                            symbol=ep.symbol,
                            direction=ep.side,
                            entry_price=ep.entry_price,
                            current_price=ep.mark_price,
                            position_size=ep.quantity,
                            stop_loss=0.0,
                            take_profit_levels=[],
                            # No known SL -> assume full notional at risk so heat is
                            # not under-counted; this is intentionally conservative.
                            risk_amount=ep.entry_price * ep.quantity,
                            unrealized_pnl=ep.unrealized_pnl,
                            risk_percentage=(
                                (ep.entry_price * ep.quantity) / self.account_balance
                                if self.account_balance > 0 else 0.0
                            ),
                            opened_at=datetime.now(),
                            strategy_type='DAY_TRADE',
                            confidence_score=0.5
                        )

                self.positions = rebuilt

            plog.info(
                f"Reconciliation (live): rebuilt {len(self.positions)} authoritative "
                f"position(s) from exchange "
                f"(snapshot had {summary['snapshot_positions']})",
                agent="risk_agent",
                phase="reconciliation"
            )

            # Persist the reconciled, authoritative state immediately.
            await self._persist()

        except Exception as e:
            # Reconciliation must never crash startup.
            summary['error'] = str(e)
            plog.error(
                f"Reconciliation failed (continuing with current state): {e}",
                exception=e,
                agent="risk_agent",
                phase="reconciliation"
            )

        return summary

    async def sync_with_state_manager(self):
        """Sync portfolio state with StateManager"""
        if not self.state_manager:
            return
        
        try:
            snapshot = await self.get_current_snapshot()
            
            # Update state manager with current portfolio state
            await self.state_manager.update_portfolio(
                {
                    'account_balance': snapshot.account_balance,
                    'total_equity': snapshot.total_equity,
                    'portfolio_heat': snapshot.portfolio_heat,
                    'open_positions': len(snapshot.open_positions),
                    'daily_pnl': snapshot.daily_pnl,
                    'current_drawdown': snapshot.current_drawdown,
                    'circuit_breaker_active': self.circuit_breaker_active
                }
            )
            
            plog.debug(
                "Synced portfolio state with StateManager",
                agent="risk_agent",
                phase="state_sync"
            )
            
        except Exception as e:
            plog.warning(
                f"Failed to sync with StateManager: {e}",
                agent="risk_agent",
                phase="state_sync"
            )
    
    async def get_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive risk summary"""
        snapshot = await self.get_current_snapshot()
        
        return {
            'timestamp': snapshot.timestamp.isoformat(),
            'total_equity': round(snapshot.total_equity, 2),
            'account_balance': round(snapshot.account_balance, 2),
            'unrealized_pnl': round(snapshot.total_unrealized_pnl, 2),
            'open_positions': len(snapshot.open_positions),
            'total_risk': round(snapshot.total_risk_amount, 2),
            'portfolio_heat': round(snapshot.portfolio_heat * 100, 2),
            'daily_pnl': round(snapshot.daily_pnl, 2),
            'daily_pnl_percentage': round(
                (snapshot.daily_pnl / self.daily_start_equity * 100), 2
            ) if self.daily_start_equity > 0 else 0,
            'current_drawdown': round(snapshot.current_drawdown * 100, 2),
            'drawdown_dollars': round(snapshot.current_drawdown_dollars, 2),
            'win_streak': snapshot.win_streak,
            'loss_streak': snapshot.loss_streak,
            'circuit_breaker_active': self.circuit_breaker_active,
            'circuit_breaker_reason': self.circuit_breaker_reason
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary"""
        return {
            'initial_balance': self.initial_balance,
            'account_balance': round(self.account_balance, 2),
            'peak_equity': round(self.peak_equity, 2),
            'daily_start_equity': round(self.daily_start_equity, 2),
            'daily_trades': self.daily_trades,
            'daily_wins': self.daily_wins,
            'daily_losses': self.daily_losses,
            'win_streak': self.win_streak,
            'loss_streak': self.loss_streak,
            'total_positions': len(self.positions),
            'circuit_breaker_active': self.circuit_breaker_active
        }
