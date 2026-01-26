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

    def __init__(
        self,
        initial_balance: float = 10000.0,
        state_manager: Optional[Any] = None,
        snapshot_dir: Optional[str] = None
    ):
        self.initial_balance = initial_balance
        self.account_balance = initial_balance
        self.state_manager = state_manager

        # Active positions
        self.positions: Dict[str, Position] = {}

        # Performance tracking
        self.peak_equity = initial_balance
        self.daily_start_equity = initial_balance
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
                'pnl_percentage': round(
                    (final_pnl / position.risk_amount) * 100, 2
                ),
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

            return result

    async def get_current_snapshot(self) -> PortfolioSnapshot:
        """
        Get current portfolio snapshot with all metrics
        """
        async with self._lock:
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
                loss_streak=self.loss_streak
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
        """Reset daily statistics (call at start of each day)"""
        async with self._lock:
            snapshot = await self.get_current_snapshot()
            self.daily_start_equity = snapshot.total_equity
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
            
            # Calculate correlation risk score (0-1)
            snapshot = await self.get_current_snapshot()
            correlation_pct = total_exposure / snapshot.total_equity if snapshot.total_equity > 0 else 0
            
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
            
            plog.info(
                f"Loaded portfolio snapshot from {filepath}",
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
