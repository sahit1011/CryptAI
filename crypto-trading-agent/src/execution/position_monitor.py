"""
Position Monitor
Real-time position tracking and risk monitoring
"""
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import asyncio


@dataclass
class MonitoredPosition:
    """Position being monitored"""
    position_id: str
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    quantity: float
    entry_price: float
    current_price: float
    
    # Risk levels
    stop_loss: float
    take_profit_levels: List[float]
    trailing_stop_distance: Optional[float] = None
    
    # P&L
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    
    # Status
    opened_at: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    # Alerts
    alerts_sent: List[str] = field(default_factory=list)
    
    def calculate_pnl(self, current_price: float):
        """Calculate current P&L"""
        self.current_price = current_price
        
        if self.side == 'LONG':
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
        
        if self.entry_price > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100
        
        self.last_update = datetime.now()
    
    def check_stop_loss(self) -> bool:
        """Check if stop-loss hit"""
        if self.side == 'LONG':
            return self.current_price <= self.stop_loss
        else:
            return self.current_price >= self.stop_loss
    
    def check_take_profit(self) -> Optional[float]:
        """Check if any take-profit hit"""
        for tp_price in self.take_profit_levels:
            if self.side == 'LONG' and self.current_price >= tp_price:
                return tp_price
            elif self.side == 'SHORT' and self.current_price <= tp_price:
                return tp_price
        return None
    
    def update_trailing_stop(self):
        """Update trailing stop if applicable"""
        if not self.trailing_stop_distance:
            return
        
        if self.side == 'LONG':
            new_stop = self.current_price - self.trailing_stop_distance
            if new_stop > self.stop_loss:
                logger.info(
                    f"Trailing stop updated: "
                    f"${self.stop_loss:.2f} -> ${new_stop:.2f}"
                )
                self.stop_loss = new_stop
        else:
            new_stop = self.current_price + self.trailing_stop_distance
            if new_stop < self.stop_loss:
                logger.info(
                    f"Trailing stop updated: "
                    f"${self.stop_loss:.2f} -> ${new_stop:.2f}"
                )
                self.stop_loss = new_stop
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'stop_loss': self.stop_loss,
            'take_profit_levels': self.take_profit_levels,
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'unrealized_pnl_pct': round(self.unrealized_pnl_pct, 2),
            'duration_minutes': (datetime.now() - self.opened_at).total_seconds() / 60,
            'last_update': self.last_update.isoformat()
        }


class PositionMonitor:
    """
    Real-time position monitoring
    
    Monitors:
    - P&L
    - Stop-loss triggers
    - Take-profit triggers
    - Trailing stops
    - Position alerts
    """
    
    def __init__(self, update_interval: float = 1.0):
        self.update_interval = update_interval
        
        # Monitored positions
        self.positions: Dict[str, MonitoredPosition] = {}
        
        # Callbacks
        self.on_stop_loss_callbacks: List[Callable] = []
        self.on_take_profit_callbacks: List[Callable] = []
        self.on_alert_callbacks: List[Callable] = []
        
        # State
        self.running = False
        
        logger.info(f"Position monitor initialized (update: {update_interval}s)")
    
    def add_position(
        self,
        position_id: str,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[float],
        trailing_stop_distance: Optional[float] = None
    ):
        """Add position to monitor"""
        
        position = MonitoredPosition(
            position_id=position_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            trailing_stop_distance=trailing_stop_distance
        )
        
        self.positions[position_id] = position
        
        logger.info(
            f"Monitoring position: {position_id} | "
            f"{side} {quantity} {symbol} @ ${entry_price}"
        )
    
    def remove_position(self, position_id: str):
        """Stop monitoring position"""
        if position_id in self.positions:
            del self.positions[position_id]
            logger.info(f"Stopped monitoring position: {position_id}")
    
    def update_price(self, symbol: str, price: float):
        """Update price for symbol"""
        for position in self.positions.values():
            if position.symbol == symbol:
                position.calculate_pnl(price)
                
                # Check trailing stop
                position.update_trailing_stop()
                
                # Check triggers
                asyncio.create_task(self._check_triggers(position))
    
    async def _check_triggers(self, position: MonitoredPosition):
        """Check stop-loss and take-profit triggers"""
        
        # Check stop-loss
        if position.check_stop_loss():
            alert = f"STOP-LOSS HIT: {position.symbol} @ ${position.current_price:.2f}"
            if alert not in position.alerts_sent:
                position.alerts_sent.append(alert)
                logger.warning(alert)
                
                for callback in self.on_stop_loss_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(position)
                        else:
                            callback(position)
                    except Exception as e:
                        logger.error(f"Stop-loss callback error: {e}")
        
        # Check take-profit
        tp_hit = position.check_take_profit()
        if tp_hit:
            alert = f"TAKE-PROFIT HIT: {position.symbol} @ ${tp_hit:.2f}"
            if alert not in position.alerts_sent:
                position.alerts_sent.append(alert)
                logger.info(alert)
                
                for callback in self.on_take_profit_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(position, tp_hit)
                        else:
                            callback(position, tp_hit)
                    except Exception as e:
                        logger.error(f"Take-profit callback error: {e}")
    
    def on_stop_loss(self, callback: Callable):
        """Register stop-loss callback"""
        self.on_stop_loss_callbacks.append(callback)
    
    def on_take_profit(self, callback: Callable):
        """Register take-profit callback"""
        self.on_take_profit_callbacks.append(callback)
    
    def get_positions(self) -> List[MonitoredPosition]:
        """Get all monitored positions"""
        return list(self.positions.values())
    
    def get_position(self, position_id: str) -> Optional[MonitoredPosition]:
        """Get specific position"""
        return self.positions.get(position_id)
    
    def get_total_pnl(self) -> float:
        """Get total unrealized P&L"""
        return sum(pos.unrealized_pnl for pos in self.positions.values())
