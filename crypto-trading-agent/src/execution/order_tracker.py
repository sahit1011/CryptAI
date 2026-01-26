"""
Order Status Tracker
Real-time order status monitoring via WebSocket and polling
"""
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import asyncio
import json

from src.execution.exchange_client import ExchangeClient, Order, OrderStatus


@dataclass
class OrderUpdate:
    """Order status update"""
    order_id: str
    symbol: str
    status: OrderStatus
    filled_quantity: float
    average_price: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'average_price': self.average_price,
            'timestamp': self.timestamp.isoformat()
        }


class OrderTracker:
    """
    Order Status Tracker
    
    Monitors order status via:
    - WebSocket for real-time updates (primary)
    - Polling as fallback
    
    Provides callbacks for order events
    """
    
    def __init__(
        self,
        exchange_client: ExchangeClient,
        polling_interval: int = 5,
        enable_websocket: bool = True
    ):
        self.exchange = exchange_client
        self.polling_interval = polling_interval
        self.enable_websocket = enable_websocket
        
        # Order tracking
        self.tracked_orders: Dict[str, Order] = {}
        self.order_updates: List[OrderUpdate] = []
        
        # Callbacks
        self.on_fill_callbacks: List[Callable] = []
        self.on_partial_fill_callbacks: List[Callable] = []
        self.on_cancel_callbacks: List[Callable] = []
        self.on_reject_callbacks: List[Callable] = []
        
        # WebSocket state
        self.ws_connected = False
        self.ws_task: Optional[asyncio.Task] = None
        
        # Polling state
        self.polling_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info(
            f"Order tracker initialized (websocket={enable_websocket}, "
            f"polling_interval={polling_interval}s)"
        )
    
    def track_order(self, order: Order):
        """Add order to tracking"""
        self.tracked_orders[order.order_id] = order
        logger.info(f"Tracking order: {order.order_id} ({order.symbol})")
    
    def untrack_order(self, order_id: str):
        """Remove order from tracking"""
        if order_id in self.tracked_orders:
            del self.tracked_orders[order_id]
            logger.info(f"Stopped tracking order: {order_id}")
    
    def register_on_fill(self, callback: Callable):
        """Register callback for order fills"""
        self.on_fill_callbacks.append(callback)
    
    def register_on_partial_fill(self, callback: Callable):
        """Register callback for partial fills"""
        self.on_partial_fill_callbacks.append(callback)
    
    def register_on_cancel(self, callback: Callable):
        """Register callback for order cancellations"""
        self.on_cancel_callbacks.append(callback)
    
    def register_on_reject(self, callback: Callable):
        """Register callback for order rejections"""
        self.on_reject_callbacks.append(callback)
    
    async def start(self):
        """Start order tracking"""
        if self.is_running:
            logger.warning("Order tracker already running")
            return
        
        self.is_running = True
        logger.info("Starting order tracker...")
        
        # Start WebSocket if enabled
        if self.enable_websocket:
            self.ws_task = asyncio.create_task(self._websocket_loop())
        
        # Start polling as fallback
        self.polling_task = asyncio.create_task(self._polling_loop())
        
        logger.info("Order tracker started")
    
    async def stop(self):
        """Stop order tracking"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Stopping order tracker...")
        
        # Cancel tasks
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Order tracker stopped")
    
    async def _websocket_loop(self):
        """WebSocket monitoring loop"""
        logger.info("WebSocket monitoring started")
        
        while self.is_running:
            try:
                # Note: Actual WebSocket implementation would connect to exchange
                # For now, this is a placeholder that falls back to polling
                logger.debug("WebSocket connection not implemented, using polling fallback")
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.ws_connected = False
                await asyncio.sleep(5)  # Reconnect delay
    
    async def _polling_loop(self):
        """Polling fallback loop"""
        logger.info("Polling monitoring started")
        
        while self.is_running:
            try:
                await self._poll_orders()
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(self.polling_interval)
    
    async def _poll_orders(self):
        """Poll order status for all tracked orders"""
        if not self.tracked_orders:
            return
        
        for order_id, old_order in list(self.tracked_orders.items()):
            try:
                # Get updated order status
                updated_order = await self.exchange.get_order_status(
                    symbol=old_order.symbol,
                    order_id=order_id
                )
                
                # Check for status changes
                if updated_order.status != old_order.status:
                    await self._handle_status_change(old_order, updated_order)
                
                # Check for fill changes
                if updated_order.filled_quantity != old_order.filled_quantity:
                    await self._handle_fill_change(old_order, updated_order)
                
                # Update tracked order
                self.tracked_orders[order_id] = updated_order
                
            except Exception as e:
                logger.error(f"Failed to poll order {order_id}: {e}")
    
    async def _handle_status_change(self, old_order: Order, new_order: Order):
        """Handle order status change"""
        logger.info(
            f"Order {new_order.order_id} status changed: "
            f"{old_order.status.value} -> {new_order.status.value}"
        )
        
        # Create update record
        update = OrderUpdate(
            order_id=new_order.order_id,
            symbol=new_order.symbol,
            status=new_order.status,
            filled_quantity=new_order.filled_quantity,
            average_price=new_order.average_price,
            timestamp=datetime.now()
        )
        self.order_updates.append(update)
        
        # Trigger callbacks
        if new_order.status == OrderStatus.FILLED:
            await self._trigger_callbacks(self.on_fill_callbacks, new_order)
            # Stop tracking filled orders
            self.untrack_order(new_order.order_id)
        
        elif new_order.status == OrderStatus.CANCELED:
            await self._trigger_callbacks(self.on_cancel_callbacks, new_order)
            self.untrack_order(new_order.order_id)
        
        elif new_order.status == OrderStatus.REJECTED:
            await self._trigger_callbacks(self.on_reject_callbacks, new_order)
            self.untrack_order(new_order.order_id)
    
    async def _handle_fill_change(self, old_order: Order, new_order: Order):
        """Handle order fill quantity change"""
        if new_order.status == OrderStatus.PARTIALLY_FILLED:
            logger.info(
                f"Order {new_order.order_id} partially filled: "
                f"{new_order.filled_quantity}/{new_order.quantity} "
                f"@ ${new_order.average_price}"
            )
            await self._trigger_callbacks(self.on_partial_fill_callbacks, new_order)
    
    async def _trigger_callbacks(self, callbacks: List[Callable], order: Order):
        """Trigger registered callbacks"""
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.error(f"Callback error: {e}", exc_info=True)
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current order status from cache"""
        return self.tracked_orders.get(order_id)
    
    def get_tracked_orders(self) -> List[Order]:
        """Get all tracked orders"""
        return list(self.tracked_orders.values())
    
    def get_recent_updates(self, limit: int = 10) -> List[OrderUpdate]:
        """Get recent order updates"""
        return self.order_updates[-limit:]
