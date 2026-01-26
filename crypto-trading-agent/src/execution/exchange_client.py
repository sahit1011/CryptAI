"""
Exchange API Client
Unified interface for BingX and CoinDCX exchanges
"""
from typing import Dict, Optional, Any, List
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod
import hmac
import hashlib
import time
from datetime import datetime
from loguru import logger
import aiohttp
import asyncio


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderSide(Enum):
    """Order sides"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    """Order representation"""
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float]
    quantity: float
    status: OrderStatus
    filled_quantity: float
    average_price: float
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'order_id': self.order_id,
            'client_order_id': self.client_order_id,
            'symbol': self.symbol,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'price': self.price,
            'quantity': self.quantity,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'average_price': self.average_price,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


@dataclass
class Position:
    """Position representation"""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'mark_price': self.mark_price,
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'leverage': self.leverage
        }


class ExchangeClient(ABC):
    """
    Abstract base class for exchange clients
    Provides unified interface across exchanges
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Rate limiting
        self.request_timestamps: List[float] = []
        self.max_requests_per_minute = 1200  # Conservative default
        
        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"{self.__class__.__name__} initialized (testnet={testnet})")
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the client session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _check_rate_limit(self):
        """Check and enforce rate limits"""
        now = time.time()
        
        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            ts for ts in self.request_timestamps
            if now - ts < 60
        ]
        
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            sleep_time = 60 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self.request_timestamps.append(now)
    
    @abstractmethod
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Sign API request (exchange-specific)"""
        pass
    
    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place market order"""
        pass
    
    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place limit order"""
        pass
    
    @abstractmethod
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place stop-loss order"""
        pass
    
    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: str
    ) -> bool:
        """Cancel order"""
        pass
    
    @abstractmethod
    async def get_order_status(
        self,
        symbol: str,
        order_id: str
    ) -> Order:
        """Get order status"""
        pass
    
    @abstractmethod
    async def get_account_balance(self) -> Dict[str, float]:
        """Get account balance"""
        pass
    
    @abstractmethod
    async def get_open_positions(self) -> List[Position]:
        """Get open positions"""
        pass


class BingXClient(ExchangeClient):
    """
    BingX Exchange API Client
    https://bingx-api.github.io/docs/
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        
        self.base_url = "https://open-api-vst.bingx.com" if testnet else \
                        "https://open-api.bingx.com"
        
        self.max_requests_per_minute = 1200
        
        logger.info(f"BingX client initialized: {self.base_url}")
    
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """
        Sign BingX API request
        
        BingX uses HMAC SHA256 signature
        """
        # Sort parameters
        sorted_params = sorted(params.items())
        query_string = '&'.join([f"{k}={v}" for k, v in sorted_params])
        
        # Generate signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True
    ) -> Dict[str, Any]:
        """Make authenticated API request"""
        
        await self._ensure_session()
        self._check_rate_limit()
        
        if params is None:
            params = {}
        
        # Add timestamp
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign_request(params)
        
        headers = {
            'X-BX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                async with self.session.get(url, params=params, headers=headers) as response:
                    data = await response.json()
            elif method == 'POST':
                async with self.session.post(url, json=params, headers=headers) as response:
                    data = await response.json()
            elif method == 'DELETE':
                async with self.session.delete(url, params=params, headers=headers) as response:
                    data = await response.json()
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check for errors
            if data.get('code') != 0:
                raise Exception(f"BingX API error: {data.get('msg')}")
            
            return data.get('data', data)
            
        except Exception as e:
            logger.error(f"BingX API request failed: {e}")
            raise
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place market order on BingX"""
        
        params = {
            'symbol': symbol,
            'side': 'BUY' if side == OrderSide.BUY else 'SELL',
            'type': 'MARKET',
            'quantity': quantity
        }
        
        if client_order_id:
            params['clientOrderId'] = client_order_id
        
        logger.info(f"Placing BingX market order: {side.value} {quantity} {symbol}")
        
        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        
        # Parse response into Order object
        order = self._parse_order(response)
        
        logger.info(f"Market order placed: {order.order_id}")
        
        return order
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place limit order on BingX"""
        
        params = {
            'symbol': symbol,
            'side': 'BUY' if side == OrderSide.BUY else 'SELL',
            'type': 'LIMIT',
            'quantity': quantity,
            'price': price,
            'timeInForce': 'GTC'
        }
        
        if client_order_id:
            params['clientOrderId'] = client_order_id
        
        logger.info(f"Placing BingX limit order: {side.value} {quantity} {symbol} @ ${price}")
        
        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        
        order = self._parse_order(response)
        
        logger.info(f"Limit order placed: {order.order_id}")
        
        return order
    
    async def place_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place stop-loss order on BingX"""
        
        params = {
            'symbol': symbol,
            'side': 'BUY' if side == OrderSide.BUY else 'SELL',
            'type': 'STOP_MARKET',
            'quantity': quantity,
            'stopPrice': stop_price
        }
        
        if client_order_id:
            params['clientOrderId'] = client_order_id
        
        logger.info(f"Placing BingX stop-loss: {side.value} {quantity} {symbol} @ ${stop_price}")
        
        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        
        order = self._parse_order(response)
        
        logger.info(f"Stop-loss order placed: {order.order_id}")
        
        return order
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order on BingX"""
        
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        logger.info(f"Canceling BingX order: {order_id}")
        
        try:
            await self._request('DELETE', '/openApi/swap/v2/trade/order', params)
            logger.info(f"Order canceled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def get_order_status(self, symbol: str, order_id: str) -> Order:
        """Get order status from BingX"""
        
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        
        response = await self._request('GET', '/openApi/swap/v2/trade/order', params)
        
        return self._parse_order(response)
    
    async def get_account_balance(self) -> Dict[str, float]:
        """Get account balance from BingX"""
        
        response = await self._request('GET', '/openApi/swap/v2/user/balance')
        
        balances = {}
        for asset in response.get('balance', []):
            balances[asset['asset']] = float(asset['balance'])
        
        return balances
    
    async def get_open_positions(self) -> List[Position]:
        """Get open positions from BingX"""
        
        response = await self._request('GET', '/openApi/swap/v2/user/positions')
        
        positions = []
        for pos_data in response:
            if float(pos_data.get('positionAmt', 0)) != 0:
                position = Position(
                    symbol=pos_data['symbol'],
                    side='LONG' if float(pos_data['positionAmt']) > 0 else 'SHORT',
                    quantity=abs(float(pos_data['positionAmt'])),
                    entry_price=float(pos_data['entryPrice']),
                    mark_price=float(pos_data['markPrice']),
                    unrealized_pnl=float(pos_data['unRealizedProfit']),
                    leverage=int(pos_data.get('leverage', 1))
                )
                positions.append(position)
        
        return positions
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse BingX order response into Order object"""
        
        return Order(
            order_id=str(data.get('orderId')),
            client_order_id=data.get('clientOrderId', ''),
            symbol=data.get('symbol'),
            side=OrderSide.BUY if data.get('side') == 'BUY' else OrderSide.SELL,
            order_type=OrderType[data.get('type', 'MARKET')],
            price=float(data.get('price', 0)) if data.get('price') else None,
            quantity=float(data.get('origQty', 0)),
            status=OrderStatus[data.get('status', 'NEW')],
            filled_quantity=float(data.get('executedQty', 0)),
            average_price=float(data.get('avgPrice', 0)),
            created_at=datetime.fromtimestamp(int(data.get('time', 0)) / 1000),
            updated_at=datetime.fromtimestamp(int(data.get('updateTime', 0)) / 1000)
        )


# CoinDCX client would follow similar pattern
class CoinDCXClient(ExchangeClient):
    """CoinDCX Exchange API Client (placeholder)"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        logger.info("CoinDCX client initialized")
    
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Sign CoinDCX API request"""
        # Placeholder implementation
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def place_market_order(
        self, symbol: str, side: OrderSide, quantity: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def place_limit_order(
        self, symbol: str, side: OrderSide, quantity: float, price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def place_stop_loss_order(
        self, symbol: str, side: OrderSide, quantity: float, stop_price: float,
        client_order_id: Optional[str] = None
    ) -> Order:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def get_order_status(self, symbol: str, order_id: str) -> Order:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def get_account_balance(self) -> Dict[str, float]:
        raise NotImplementedError("CoinDCX client not yet implemented")
    
    async def get_open_positions(self) -> List[Position]:
        raise NotImplementedError("CoinDCX client not yet implemented")


class ExchangeClientFactory:
    """Factory for creating exchange clients"""
    
    @staticmethod
    def create_client(
        exchange_name: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False
    ) -> ExchangeClient:
        """
        Create exchange client by name
        
        Args:
            exchange_name: 'bingx' or 'coindcx'
            api_key: API key
            api_secret: API secret
            testnet: Use testnet
            
        Returns:
            ExchangeClient instance
        """
        
        exchange_name = exchange_name.lower()
        
        if exchange_name == 'bingx':
            return BingXClient(api_key, api_secret, testnet)
        elif exchange_name == 'coindcx':
            return CoinDCXClient(api_key, api_secret, testnet)
        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
