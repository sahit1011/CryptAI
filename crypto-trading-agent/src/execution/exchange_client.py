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

from src.execution.error_handler import (
    ErrorClassifier,
    NetworkException,
    ExchangeException,
)


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
        *,
        reduce_only: bool = False,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place market order.

        Unified order interface implemented by both the live exchange client and
        the paper-trading engine (a contract test enforces signature parity).
        reduce_only/position_side/client_order_id are keyword-only so existing
        positional callers keep working.
        """
        pass

    @abstractmethod
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
        *,
        reduce_only: bool = True,
        position_side: str = "BOTH",
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
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol"""
        pass

    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        *,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ) -> Order:
        """Close (reduce-only) an open position with a market order.

        `side` is the closing side (SELL to close a LONG, BUY to close a SHORT).
        """
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
    
    @staticmethod
    def _format_symbol(symbol: str) -> str:
        """Normalize a symbol to BingX swap format (e.g. BTC-USDT).

        Upstream uses 'BTCUSDT' / 'BTC/USDT'; BingX perpetual-swap endpoints expect
        a hyphenated 'BASE-QUOTE'. Validate on BingX VST testnet before live use.
        """
        if not symbol:
            return symbol
        if '-' in symbol:
            return symbol
        s = symbol.replace('/', '')
        for quote in ('USDT', 'USDC', 'USD'):
            if s.endswith(quote) and len(s) > len(quote):
                return f"{s[:-len(quote)]}-{quote}"
        return symbol

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True
    ) -> Dict[str, Any]:
        """Make an authenticated BingX request.

        BingX computes the HMAC signature over the sorted query string and expects
        the signed parameters in the QUERY STRING for every method (including POST
        and DELETE). The previous implementation sent POST/DELETE params as a JSON
        body, so the body never matched the query-string signature and every live
        order was rejected with a signature error. We now always pass params as the
        query string and append the signature last (it must not itself be signed).
        Transient transport/rate-limit failures are raised as typed, retryable
        exceptions so RetryHandler can act on them.
        """

        await self._ensure_session()
        self._check_rate_limit()

        if params is None:
            params = {}

        if signed:
            # recvWindow guards against timestamp drift rejections.
            params.setdefault('recvWindow', 5000)
            params['timestamp'] = int(time.time() * 1000)
            # Signature is computed over all params and appended last (never signed).
            params['signature'] = self._sign_request(params)

        headers = {'X-BX-APIKEY': self.api_key}
        url = f"{self.base_url}{endpoint}"

        try:
            # Always send signed params in the query string so the transport matches
            # the signature, regardless of HTTP method.
            async with self.session.request(method, url, params=params, headers=headers) as response:
                text = await response.text()
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    raise ExchangeException(
                        f"BingX returned non-JSON (HTTP {response.status}): {text[:200]}"
                    )
                # HTTP-level errors -> classify (5xx/timeouts are retryable network errors)
                if response.status >= 500:
                    raise NetworkException(f"BingX HTTP {response.status}: {text[:200]}")
                if response.status == 429:
                    raise ErrorClassifier.classify_error("rate limit", str(response.status))
                if response.status >= 400:
                    raise ErrorClassifier.classify_error(
                        f"{data.get('msg', text[:200])}", str(response.status)
                    )

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Connection resets / DNS / timeouts -> retryable network error.
            logger.error(f"BingX network error: {e}")
            raise NetworkException(f"BingX network error: {e}") from e

        # BingX application-level error (code != 0) -> classify by message/code so the
        # retry handler retries transient ones and fails fast on auth/param errors.
        code = data.get('code')
        if code not in (0, None):
            msg = data.get('msg', 'unknown error')
            logger.error(f"BingX API error (code={code}): {msg}")
            raise ErrorClassifier.classify_error(msg, str(code))

        return data.get('data', data)
    
    def _order_params(
        self,
        symbol: str,
        side: OrderSide,
        order_type: str,
        quantity: float,
        position_side: str,
        reduce_only: bool,
        client_order_id: Optional[str],
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build a BingX swap-v2 order parameter dict (shared by all order types).

        positionSide=BOTH is one-way mode (the default). reduceOnly is only honored
        by BingX in one-way mode; in hedge mode you close by the opposite
        positionSide instead. Validate the exact field semantics on VST testnet.
        """
        params: Dict[str, Any] = {
            'symbol': self._format_symbol(symbol),
            'side': 'BUY' if side == OrderSide.BUY else 'SELL',
            'positionSide': position_side,
            'type': order_type,
            'quantity': quantity,
        }
        if price is not None:
            params['price'] = price
            params['timeInForce'] = 'GTC'
        if stop_price is not None:
            params['stopPrice'] = stop_price
        # reduceOnly is only meaningful in one-way (BOTH) mode.
        if reduce_only and position_side == 'BOTH':
            params['reduceOnly'] = 'true'
        if client_order_id:
            params['clientOrderID'] = client_order_id
        return params

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        *,
        reduce_only: bool = False,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place market order on BingX"""

        params = self._order_params(
            symbol, side, 'MARKET', quantity, position_side, reduce_only, client_order_id
        )

        logger.info(f"Placing BingX market order: {side.value} {quantity} {symbol} (reduce_only={reduce_only})")

        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        order = self._parse_order(response)
        logger.info(f"Market order placed: {order.order_id}")
        return order

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
    ) -> Order:
        """Place limit order on BingX"""

        params = self._order_params(
            symbol, side, 'LIMIT', quantity, position_side, reduce_only, client_order_id, price=price
        )

        logger.info(f"Placing BingX limit order: {side.value} {quantity} {symbol} @ ${price} (reduce_only={reduce_only})")

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
        *,
        reduce_only: bool = True,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ) -> Order:
        """Place stop-loss (STOP_MARKET) order on BingX"""

        params = self._order_params(
            symbol, side, 'STOP_MARKET', quantity, position_side, reduce_only, client_order_id, stop_price=stop_price
        )

        logger.info(f"Placing BingX stop-loss: {side.value} {quantity} {symbol} @ ${stop_price}")

        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        order = self._parse_order(response)
        logger.info(f"Stop-loss order placed: {order.order_id}")
        return order

    async def close_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        *,
        position_side: str = "BOTH",
        client_order_id: Optional[str] = None
    ) -> Order:
        """Reduce-only market close of an open position."""
        params = self._order_params(
            symbol, side, 'MARKET', quantity, position_side, reduce_only=True, client_order_id=client_order_id
        )
        logger.warning(f"Closing BingX position (reduce-only): {side.value} {quantity} {symbol}")
        response = await self._request('POST', '/openApi/swap/v2/trade/order', params)
        order = self._parse_order(response)
        logger.info(f"Close order placed: {order.order_id}")
        return order

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order on BingX"""

        params = {
            'symbol': self._format_symbol(symbol),
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

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol on BingX."""
        params = {'symbol': self._format_symbol(symbol)}
        logger.warning(f"Cancelling all BingX orders for {symbol}")
        try:
            await self._request('DELETE', '/openApi/swap/v2/trade/allOpenOrders', params)
            logger.info(f"All orders cancelled for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders for {symbol}: {e}")
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

    async def cancel_all_orders(self, symbol: str) -> bool:
        raise NotImplementedError("CoinDCX client not yet implemented")

    async def close_position(
        self, symbol: str, side: OrderSide, quantity: float,
        *, position_side: str = "BOTH", client_order_id: Optional[str] = None
    ) -> Order:
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
