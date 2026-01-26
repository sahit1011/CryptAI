"""
Order Placement System
Handles complex trade setups with multiple order types
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from loguru import logger
import uuid
import asyncio

from src.execution.exchange_client import (
    ExchangeClient, Order, OrderSide, OrderType, OrderStatus
)


class ExecutionStrategy(Enum):
    """Execution strategies"""
    IMMEDIATE = "immediate"  # Market order
    PATIENT = "patient"      # Limit order
    TWAP = "twap"           # Time-weighted average price


@dataclass
class TradeExecution:
    """Complete trade execution record"""
    execution_id: str
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    
    # Entry
    entry_order: Optional[Order] = None
    entry_filled: bool = False
    
    # Stop-loss
    stop_loss_order: Optional[Order] = None
    stop_loss_price: float = 0.0
    
    # Take-profits
    take_profit_orders: List[Order] = field(default_factory=list)
    take_profit_prices: List[float] = field(default_factory=list)
    take_profit_sizes: List[float] = field(default_factory=list)
    
    # Status
    status: str = "pending"  # pending, active, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    
    # Metadata
    strategy_type: str = ""
    confidence_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'execution_id': self.execution_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_order': self.entry_order.to_dict() if self.entry_order else None,
            'entry_filled': self.entry_filled,
            'stop_loss_order': self.stop_loss_order.to_dict() if self.stop_loss_order else None,
            'take_profit_orders': [tp.to_dict() for tp in self.take_profit_orders],
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }


class OrderManager:
    """
    Order Placement System
    
    Handles:
    - Multi-leg order execution
    - Order coordination
    - Execution strategies
    - Error recovery
    """
    
    def __init__(self, exchange_client: ExchangeClient):
        self.exchange = exchange_client
        
        # Tracking
        self.active_executions: Dict[str, TradeExecution] = {}
        self.completed_executions: List[TradeExecution] = []
        
        logger.info("Order manager initialized")
    
    async def execute_trade_setup(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_levels: List[Dict[str, float]],  # [{'price': 43500, 'size': 0.33}]
        total_quantity: float,
        strategy: ExecutionStrategy = ExecutionStrategy.IMMEDIATE,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TradeExecution:
        """
        Execute complete trade setup
        
        Args:
            symbol: Trading pair
            direction: 'LONG' or 'SHORT'
            entry_price: Entry price (for limit orders)
            stop_loss_price: Stop-loss trigger price
            take_profit_levels: List of TP targets with sizes
            total_quantity: Total position size
            strategy: Execution strategy
            metadata: Additional metadata
            
        Returns:
            TradeExecution record
        """
        execution_id = str(uuid.uuid4())
        
        logger.info(
            f"[OrderManager] Executing {direction} {symbol} setup | "
            f"Qty: {total_quantity} | Entry: ${entry_price} | SL: ${stop_loss_price}"
        )
        
        # Create execution record
        execution = TradeExecution(
            execution_id=execution_id,
            symbol=symbol,
            direction=direction,
            stop_loss_price=stop_loss_price,
            take_profit_prices=[tp['price'] for tp in take_profit_levels],
            take_profit_sizes=[tp['size'] for tp in take_profit_levels],
            strategy_type=metadata.get('strategy_type', '') if metadata else '',
            confidence_score=metadata.get('confidence_score', 0.0) if metadata else 0.0
        )
        
        self.active_executions[execution_id] = execution
        
        try:
            # Step 1: Place entry order
            entry_order = await self._place_entry_order(
                symbol=symbol,
                direction=direction,
                quantity=total_quantity,
                price=entry_price,
                strategy=strategy
            )
            
            execution.entry_order = entry_order
            
            # Step 2: Wait for entry fill (if limit order)
            if strategy == ExecutionStrategy.PATIENT:
                logger.info(f"⏳ Waiting for limit order to fill (timeout: 3600s / 1 hour)...")
                filled = await self._wait_for_fill(entry_order, timeout=3600)  # 1 hour timeout
                
                if not filled:
                    logger.warning(f"❌ Entry order not filled within timeout: {entry_order.order_id}")
                    logger.warning(f"Cancelling unfilled limit order...")
                    
                    # Cancel the unfilled order
                    try:
                        await self.exchange.cancel_order(symbol, entry_order.order_id)
                        logger.info(f"✅ Cancelled unfilled limit order: {entry_order.order_id}")
                    except Exception as e:
                        logger.error(f"Failed to cancel order {entry_order.order_id}: {e}")
                    
                    execution.status = "timeout"
                    return execution
            
            execution.entry_filled = True
            
            # Step 3: Place stop-loss order
            stop_loss_order = await self._place_stop_loss(
                symbol=symbol,
                direction=direction,
                quantity=total_quantity,
                stop_price=stop_loss_price
            )
            
            execution.stop_loss_order = stop_loss_order
            
            # Step 4: Place take-profit orders
            for tp_level in take_profit_levels:
                tp_order = await self._place_take_profit(
                    symbol=symbol,
                    direction=direction,
                    quantity=tp_level['size'],
                    price=tp_level['price']
                )
                execution.take_profit_orders.append(tp_order)
            
            execution.status = "active"
            
            logger.info(
                f"[OrderManager] ✅ Trade setup executed successfully | "
                f"Execution ID: {execution_id}"
            )
            
            return execution
            
        except Exception as e:
            logger.error(f"Trade execution failed: {e}", exc_info=True)
            execution.status = "failed"
            
            # Attempt rollback
            await self._rollback_execution(execution)
            
            return execution
    
    async def _place_entry_order(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        price: float,
        strategy: ExecutionStrategy
    ) -> Order:
        """Place entry order"""
        
        side = OrderSide.BUY if direction == 'LONG' else OrderSide.SELL
        
        if strategy == ExecutionStrategy.IMMEDIATE:
            # Market order
            order = await self.exchange.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity
            )
        else:
            # Limit order
            order = await self.exchange.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price
            )
        
        logger.info(f"Entry order placed: {order.order_id}")
        
        return order
    
    async def _place_stop_loss(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        stop_price: float
    ) -> Order:
        """Place stop-loss order"""
        
        # Opposite side of entry
        side = OrderSide.SELL if direction == 'LONG' else OrderSide.BUY
        
        order = await self.exchange.place_stop_loss_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            stop_price=stop_price
        )
        
        logger.info(f"Stop-loss order placed: {order.order_id} @ ${stop_price}")
        
        return order
    
    async def _place_take_profit(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        price: float
    ) -> Order:
        """Place take-profit limit order"""
        
        # Opposite side of entry
        side = OrderSide.SELL if direction == 'LONG' else OrderSide.BUY
        
        order = await self.exchange.place_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            reduce_only=True  # CRITICAL FIX: TP orders should close positions, not open new ones
        )
        
        logger.info(f"Take-profit order placed: {order.order_id} @ ${price}")
        
        return order
    
    async def _wait_for_fill(
        self,
        order: Order,
        timeout: int = 60,
        check_interval: int = 2
    ) -> bool:
        """Wait for order to fill"""
        
        elapsed = 0
        while elapsed < timeout:
            # Check order status
            updated_order = await self.exchange.get_order_status(
                symbol=order.symbol,
                order_id=order.order_id
            )
            
            if updated_order.status == OrderStatus.FILLED:
                logger.info(f"Order filled: {order.order_id}")
                return True
            elif updated_order.status in [OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                logger.warning(f"Order not filled: {order.order_id} - {updated_order.status.value}")
                return False
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
        
        logger.warning(f"Order fill timeout: {order.order_id}")
        return False
    
    async def _rollback_execution(self, execution: TradeExecution):
        """Rollback failed execution (cancel all orders)"""
        
        logger.warning(f"Rolling back execution: {execution.execution_id}")
        
        # Cancel entry order if not filled
        if execution.entry_order and not execution.entry_filled:
            try:
                await self.exchange.cancel_order(
                    symbol=execution.symbol,
                    order_id=execution.entry_order.order_id
                )
            except Exception as e:
                logger.error(f"Failed to cancel entry order: {e}")
        
        # Cancel stop-loss
        if execution.stop_loss_order:
            try:
                await self.exchange.cancel_order(
                    symbol=execution.symbol,
                    order_id=execution.stop_loss_order.order_id
                )
            except Exception as e:
                logger.error(f"Failed to cancel stop-loss: {e}")
        
        # Cancel take-profits
        for tp_order in execution.take_profit_orders:
            try:
                await self.exchange.cancel_order(
                    symbol=execution.symbol,
                    order_id=tp_order.order_id
                )
            except Exception as e:
                logger.error(f"Failed to cancel take-profit: {e}")
    
    async def on_take_profit_fill(
        self,
        execution_id: str,
        tp_order_id: str,
        filled_price: float
    ):
        """
        Handle take-profit fill
        - Move SL to breakeven if configured
        - Update execution status
        """
        execution = self.get_execution(execution_id)
        if not execution:
            logger.error(f"Execution not found: {execution_id}")
            return
        
        logger.info(f"Take-profit filled for {execution_id} @ ${filled_price}")
        
        # Move SL to breakeven after first TP
        # Check if this is the first TP fill (or if we should move SL)
        # For simplicity, we'll move SL to entry price after any TP fill
        # In a real system, we might have more complex logic (e.g. TP1 -> BE, TP2 -> TP1)
        
        if execution.stop_loss_order:
            current_sl_price = execution.stop_loss_price
            entry_price = execution.entry_order.average_price if execution.entry_order else 0
            
            # Only move if it improves the position
            should_move = False
            if execution.direction == 'LONG':
                if current_sl_price < entry_price:
                    should_move = True
            else:
                if current_sl_price > entry_price:
                    should_move = True
            
            if should_move:
                logger.info(f"Moving Stop-Loss to Breakeven: ${entry_price}")
                try:
                    await self.move_stop_loss(execution_id, entry_price)
                except Exception as e:
                    logger.error(f"Failed to move SL to breakeven: {e}")

    async def move_stop_loss(self, execution_id: str, new_price: float) -> Order:
        """
        Move stop-loss to new price
        
        Args:
            execution_id: Trade execution ID
            new_price: New stop price
            
        Returns:
            New stop-loss order
        """
        execution = self.get_execution(execution_id)
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")
        
        if not execution.stop_loss_order:
            raise ValueError("No active stop-loss order to move")
        
        old_sl_order = execution.stop_loss_order
        
        logger.info(
            f"Modifying Stop-Loss for {execution.symbol}: "
            f"${execution.stop_loss_price} -> ${new_price}"
        )
        
        # Cancel old SL
        try:
            await self.exchange.cancel_order(
                symbol=execution.symbol,
                order_id=old_sl_order.order_id
            )
        except Exception as e:
            logger.warning(f"Failed to cancel old SL (might be filled/cancelled): {e}")
        
        # Place new SL
        # Note: We need to know the remaining quantity. 
        # For simplicity, we use the original quantity or track it.
        # Ideally, we should track remaining position size.
        # Here we assume SL covers the entire remaining position.
        
        # TODO: Get actual remaining quantity from position monitor or tracker
        quantity = old_sl_order.quantity 
        
        new_sl_order = await self._place_stop_loss(
            symbol=execution.symbol,
            direction=execution.direction,
            quantity=quantity,
            stop_price=new_price
        )
        
        # Update execution record
        execution.stop_loss_order = new_sl_order
        execution.stop_loss_price = new_price
        
        return new_sl_order

    def get_execution(self, execution_id: str) -> Optional[TradeExecution]:
        """Get execution by ID"""
        return self.active_executions.get(execution_id)
    
    def get_active_executions(self) -> List[TradeExecution]:
        """Get all active executions"""
        return list(self.active_executions.values())
