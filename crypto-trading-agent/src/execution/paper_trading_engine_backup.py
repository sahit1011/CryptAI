"""
Paper Trading Engine
Realistic simulation of BingX exchange order placement and execution
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import random
from loguru import logger

class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"

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
            "updateTime": int(datetime.now().timestamp() * 1000)
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
        message_bus: Optional[Any] = None
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_range = slippage_range
        self.enable_realistic_fills = enable_realistic_fills
        self.message_bus = message_bus
        
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
        """Publish update to message bus if available"""
        if self.message_bus:
            try:
                await self.message_bus.publish(channel, {
                    "type": update_type,
                    "payload": payload,
                    "timestamp": datetime.now().isoformat()
                })
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
