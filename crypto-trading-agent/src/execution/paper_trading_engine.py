"""
Paper Trading Engine
Realistic simulation of BingX exchange order placement and execution
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import os
import random
import json
from loguru import logger

class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"

#: Which order type closed a position -> the exit reason recorded in the ledger.
#: `trades.exit_reason` documents TP_HIT/SL_HIT/MANUAL/INVALIDATED; a reduce-only
#: MARKET fill is a deliberate close (user click, monitor time-stop, admin sweep),
#: which is MANUAL — never a take-profit that happened to be green.
_EXIT_REASON_BY_ORDER_TYPE = {
    "STOP_MARKET": "SL_HIT",
    "STOP_LIMIT": "SL_HIT",
    "TAKE_PROFIT": "TP_HIT",
    "TAKE_PROFIT_MARKET": "TP_HIT",
    "LIMIT": "TP_HIT",       # resting reduce-only limit == a take-profit leg
    "MARKET": "MANUAL",
}


def _exit_reason_for(order) -> str:
    """The OBSERVED exit reason for the order that closed a position.

    Unknown order types return "UNKNOWN" rather than a plausible guess: an honest
    gap in the ledger can be found and fixed, a fabricated label cannot.
    """
    raw = getattr(getattr(order, "type", None), "value", None) or str(getattr(order, "type", ""))
    return _EXIT_REASON_BY_ORDER_TYPE.get(str(raw).upper(), "UNKNOWN")


class OrderSide(Enum):
    """Order sides"""
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    """Order statuses"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class PaperOrder:
    """Simulated order matching BingX format"""
    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Status tracking
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: Optional[float] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    
    # Execution details
    commission: float = 0.0
    commission_asset: str = "USDT"
    
    # Metadata
    client_order_id: Optional[str] = None
    reduce_only: bool = False
    time_in_force: str = "GTC"  # Good Till Cancel
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to BingX-like response format"""
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.type.value,
            "origQty": str(self.quantity),
            "price": str(self.price) if self.price else "0",
            "stopPrice": str(self.stop_price) if self.stop_price else "0",
            "executedQty": str(self.filled_quantity),
            "avgPrice": str(self.filled_price) if self.filled_price else "0",
            "status": self.status.value,
            "timeInForce": self.time_in_force,
            "reduceOnly": self.reduce_only,
            "closePosition": False,
            "updateTime": int(self.updated_at.timestamp() * 1000),
            "workingType": "CONTRACT_PRICE",
            "priceProtect": False,
            "clientOrderId": self.client_order_id or ""
        }

@dataclass
class PaperPosition:
    """Simulated position"""
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    current_price: float
    leverage: int = 1
    position_id: Optional[str] = None  # Link to trade_id
    
    # P&L tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    # Risk management
    stop_loss: Optional[float] = None
    take_profit_levels: List[float] = field(default_factory=list)
    
    # Metadata
    position_id: str = ""
    opened_at: datetime = field(default_factory=datetime.now)
    
    def update_pnl(self, current_price: float):
        """Update unrealized P&L"""
        self.current_price = current_price
        if self.side == "LONG":
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to BingX-like position format"""
        return {
            "position_id": self.position_id,  # CRITICAL FIX: Include unique position ID
            "symbol": self.symbol,
            "positionSide": self.side,
            "positionAmt": str(self.quantity),
            "entryPrice": str(self.entry_price),
            "markPrice": str(self.current_price),
            "unRealizedProfit": str(round(self.unrealized_pnl, 2)),
            "liquidationPrice": "0",
            "leverage": str(self.leverage),
            "maxNotionalValue": "0",
            "marginType": "cross",
            "isolatedMargin": "0",
            "isAutoAddMargin": "false",
            "positionInitialMargin": str(round(self.entry_price * self.quantity / self.leverage, 2)),
            "updateTime": int(datetime.now().timestamp() * 1000),
            "stopLoss": str(self.stop_loss) if self.stop_loss else None,
            "takeProfit": str(self.take_profit_levels[0]) if self.take_profit_levels else None
        }


class PaperTradingEngine:
    """
    Realistic paper trading engine that mimics BingX exchange behavior
    
    Features:
    - Realistic order fills with slippage
    - Market impact simulation
    - Commission fees (0.04% maker, 0.06% taker)
    - Position tracking
    - Stop-loss and take-profit triggers
    - Order book depth simulation
    - Real-time event publishing to MessageBus
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        maker_fee: float = 0.0004,  # 0.04%
        taker_fee: float = 0.0006,  # 0.06%
        slippage_range: Tuple[float, float] = (0.0001, 0.0005),  # 0.01% - 0.05%
        enable_realistic_fills: bool = True,
        message_bus: Optional[Any] = None,
        state_manager: Optional[Any] = None,  # CRITICAL FIX: Add StateManager
        leverage: int = 10,  # Default leverage
        user_id: Optional[str] = None,  # owning tenant (multi-user); falls back to env
    ):
        # Owning tenant: published updates + persisted state are namespaced to this user
        # so multiple per-user engines never share state. Falls back to BOT_USER_ID for
        # the single-bot deployment.
        self.user_id = user_id or os.getenv("BOT_USER_ID")
        # Async hook fired when a position fully closes (position_id, symbol, exit_price,
        # pnl, reason). UserSession points this at its PortfolioStateTracker so per-user
        # risk limits (heat, daily loss, trade count) see real closes.
        self.on_position_closed: Optional[Any] = None
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_range = slippage_range
        self.enable_realistic_fills = enable_realistic_fills
        self.message_bus = message_bus
        self.state_manager = state_manager  # CRITICAL FIX: Store StateManager reference
        self.leverage = leverage
        
        # Order and position tracking
        self.orders: Dict[str, PaperOrder] = {}
        self.positions: Dict[str, PaperPosition] = {}
        self.order_counter = 0
        
        # Current market prices (updated externally)
        self.current_prices: Dict[str, float] = {}
        
        # Performance tracking
        self.trade_history: List[Dict[str, Any]] = []
        self.peak_balance = initial_balance
        self.max_drawdown = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.total_commission = 0.0
        
        logger.info(f"Paper Trading Engine initialized with ${initial_balance:,.2f}")
    
    async def _publish_update(self, channel: str, update_type: str, payload: dict):
        """Publish update to message bus if available.

        Stamps the owning tenant (BOT_USER_ID) so the API can route this update only to
        that user's WebSocket connections. In single-bot mode BOT_USER_ID identifies the
        operator's account; unset means an untenanted broadcast (dev / global).
        """
        if self.message_bus:
            try:
                message = {
                    "type": update_type,
                    "payload": payload,
                    "timestamp": datetime.now().isoformat(),
                }
                bot_user_id = self.user_id
                if bot_user_id:
                    message["user_id"] = bot_user_id
                await self.message_bus.publish(channel, message)
            except Exception as e:
                logger.error(f"Failed to publish update: {e}")
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        self.order_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PT_{timestamp}_{self.order_counter:04d}"
    
    def _calculate_slippage(self, order_type: OrderType, side: OrderSide) -> float:
        """Calculate realistic slippage"""
        if not self.enable_realistic_fills:
            return 0.0
        
        # Market orders have more slippage
        if order_type == OrderType.MARKET:
            base_slippage = random.uniform(self.slippage_range[0] * 2, self.slippage_range[1] * 2)
        else:
            base_slippage = random.uniform(self.slippage_range[0], self.slippage_range[1])
        
        # Slippage direction depends on side
        return base_slippage if side == OrderSide.BUY else -base_slippage
    
    def _calculate_commission(self, quantity: float, price: float, is_maker: bool) -> float:
        """Calculate trading commission"""
        notional_value = quantity * price
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        return notional_value * fee_rate
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a paper trading order (mimics BingX API)
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: BUY or SELL
            order_type: Order type
            quantity: Order quantity
            price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            reduce_only: Reduce-only flag
            client_order_id: Client order ID
            
        Returns:
            Order response (BingX format)
        """
        # Normalize the side to THIS module's enum. Callers (OrderManager, the
        # API's manual-execution path) pass exchange_client.OrderSide — a
        # DIFFERENT Enum class whose members NEVER compare equal to ours, so
        # `order.side == OrderSide.BUY` was always False and every BUY entry
        # silently booked as a SHORT position. Coerce by value once here; all
        # downstream comparisons are then same-class and correct.
        if not isinstance(side, OrderSide):
            side = OrderSide(str(getattr(side, "value", side)).upper())

        order_id = self._generate_order_id()

        # Create order
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id
        )
        
        # Validate order
        if order_type == OrderType.LIMIT and price is None:
            order.status = OrderStatus.REJECTED
            logger.error(f"LIMIT order requires price")
            return order.to_dict()
        
        if order_type in [OrderType.STOP_MARKET, OrderType.STOP_LIMIT] and stop_price is None:
            order.status = OrderStatus.REJECTED
            logger.error(f"STOP order requires stop_price")
            return order.to_dict()
        
        # Check balance for new positions
        if not reduce_only:
            # Calculate required margin using leverage
            notional_value = quantity * (price or self.current_prices.get(symbol, 0))
            required_margin = notional_value / self.leverage
            
            if required_margin > self.balance:
                order.status = OrderStatus.REJECTED
                logger.error(f"Insufficient balance: ${self.balance:.2f} < ${required_margin:.2f} (Margin for ${notional_value:.2f} @ {self.leverage}x)")
                return order.to_dict()
        
        # Store order
        self.orders[order_id] = order
        order.status = OrderStatus.OPEN
        
        # Market orders fill immediately
        if order_type == OrderType.MARKET:
            await self._fill_market_order(order)
        
        logger.info(
            f"Order placed: {order_id} | {side.value} {quantity} {symbol} "
            f"@ {price or 'MARKET'} | Status: {order.status.value}"
        )
        
        return order.to_dict()
    
    async def _fill_market_order(self, order: PaperOrder):
        """Fill market order immediately with slippage"""
        current_price = self.current_prices.get(order.symbol, 0)
        if current_price == 0:
            logger.error(f"No price data for {order.symbol}")
            order.status = OrderStatus.REJECTED
            return
        
        # Apply slippage
        slippage = self._calculate_slippage(OrderType.MARKET, order.side)
        fill_price = current_price * (1 + slippage)
        
        # Calculate commission (taker fee for market orders)
        commission = self._calculate_commission(order.quantity, fill_price, is_maker=False)
        
        # Fill order
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.commission = commission
        
        # Update balance
        self.balance -= commission
        self.total_commission += commission
        
        # Create or update position
        await self._update_position(order)
        
        logger.info(
            f"Market order filled: {order.order_id} | "
            f"Price: ${fill_price:.2f} | Slippage: {slippage*100:.3f}% | "
            f"Commission: ${commission:.2f}"
        )
    
    async def check_limit_orders(self, symbol: str, current_price: float):
        """Check if any limit orders should be filled"""
        self.current_prices[symbol] = current_price
        
        for order_id, order in list(self.orders.items()):
            if order.symbol != symbol or order.status != OrderStatus.OPEN:
                continue
            
            if order.type == OrderType.LIMIT:
                # Check if price reached
                should_fill = False
                if order.side == OrderSide.BUY and current_price <= order.price:
                    should_fill = True
                elif order.side == OrderSide.SELL and current_price >= order.price:
                    should_fill = True
                
                if should_fill:
                    await self._fill_limit_order(order, current_price)
            
            elif order.type in [OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET]:
                # Check if stop price triggered
                should_trigger = False
                if order.side == OrderSide.BUY and current_price >= order.stop_price:
                    should_trigger = True
                elif order.side == OrderSide.SELL and current_price <= order.stop_price:
                    should_trigger = True
                
                if should_trigger:
                    await self._fill_stop_order(order, current_price)
    
    async def _fill_limit_order(self, order: PaperOrder, current_price: float):
        """Fill limit order"""
        # Limit orders get filled at limit price (or better)
        fill_price = order.price
        
        # Small chance of price improvement
        if random.random() < 0.1:  # 10% chance
            improvement = random.uniform(0, 0.0002)  # Up to 0.02%
            if order.side == OrderSide.BUY:
                fill_price *= (1 - improvement)
            else:
                fill_price *= (1 + improvement)
        
        # Calculate commission (maker fee for limit orders)
        commission = self._calculate_commission(order.quantity, fill_price, is_maker=True)
        
        # Fill order
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.commission = commission
        
        # Update balance
        self.balance -= commission
        self.total_commission += commission
        
        # Create or update position
        await self._update_position(order)
        
        logger.info(
            f"Limit order filled: {order.order_id} | "
            f"Price: ${fill_price:.2f} | Commission: ${commission:.2f}"
        )
    
    async def _fill_stop_order(self, order: PaperOrder, current_price: float):
        """Fill stop order (converts to market order)"""
        # Stop orders become market orders when triggered
        slippage = self._calculate_slippage(OrderType.MARKET, order.side)
        fill_price = current_price * (1 + slippage)
        
        # Calculate commission (taker fee)
        commission = self._calculate_commission(order.quantity, fill_price, is_maker=False)
        
        # Fill order
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()
        order.commission = commission
        
        # Update balance
        self.balance -= commission
        self.total_commission += commission
        
        # Create or update position
        await self._update_position(order)
        
        logger.info(
            f"Stop order triggered and filled: {order.order_id} | "
            f"Trigger: ${order.stop_price:.2f} | Fill: ${fill_price:.2f} | "
            f"Commission: ${commission:.2f}"
        )
    
    async def _update_position(self, order: PaperOrder):
        """Create or update position based on filled order"""
        symbol = order.symbol
        
        if symbol not in self.positions:
            # New position
            if order.reduce_only:
                logger.warning(f"Reduce-only order but no position exists for {symbol}")
                return
            
            side = "LONG" if order.side == OrderSide.BUY else "SHORT"
            position = PaperPosition(
                symbol=symbol,
                side=side,
                quantity=order.filled_quantity,
                entry_price=order.filled_price,
                current_price=order.filled_price,
                position_id=f"POS_{order.order_id}",
                leverage=self.leverage
            )
            self.positions[symbol] = position
            logger.info(f"Position opened: {side} {order.filled_quantity} {symbol} @ ${order.filled_price:.2f}")
        
        else:
            # Modify existing position
            position = self.positions[symbol]
            
            if order.reduce_only or (
                (position.side == "LONG" and order.side == OrderSide.SELL) or
                (position.side == "SHORT" and order.side == OrderSide.BUY)
            ):
                # Closing position (partial or full)
                close_quantity = min(order.filled_quantity, position.quantity)
                
                # Calculate realized P&L
                if position.side == "LONG":
                    pnl = (order.filled_price - position.entry_price) * close_quantity
                else:
                    pnl = (position.entry_price - order.filled_price) * close_quantity
                
                position.realized_pnl += pnl
                position.quantity -= close_quantity
                self.balance += pnl
                
                # Track performance
                self.total_trades += 1
                if pnl > 0:
                    self.winning_trades += 1
                
                # Update peak and drawdown
                if self.balance > self.peak_balance:
                    self.peak_balance = self.balance
                current_drawdown = (self.peak_balance - self.balance) / self.peak_balance
                if current_drawdown > self.max_drawdown:
                    self.max_drawdown = current_drawdown
                
                logger.info(
                    f"Position reduced: {symbol} | Closed: {close_quantity} | "
                    f"P&L: ${pnl:+.2f} | Remaining: {position.quantity}"
                )
                
                # Remove position if fully closed
                if position.quantity <= 0.001:  # Account for floating point
                    del self.positions[symbol]
                    logger.info(f"Position closed: {symbol} | Total P&L: ${position.realized_pnl:+.2f}")

                    # THE EXIT REASON IS OBSERVED, NOT INFERRED FROM P&L.
                    # This used to be `"TP_HIT" if pnl > 0 else "SL_HIT"`, which is a
                    # fabrication: a stop that fills above entry (gap, trailing stop)
                    # was logged as a take-profit, and a TP filled at a loss as a stop.
                    # Every outcome-attribution query in the evidence plan reads this
                    # column, so a guess here poisons the calibration ledger (honesty
                    # law). The filling ORDER knows the truth — use it.
                    exit_reason = _exit_reason_for(order)
                    if self.on_position_closed is not None:
                        try:
                            await self.on_position_closed(
                                position_id=position.position_id,
                                symbol=symbol,
                                exit_price=order.filled_price,
                                pnl=position.realized_pnl,
                                reason=exit_reason.lower(),
                            )
                        except Exception as e:
                            logger.warning(f"on_position_closed hook failed for {symbol}: {e}")

                    # CRITICAL FIX: Notify Memory Agent to update DB with exit details
                    if self.message_bus:
                        # Extract trade ID from position ID (POS_PT_...) -> PT_...
                        trade_id = position.position_id.replace("POS_", "")
                        
                        await self.message_bus.publish(
                            "memory_agent_inbox",
                            {
                                "id": f"update_{trade_id}",
                                "correlation_id": f"update_{trade_id}",
                                "sender": "paper_trading_engine",
                                "receiver": "memory_agent",
                                "type": "update_trade",
                                "payload": {
                                    "trade_id": trade_id,
                                    "exit_price": order.filled_price,
                                    "exit_time": datetime.now().isoformat(),
                                    "exit_reason": exit_reason,  # observed, see above
                                    "notes": f"Closed via {order.type.value}"
                                },
                                "timestamp": datetime.now().isoformat()
                            }
                        )
                        logger.info(f"💾 Sent update_trade to Memory Agent for {trade_id}")
        
        # CRITICAL FIX: Publish portfolio update immediately to reflect changes in frontend
        await self.publish_portfolio_update()
    
    async def update_positions(self, symbol: str, current_price: float):
        """Update position P&L with current price"""
        self.current_prices[symbol] = current_price
        
        if symbol in self.positions:
            position = self.positions[symbol]
            position.update_pnl(current_price)
            
            # Check stop-loss and take-profit
            await self._check_position_exits(position, current_price)
    
    async def _check_position_exits(self, position: PaperPosition, current_price: float):
        """Check if position should be exited (SL/TP)"""
        # Check stop-loss
        if position.stop_loss:
            hit_sl = False
            if position.side == "LONG" and current_price <= position.stop_loss:
                hit_sl = True
            elif position.side == "SHORT" and current_price >= position.stop_loss:
                hit_sl = True
            
            if hit_sl:
                logger.warning(f"Stop-loss triggered for {position.symbol} @ ${current_price:.2f}")
                # Place market order to close
                side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
                await self.place_order(
                    symbol=position.symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                    reduce_only=True
                )
        
        # Check take-profit levels
        for tp_price in position.take_profit_levels:
            hit_tp = False
            if position.side == "LONG" and current_price >= tp_price:
                hit_tp = True
            elif position.side == "SHORT" and current_price <= tp_price:
                hit_tp = True
            
            if hit_tp:
                logger.info(f"Take-profit triggered for {position.symbol} @ ${current_price:.2f}")
                # This would typically trigger partial close
                # For now, we'll let the execution agent handle this
    
    def get_balance(self) -> float:
        """Get current balance"""
        return self.balance
    
    def get_total_equity(self) -> float:
        """Get total equity (balance + unrealized P&L)"""
        total_unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
        return self.balance + total_unrealized
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions (BingX format)"""
        return [pos.to_dict() for pos in self.positions.values()]
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders (BingX format)"""
        return [
            order.to_dict() 
            for order in self.orders.values() 
            if order.status == OrderStatus.OPEN
        ]
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get specific order"""
        order = self.orders.get(order_id)
        return order.to_dict() if order else None
    
    async def cancel_order(self, symbol: str, order_id: Optional[str] = None) -> Dict[str, Any]:
        """Cancel an open order.

        Unified interface is cancel_order(symbol, order_id); for backward
        compatibility, cancel_order(order_id) (single arg) is also accepted.
        """
        if order_id is None:
            order_id = symbol  # single-arg legacy call
        order = self.orders.get(order_id)
        if not order:
            return {"error": "Order not found"}

        if order.status != OrderStatus.OPEN:
            return {"error": f"Cannot cancel order with status {order.status.value}"}

        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now()

        logger.info(f"Order canceled: {order_id}")
        return order.to_dict()

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol (unified interface parity)."""
        cancelled = 0
        for oid, order in list(self.orders.items()):
            if order.status == OrderStatus.OPEN and getattr(order, 'symbol', None) in (symbol, symbol.replace('/', '')):
                order.status = OrderStatus.CANCELED
                order.updated_at = datetime.now()
                cancelled += 1
        logger.info(f"Cancelled {cancelled} open paper order(s) for {symbol}")
        return True

    async def close_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        *,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ):
        """Reduce-only market close of a paper position (unified interface parity)."""
        return await self.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            reduce_only=True,
            position_side=position_side,
            client_order_id=client_order_id,
        )


    def get_performance_summary(self) -> Dict[str, Any]:
        """Get trading performance summary"""
        total_equity = self.get_total_equity()
        total_pnl = total_equity - self.initial_balance
        total_pnl_pct = (total_pnl / self.initial_balance) * 100
        
        return {
            "initial_balance": round(self.initial_balance, 2),
            "current_balance": round(self.balance, 2),
            "total_equity": round(total_equity, 2),
            "unrealized_pnl": round(sum(pos.unrealized_pnl for pos in self.positions.values()), 2),
            "realized_pnl": round(total_pnl, 2),
            "realized_pnl_pct": round(total_pnl_pct, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": round(self.winning_trades / max(self.total_trades, 1) * 100, 1),
            "total_commission": round(self.total_commission, 2),
            "peak_balance": round(self.peak_balance, 2),
            "max_drawdown": round(self.max_drawdown * 100, 2),
            "open_positions": len(self.positions)
        }
    
    async def restore_from_historical_trades(self, database_url: str):
        """Legacy single-bot restore — now a thin delegate to src.core.rehydration.

        Kept for src/main.py, the standalone single-process entrypoint. The
        multi-user daemon does NOT call this: UserSession.rehydrate() runs the
        same core per tenant with a scoped query. This path stays UNSCOPED only
        when the engine has no user_id (true single-bot deployments, where all
        rows belong to the bot); with a user_id it scopes like everyone else.
        """
        try:
            from src.core.rehydration import load_trades, rehydrate_engine
            from src.memory.trade_history_manager import TradeHistoryManager

            logger.info("🔄 Restoring portfolio state from historical trades...")
            manager = TradeHistoryManager(database_url)
            open_rows, closed_rows = load_trades(
                manager, self.user_id, allow_unscoped=self.user_id is None
            )
            if not open_rows and not closed_rows:
                logger.info("✅ No historical trades found - starting with initial balance")
                return
            await rehydrate_engine(self, open_rows, closed_rows)
        except Exception as e:
            logger.warning(f"⚠️ Could not restore from historical trades: {e}")
            logger.info("Starting with initial balance")

    async def publish_initial_state(self):
        """
        Publish initial portfolio state immediately on startup.
        This ensures the frontend displays the initial capital right away.
        """
        if not self.message_bus:
            return
        
        perf = self.get_performance_summary()
        
        # Persist to StateManager per-tenant (namespaced by BOT_USER_ID).
        if self.state_manager:
            await self.state_manager.update_portfolio(perf, user_id=self.user_id)
            logger.info(f"💾 Persisted initial portfolio state to Redis")
        
        # Publish initial balance
        await self._publish_update("execution_status", "balance_update", {
            "initial_balance": perf["initial_balance"],
            "current_balance": perf["current_balance"],
            "total_equity": perf["total_equity"],
            "unrealized_pnl": perf["unrealized_pnl"],
            "realized_pnl": perf["realized_pnl"],
            "win_rate": perf["win_rate"],
            "total_trades": perf["total_trades"],
            "total_commission": perf["total_commission"],
            "max_drawdown": perf["max_drawdown"]
        })
        
        # Publish restored positions
        positions = self.get_positions()
        await self._publish_update("execution_status", "position_update", positions)
        
        # Persist positions to StateManager (per-tenant, atomic replace).
        if self.state_manager:
            for pos in positions:
                if 'unRealizedProfit' not in pos:
                    pos['unRealizedProfit'] = "0.00"
            await self.state_manager.replace_positions(positions, user_id=self.user_id)
            logger.info(f"💾 Persisted {len(positions)} restored positions to Redis")
        
        logger.info(f"📊 Published initial portfolio state: ${perf['total_equity']:,.2f}")
    
    async def publish_portfolio_update(self):
        """Publish portfolio update to frontend via message bus"""
        if not self.message_bus:
            return
        
        perf = self.get_performance_summary()
        positions = self.get_positions()
        
        # Persist to StateManager per-tenant (namespaced by BOT_USER_ID).
        if self.state_manager:
            uid = self.user_id
            await self.state_manager.update_portfolio(perf, user_id=uid)
            for pos in positions:
                if 'unRealizedProfit' not in pos:
                    pos['unRealizedProfit'] = "0.00"
            await self.state_manager.replace_positions(positions, user_id=uid)
            logger.debug(f"💾 Persisted portfolio state to Redis: ${perf['total_equity']:.2f}, {len(positions)} positions")
        
        # Publish balance update
        await self._publish_update("execution_status", "balance_update", {
            "initial_balance": perf["initial_balance"],
            "current_balance": perf["current_balance"],
            "total_equity": perf["total_equity"],
            "unrealized_pnl": perf["unrealized_pnl"],
            "realized_pnl": perf["realized_pnl"],
            "win_rate": perf["win_rate"],
            "total_trades": perf["total_trades"],
            "total_commission": perf["total_commission"],
            "max_drawdown": perf["max_drawdown"]
        })
        
        # Publish position update
        await self._publish_update("execution_status", "position_update", positions)

        # Open (resting) orders — a bracket's SL/TP legs. Persisted so the API can
        # list them cross-process, and pushed so the terminal's Orders tab is live.
        open_orders = self.get_open_orders()
        if self.state_manager:
            await self.state_manager.replace_orders(open_orders, user_id=self.user_id)
        await self._publish_update("execution_status", "open_orders", open_orders)

        logger.debug(
            f"Published portfolio update: ${perf['total_equity']:.2f} | "
            f"{len(positions)} positions | {len(open_orders)} open orders"
        )
    
    # ============================================================================
    # Exchange Client Interface Compatibility Methods
    # These methods make PaperTradingEngine compatible with OrderManager
    # ============================================================================
    
    def _rejected_market_order(self, symbol: str, side: OrderSide, quantity: float, client_order_id: Optional[str]):
        """An exchange-shaped REJECTED order — no live price, so nothing filled."""
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        return Order(
            order_id=self._generate_order_id(),
            client_order_id=client_order_id or "",
            symbol=symbol,
            side=side.value if hasattr(side, "value") else str(side),
            order_type="MARKET",
            price=None,
            quantity=quantity,
            status=ExchangeOrderStatus.REJECTED,
            filled_quantity=0.0,
            average_price=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        *,
        reduce_only: bool = False,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ):
        """Place market order (unified OrderManager interface — matches BingXClient)."""
        # CRITICAL FIX: Ensure current price is set before placing order
        if symbol not in self.current_prices or self.current_prices[symbol] == 0:
            # Try to get price from symbol (remove slash for internal format)
            symbol_clean = symbol.replace('/', '')
            
            # Try to fetch from StateManager if available
            price_found = False
            if self.state_manager:
                try:
                    # Try both formats
                    price = await self.state_manager.get_price(symbol)
                    if not price:
                        price = await self.state_manager.get_price(symbol_clean)
                    
                    if price and float(price) > 0:
                        self.current_prices[symbol] = float(price)
                        self.current_prices[symbol_clean] = float(price)
                        price_found = True
                        logger.info(f"Fetched live price for {symbol} from StateManager: ${price}")
                except Exception as e:
                    logger.warning(f"Failed to fetch price from StateManager: {e}")
            
            if not price_found and (symbol_clean not in self.current_prices or self.current_prices.get(symbol_clean, 0) == 0):
                # HARD FAILURE: never invent a price. A hardcoded fallback here
                # (previously $85,000 — a BTC-shaped number) filled paper orders at
                # fantasy levels: with the fill above the bracket's take-profits the
                # TP legs "filled" instantly and the netting flipped a LONG bracket
                # into a phantom SHORT. Same doctrine as the strategy agent's
                # price/ATR hard-gates: no live price -> honest rejection; the
                # caller sees exactly why nothing was booked.
                logger.error(
                    f"No live price for {symbol} (engine + StateManager empty) — "
                    f"rejecting market order instead of filling at a fabricated price"
                )
                return self._rejected_market_order(symbol, side, quantity, client_order_id)
        
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            reduce_only=reduce_only
        )

        # Convert to Order object for compatibility
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus

        return Order(
            order_id=result['orderId'],
            client_order_id=client_order_id or "",
            symbol=result['symbol'],
            side=result['side'],
            order_type=result['type'],
            quantity=float(result['origQty']),
            price=float(result['price']) if result['price'] != '0' else None,
            status=ExchangeOrderStatus.FILLED if result['status'] == 'FILLED' else ExchangeOrderStatus.NEW,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else 0.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        *,
        reduce_only: bool = False,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ):
        """Place limit order (unified OrderManager interface — matches BingXClient)."""
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            reduce_only=reduce_only
        )

        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus

        return Order(
            order_id=result['orderId'],
            client_order_id=client_order_id or "",
            symbol=result['symbol'],
            side=result['side'],
            order_type=result['type'],
            quantity=float(result['origQty']),
            price=float(result['price']),
            status=ExchangeOrderStatus.FILLED if result['status'] == 'FILLED' else ExchangeOrderStatus.NEW,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else 0.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        *,
        reduce_only: bool = True,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ):
        """Place stop-loss order (unified OrderManager interface — matches BingXClient)."""
        result = await self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=reduce_only
        )
        
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        return Order(
            order_id=result['orderId'],
            client_order_id=client_order_id or "",
            symbol=result['symbol'],
            side=result['side'],
            order_type=result['type'],
            quantity=float(result['origQty']),
            price=None,
            status=ExchangeOrderStatus.NEW,
            filled_quantity=float(result['executedQty']),
            average_price=float(result['avgPrice']) if result['avgPrice'] != '0' else 0.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    async def get_order_status(self, symbol: str, order_id: str):
        """Get order status (OrderManager interface)"""
        order_dict = self.get_order(order_id)
        if not order_dict:
            return None
        
        from src.execution.exchange_client import Order, OrderStatus as ExchangeOrderStatus
        
        status_map = {
            'PENDING': ExchangeOrderStatus.NEW,
            'OPEN': ExchangeOrderStatus.NEW,
            'FILLED': ExchangeOrderStatus.FILLED,
            'CANCELED': ExchangeOrderStatus.CANCELED,
            'REJECTED': ExchangeOrderStatus.REJECTED
        }
        
        return Order(
            order_id=order_dict['orderId'],
            client_order_id="",
            symbol=order_dict['symbol'],
            side=order_dict['side'],
            order_type=order_dict['type'],
            quantity=float(order_dict['origQty']),
            price=float(order_dict['price']) if order_dict['price'] != '0' else None,
            status=status_map.get(order_dict['status'], ExchangeOrderStatus.NEW),
            filled_quantity=float(order_dict['executedQty']),
        average_price=float(order_dict['avgPrice']) if order_dict['avgPrice'] != '0' else 0.0,
            created_at=datetime.fromtimestamp(order_dict['updateTime'] / 1000),
            updated_at=datetime.fromtimestamp(order_dict['updateTime'] / 1000)
        )

    async def close_all_positions(self, reason: str = "System Shutdown") -> Dict[str, Any]:
        """
        Close all open positions immediately.
        Used for emergency shutdown or system reset.
        
        Returns:
            Dict with success status, closed positions, failures, and total P&L
        """
        result = {
            'success': True,
            'closed_positions': [],
            'failed_positions': [],
            'total_realized_pnl': 0.0,
            'errors': []
        }
        
        positions_to_close = list(self.positions.values())
        
        if not positions_to_close:
            logger.info("No open positions to close.")
            return result
            
        logger.warning(f"🚨 Closing {len(positions_to_close)} positions due to: {reason}")
        
        # Initialize DB manager for persistence
        db_manager = None
        try:
            from src.utils.config import get_config
            from src.memory.trade_history_manager import TradeHistoryManager
            config = get_config()
            db_manager = TradeHistoryManager(config.database.postgres_url)
            logger.info("✅ Database manager initialized for shutdown")
        except Exception as e:
            logger.error(f"Failed to initialize DB manager for shutdown: {e}")
            result['errors'].append(f"DB init failed: {str(e)}")
        
        for position in positions_to_close:
            try:
                # Determine close side
                close_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
                
                # Place market close order
                logger.info(f"Closing {position.symbol} ({position.side}) position...")
                
                # Ensure we have a price
                if position.symbol not in self.current_prices:
                    # Use current price from position if available, otherwise fallback
                    self.current_prices[position.symbol] = position.current_price
                
                order_result = await self.place_order(
                    symbol=position.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                    reduce_only=True
                )
                
                if order_result['status'] == 'FILLED':
                    exit_price = float(order_result.get('avgPrice', 0))
                    
                    # Calculate P&L
                    if position.side == "LONG":
                        pnl = (exit_price - position.entry_price) * position.quantity
                    else:
                        pnl = (position.entry_price - exit_price) * position.quantity
                    
                    result['closed_positions'].append({
                        'symbol': position.symbol,
                        'side': position.side,
                        'pnl': pnl,
                        'exit_price': exit_price,
                        'position_id': position.position_id
                    })
                    result['total_realized_pnl'] += pnl
                    
                    logger.success(f"✅ Closed {position.symbol} at ${exit_price:.2f}, P&L: ${pnl:+.2f}")
                    
                    # CRITICAL FIX: Update database with exit details
                    if db_manager and position.position_id:
                        try:
                            # CRITICAL: Strip "POS_" prefix to get actual trade_id
                            # position_id format: "POS_PT_123456"
                            # trade_id format: "PT_123456"
                            trade_id = position.position_id.replace("POS_", "") if position.position_id.startswith("POS_") else position.position_id
                            
                            db_manager.update_trade_exit(
                                trade_id=trade_id,
                                exit_price=exit_price,
                                exit_time=datetime.now(),
                                exit_reason=reason,
                                notes=f"Force closed due to {reason}"
                            )
                            logger.info(f"💾 Updated trade {trade_id} in database")
                        except Exception as db_e:
                            logger.error(f"Failed to update DB for {position.position_id}: {db_e}")
                            result['errors'].append(f"DB update failed for {position.position_id}: {str(db_e)}")
                    
                else:
                    logger.error(f"❌ Failed to close {position.symbol}: {order_result}")
                    result['failed_positions'].append({
                        'symbol': position.symbol,
                        'error': f"Order status: {order_result.get('status')}"
                    })
                    result['success'] = False
                    
            except Exception as e:
                logger.error(f"Error closing position {position.symbol}: {e}")
                result['failed_positions'].append({
                    'symbol': position.symbol,
                    'error': str(e)
                })
                result['errors'].append(f"Error closing {position.symbol}: {str(e)}")
                result['success'] = False
        
        # CRITICAL FIX: Clear Redis positions after all closes
        if self.state_manager:
            try:
                await self.state_manager.replace_positions([], user_id=self.user_id)
                logger.info("💾 Cleared positions from Redis StateManager")
            except Exception as e:
                logger.error(f"Failed to clear Redis positions: {e}")
                result['errors'].append(f"Redis clear failed: {str(e)}")
        
        # CRITICAL FIX: Broadcast empty positions to frontend
        await self._publish_update("execution_status", "position_update", [])
        logger.info("📡 Broadcast empty positions to frontend")
        
        # Publish final portfolio update
        await self.publish_portfolio_update()
        
        logger.info(
            f"🏁 Shutdown complete: {len(result['closed_positions'])} closed, "
            f"{len(result['failed_positions'])} failed, "
            f"Total P&L: ${result['total_realized_pnl']:+.2f}"
        )
        
        return result


    