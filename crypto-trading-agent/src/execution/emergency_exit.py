"""
Emergency Exit System
Handles panic closes and market-wide exits
"""
from typing import List, Optional
from loguru import logger
import asyncio

from src.execution.exchange_client import ExchangeClient, OrderSide, OrderType
from src.execution.position_monitor import PositionMonitor
from src.execution.order_tracker import OrderTracker


class EmergencyExit:
    """
    Emergency Exit System
    
    Provides mechanisms to:
    - Cancel all open orders
    - Close all open positions (Panic Close)
    - Halt all trading
    """
    
    def __init__(
        self,
        exchange: ExchangeClient,
        position_monitor: PositionMonitor,
        order_tracker: OrderTracker
    ):
        self.exchange = exchange
        self.position_monitor = position_monitor
        self.order_tracker = order_tracker
        
        logger.info("Emergency Exit System initialized")
    
    async def cancel_all_orders(self, symbol: Optional[str] = None):
        """
        Cancel all open orders
        
        Args:
            symbol: Optional symbol to filter
        """
        logger.warning(f"🚨 EMERGENCY: Cancelling all orders (Symbol: {symbol or 'ALL'})")
        
        try:
            # Exchange specific implementation might vary
            # BingX supports cancel all
            if symbol:
                await self.exchange.cancel_all_orders(symbol)
            else:
                # If exchange doesn't support global cancel, we need to list and cancel
                # For now, we assume we might need to iterate known symbols or use exchange feature
                # BingX V2 Swap supports cancel all by symbol.
                # To cancel ALL symbols, we'd need to know active symbols.
                # We can use order tracker to find active symbols.
                
                active_symbols = set(o.symbol for o in self.order_tracker.get_active_orders())
                
                tasks = []
                for sym in active_symbols:
                    tasks.append(self.exchange.cancel_all_orders(sym))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            raise
    
    async def panic_close_all(self):
        """
        🚨 PANIC CLOSE 🚨
        Close ALL positions immediately with market orders
        """
        logger.critical("🚨🚨🚨 PANIC CLOSE INITIATED 🚨🚨🚨")
        
        # 1. Cancel all open orders first to prevent new positions
        await self.cancel_all_orders()
        
        # 2. Get all open positions
        positions = self.position_monitor.get_positions()
        
        if not positions:
            logger.info("No open positions to close.")
            return
        
        # 3. Close each position
        tasks = []
        for position in positions:
            tasks.append(self._close_position(position))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. Report results
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"Panic close complete. Closed {success_count}/{len(positions)} positions.")
        
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"Failed to close position {positions[i].symbol}: {res}")
    
    async def _close_position(self, position):
        """Close a single position"""
        logger.warning(f"Closing position: {position.symbol} {position.quantity} {position.side}")
        
        # Determine close side
        close_side = OrderSide.SELL if position.side == 'LONG' else OrderSide.BUY
        
        # Place market order
        await self.exchange.place_order(
            symbol=position.symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            price=0, # Market order
            reduce_only=True
        )
