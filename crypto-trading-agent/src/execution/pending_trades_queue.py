"""
Pending Trades Queue Manager
Manages unfilled limit orders with confidence-based replacement logic
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class PendingTrade:
    """Represents a pending trade setup waiting for entry"""
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_levels: List[Dict[str, float]]
    position_size: float
    confidence_score: float  # 0.0 - 1.0
    
    # Order tracking
    limit_order_id: Optional[str] = None
    order_placed_at: Optional[datetime] = None
    
    # Strategy metadata
    strategy_type: str = ""
    market_regime: str = ""
    
    # Timeout
    timeout_seconds: int = 3600  # 1 hour default
    
    def is_expired(self) -> bool:
        """Check if pending trade has expired"""
        if not self.order_placed_at:
            return False
        elapsed = (datetime.now() - self.order_placed_at).total_seconds()
        return elapsed > self.timeout_seconds
    
    def time_remaining(self) -> int:
        """Get remaining time in seconds before timeout"""
        if not self.order_placed_at:
            return self.timeout_seconds
        elapsed = (datetime.now() - self.order_placed_at).total_seconds()
        return max(0, int(self.timeout_seconds - elapsed))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_levels': self.take_profit_levels,
            'position_size': self.position_size,
            'confidence_score': self.confidence_score,
            'limit_order_id': self.limit_order_id,
            'order_placed_at': self.order_placed_at.isoformat() if self.order_placed_at else None,
            'strategy_type': self.strategy_type,
            'market_regime': self.market_regime,
            'timeout_seconds': self.timeout_seconds,
            'time_remaining': self.time_remaining(),
            'is_expired': self.is_expired()
        }


class PendingTradesQueue:
    """
    Manages pending trade setups (unfilled limit orders)
    
    Key Features:
    - Only ONE pending trade per symbol at a time
    - Replace lower confidence setups with higher confidence ones
    - Automatic timeout and cleanup
    - Thread-safe operations
    
    Usage:
        queue = PendingTradesQueue()
        
        # Check if should replace existing pending trade
        if queue.should_replace("BTC-USDT", new_confidence=0.85):
            # Cancel old order and place new one
            queue.add_pending_trade(new_pending_trade)
    """
    
    def __init__(self):
        self.pending_trades: Dict[str, PendingTrade] = {}  # symbol -> PendingTrade
        logger.info("✅ Pending Trades Queue initialized")
    
    def has_pending_trade(self, symbol: str) -> bool:
        """Check if there's a pending trade for this symbol"""
        return symbol in self.pending_trades
    
    def get_pending_trade(self, symbol: str) -> Optional[PendingTrade]:
        """Get pending trade for symbol"""
        return self.pending_trades.get(symbol)
    
    def should_replace(self, symbol: str, new_confidence: float) -> bool:
        """
        Determine if new setup should replace existing pending trade
        
        Logic:
        - If no pending trade exists → Always accept (return True)
        - If existing trade has expired → Always replace (return True)
        - If new confidence > existing confidence → Replace (return True)
        - If new confidence <= existing confidence → Keep existing (return False)
        
        Args:
            symbol: Trading symbol
            new_confidence: Confidence score of new setup (0.0 - 1.0)
        
        Returns:
            True if new setup should replace existing, False otherwise
        """
        if not self.has_pending_trade(symbol):
            logger.debug(f"No pending trade for {symbol}, accepting new setup")
            return True
        
        existing = self.pending_trades[symbol]
        
        # Check if existing trade has expired
        if existing.is_expired():
            logger.info(
                f"⏰ Existing pending trade for {symbol} has expired "
                f"(age: {(datetime.now() - existing.order_placed_at).total_seconds():.0f}s), "
                f"will replace"
            )
            return True
        
        # Compare confidence scores
        if new_confidence > existing.confidence_score:
            logger.info(
                f"📈 New setup has higher confidence ({new_confidence:.3f} > {existing.confidence_score:.3f}), "
                f"will replace existing pending trade for {symbol}"
            )
            return True
        else:
            logger.info(
                f"📊 Existing setup has higher/equal confidence "
                f"({existing.confidence_score:.3f} >= {new_confidence:.3f}), "
                f"keeping existing pending trade for {symbol}"
            )
            return False
    
    def add_pending_trade(self, pending_trade: PendingTrade) -> bool:
        """
        Add pending trade to queue
        
        Note: This does NOT check if it should replace existing trade.
        Call should_replace() first to determine if you should add.
        
        Args:
            pending_trade: PendingTrade object to add
        
        Returns:
            True if added successfully
        """
        symbol = pending_trade.symbol
        
        # If replacing, log the change
        if self.has_pending_trade(symbol):
            old_trade = self.pending_trades[symbol]
            logger.info(
                f"🔄 Replacing pending trade for {symbol}: "
                f"Old [Entry=${old_trade.entry_price:.2f}, Conf={old_trade.confidence_score:.3f}] → "
                f"New [Entry=${pending_trade.entry_price:.2f}, Conf={pending_trade.confidence_score:.3f}]"
            )
        
        self.pending_trades[symbol] = pending_trade
        logger.info(
            f"✅ Added pending trade for {symbol} | "
            f"Entry: ${pending_trade.entry_price:.2f} | "
            f"Confidence: {pending_trade.confidence_score:.3f} | "
            f"Order ID: {pending_trade.limit_order_id}"
        )
        return True
    
    def remove_pending_trade(self, symbol: str) -> Optional[PendingTrade]:
        """
        Remove and return pending trade
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Removed PendingTrade object, or None if not found
        """
        removed = self.pending_trades.pop(symbol, None)
        if removed:
            logger.info(f"🗑️ Removed pending trade for {symbol}")
        return removed
    
    def cleanup_expired(self) -> List[PendingTrade]:
        """
        Remove expired pending trades and return them
        
        Returns:
            List of expired PendingTrade objects that were removed
        """
        expired = []
        for symbol, trade in list(self.pending_trades.items()):
            if trade.is_expired():
                age = (datetime.now() - trade.order_placed_at).total_seconds()
                logger.warning(
                    f"⏰ Pending trade for {symbol} has expired "
                    f"(age: {age:.0f}s, timeout: {trade.timeout_seconds}s), "
                    f"removing from queue"
                )
                expired.append(self.pending_trades.pop(symbol))
        
        if expired:
            logger.info(f"🧹 Cleaned up {len(expired)} expired pending trade(s)")
        
        return expired
    
    def get_all_pending(self) -> List[PendingTrade]:
        """Get all pending trades"""
        return list(self.pending_trades.values())
    
    def get_count(self) -> int:
        """Get number of pending trades"""
        return len(self.pending_trades)
    
    def clear(self):
        """Clear all pending trades (use with caution!)"""
        count = len(self.pending_trades)
        self.pending_trades.clear()
        logger.warning(f"🗑️ Cleared all {count} pending trade(s) from queue")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of pending trades queue"""
        pending = self.get_all_pending()
        return {
            'total_pending': len(pending),
            'symbols': [p.symbol for p in pending],
            'pending_trades': [p.to_dict() for p in pending]
        }
