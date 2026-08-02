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
import json
import os
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
        """Ensure aiohttp session exists.

        Bounded timeouts on EVERY exchange call: a hung order/balance request must fail
        fast and surface as a retryable error instead of blocking the execution pipeline
        indefinitely (orders were previously unbounded).
        """
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=float(os.getenv("EXCHANGE_HTTP_TIMEOUT", "15")),
                connect=float(os.getenv("EXCHANGE_CONNECT_TIMEOUT", "5")),
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
    
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
        """Sign a BingX request: HMAC-SHA256 over the sorted query string.

        The signature is computed over the parameters in SORTED key order. The caller
        MUST also transmit the parameters in that same sorted order (see _signed_query)
        so the string BingX reconstructs is byte-identical to the string we signed.
        """
        sorted_params = sorted(params.items())
        query_string = '&'.join(f"{k}={v}" for k, v in sorted_params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _signed_query(self, params: Dict[str, Any]) -> List[tuple]:
        """Return an ordered (key, value) list to transmit for a signed request.

        BingX verifies the signature against the query string it receives. We sign the
        canonical SORTED query string (via _sign_request) and then transmit the params
        in that SAME sorted order with the signature appended last, making the
        transmitted string byte-identical to the signed string.

        The previous implementation signed the sorted string but let the HTTP client
        transmit params in insertion order, so any request whose insertion order
        differed from sorted order (i.e. essentially every order) was rejected with a
        signature error.
        """
        signature = self._sign_request(params)
        return sorted(params.items()) + [('signature', signature)]
    
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

        request_params: Any = params
        if signed:
            # recvWindow guards against timestamp drift rejections.
            params.setdefault('recvWindow', 5000)
            params['timestamp'] = int(time.time() * 1000)
            # Build an ordered param list whose transmitted order == signed order.
            request_params = self._signed_query(params)

        headers = {'X-BX-APIKEY': self.api_key}
        url = f"{self.base_url}{endpoint}"

        try:
            # Always send signed params in the query string so the transport matches
            # the signature, regardless of HTTP method.
            async with self.session.request(method, url, params=request_params, headers=headers) as response:
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
            'symbol': self._format_symbol(symbol),
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

        # BingX swap-v2 returns a list of position dicts. Its field names differ from
        # Binance's /fapi positionRisk: BingX uses avgPrice (not entryPrice) and
        # unrealizedProfit (not unRealizedProfit), and carries an explicit positionSide
        # (LONG/SHORT/BOTH). Parsing Binance names raised KeyError on any real position.
        positions = []
        for pos_data in (response or []):
            amt = float(pos_data.get('positionAmt', 0) or 0)
            if amt == 0:
                continue
            position_side = str(pos_data.get('positionSide', '') or '').upper()
            if position_side in ('LONG', 'SHORT'):
                side = position_side
            else:  # one-way (BOTH) mode: derive direction from the signed amount
                side = 'LONG' if amt > 0 else 'SHORT'
            entry_price = pos_data.get('avgPrice', pos_data.get('entryPrice', 0))
            mark_price = pos_data.get('markPrice', 0)
            unrealized = pos_data.get('unrealizedProfit', pos_data.get('unRealizedProfit', 0))
            positions.append(Position(
                symbol=pos_data['symbol'],
                side=side,
                quantity=abs(amt),
                entry_price=float(entry_price or 0),
                mark_price=float(mark_price or 0),
                unrealized_pnl=float(unrealized or 0),
                leverage=int(float(pos_data.get('leverage', 1) or 1)),
            ))

        return positions

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Open (resting) orders from BingX, normalized to the shared BingX-like
        dict shape the paper engine also emits — so the API/UI render one format.
        """
        params: Dict[str, Any] = {}
        if symbol:
            params['symbol'] = self._format_symbol(symbol)
        response = await self._request('GET', '/openApi/swap/v2/trade/openOrders', params)
        # BingX wraps the list in an `orders` envelope inside `data` (already
        # unwrapped by _request); be liberal in what we accept.
        rows = response.get('orders') if isinstance(response, dict) else response
        orders: List[Dict[str, Any]] = []
        for row in (rows or []):
            if not isinstance(row, dict):
                continue
            orders.append({
                'orderId': str(row.get('orderId', '')),
                'clientOrderId': row.get('clientOrderID', row.get('clientOrderId', '')) or '',
                'symbol': row.get('symbol', ''),
                'side': row.get('side', ''),
                'type': row.get('type', ''),
                'origQty': str(row.get('origQty', row.get('quantity', '0'))),
                'price': str(row.get('price', '0')),
                'stopPrice': str(row.get('stopPrice', '0')),
                'status': row.get('status', 'NEW'),
                'reduceOnly': bool(row.get('reduceOnly', False)),
                'updateTime': int(row.get('updateTime', row.get('time', 0)) or 0),
            })
        return orders

    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse a BingX order response into an Order object.

        BingX wraps order payloads in a `data.order` envelope on both placement
        (POST .../trade/order) and query (GET .../trade/order). `_request` already
        unwraps the outer `data`, so here we unwrap the inner `order`. Without this
        every field read missed and order_id came back as the string 'None', so the
        system could never track, cancel, or reconcile a live order.
        """
        if isinstance(data, dict) and isinstance(data.get('order'), dict):
            data = data['order']

        order_id = data.get('orderId')
        # BingX returns clientOrderID/clientOrderId inconsistently across endpoints.
        client_order_id = data.get('clientOrderID', data.get('clientOrderId', '')) or ''

        def _f(*keys, default=0.0):
            for k in keys:
                v = data.get(k)
                if v not in (None, '', '0', 0):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return default

        raw_type = str(data.get('type', 'MARKET')).upper()
        raw_status = str(data.get('status', 'NEW')).upper()
        return Order(
            order_id=str(order_id) if order_id is not None else '',
            client_order_id=client_order_id,
            symbol=data.get('symbol'),
            side=OrderSide.BUY if str(data.get('side')).upper() == 'BUY' else OrderSide.SELL,
            order_type=OrderType[raw_type] if raw_type in OrderType.__members__ else OrderType.MARKET,
            price=(_f('price') or None),
            quantity=_f('origQty', 'quantity'),
            status=OrderStatus[raw_status] if raw_status in OrderStatus.__members__ else OrderStatus.NEW,
            filled_quantity=_f('executedQty'),
            average_price=_f('avgPrice'),
            created_at=datetime.fromtimestamp(int(data.get('time', 0) or 0) / 1000),
            updated_at=datetime.fromtimestamp(int(data.get('updateTime', 0) or 0) / 1000)
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


class DeltaExchangeClient(ExchangeClient):
    """Delta Exchange **India** perpetual-futures client (REST v2).

    Auth: HMAC-SHA256 over `method + timestamp + path + query + body`, sent as the
    `api-key` / `signature` / `timestamp` headers (a `User-Agent` is also required, and
    signatures expire ~5s after creation). Orders use an integer `product_id`, so we
    resolve and cache symbol -> product_id (and its contract size) from `/v2/products`.

    Base URLs:  production-india https://api.india.delta.exchange ·
                testnet-india   https://cdn-ind.testnet.deltaex.org

    NOTE: implemented to Delta's documented v2 API but PENDING live validation against a
    real Delta India testnet key (the exchange isn't reachable from the build network).
    """

    PROD_URL = "https://api.india.delta.exchange"
    TESTNET_URL = "https://cdn-ind.testnet.deltaex.org"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        super().__init__(api_key, api_secret, testnet)
        self.base_url = self.TESTNET_URL if testnet else self.PROD_URL
        self._product_cache: Dict[str, Dict[str, Any]] = {}  # symbol -> {id, contract_value}

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Signature over the Delta prehash string (method+timestamp+path+query+body)."""
        prehash = params["prehash"]
        return hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()

    async def _request(self, method: str, path: str, *, query: str = "", body: Optional[dict] = None,
                       auth: bool = True) -> Any:
        await self._ensure_session()
        self._check_rate_limit()
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = {"Content-Type": "application/json", "User-Agent": "cryptai-trading-agent"}
        if auth:
            ts = str(int(time.time()))
            prehash = method + ts + path + (("?" + query) if query else "") + body_str
            headers.update({
                "api-key": self.api_key,
                "timestamp": ts,
                "signature": self._sign_request({"prehash": prehash}),
            })
        url = self.base_url + path + (("?" + query) if query else "")
        try:
            async with self.session.request(method, url, data=body_str or None, headers=headers) as resp:
                data = await resp.json()
                if not data.get("success", True):
                    raise ExchangeException(f"Delta error: {data.get('error') or data}")
                return data.get("result", data)
        except aiohttp.ClientError as e:
            raise NetworkException(f"Delta request failed: {e}") from e

    async def _resolve_product(self, symbol: str) -> Dict[str, Any]:
        """Map a symbol (e.g. BTCUSDT/BTCUSD) to Delta's product_id + contract size."""
        if symbol in self._product_cache:
            return self._product_cache[symbol]
        products = await self._request("GET", "/v2/products", auth=False)
        candidates = {symbol, symbol.replace("USDT", "USD"), symbol.replace("USDT", "USDT")}
        for p in products or []:
            psym = p.get("symbol", "")
            if psym in candidates or psym == symbol:
                entry = {"id": p.get("id"), "contract_value": float(p.get("contract_value") or 1)}
                self._product_cache[symbol] = entry
                return entry
        raise ExchangeException(f"Delta: no product for symbol {symbol}")

    def _contracts(self, product: Dict[str, Any], quantity: float) -> int:
        """Base-asset quantity -> integer number of contracts (>=1)."""
        cv = product.get("contract_value") or 1
        return max(1, round(float(quantity) / float(cv)))

    async def _order(self, symbol: str, side: OrderSide, quantity: float, order_type: str,
                     *, price: Optional[float] = None, stop_price: Optional[float] = None,
                     reduce_only: bool = False, client_order_id: Optional[str] = None) -> Order:
        product = await self._resolve_product(symbol)
        body: Dict[str, Any] = {
            "product_id": product["id"],
            "size": self._contracts(product, quantity),
            "side": "buy" if side == OrderSide.BUY else "sell",
            "order_type": order_type,               # market_order | limit_order
            "reduce_only": reduce_only,
            "time_in_force": "gtc",
        }
        if price is not None:
            body["limit_price"] = str(price)
        if stop_price is not None:
            body["stop_order_type"] = "stop_loss_order"
            body["stop_price"] = str(stop_price)
        if client_order_id:
            body["client_order_id"] = client_order_id
        res = await self._request("POST", "/v2/orders", body=body)
        return self._to_order(res, symbol, side, order_type)

    @staticmethod
    def _map_state(res: dict) -> OrderStatus:
        """Map a Delta order 'state' + fill sizes onto our OrderStatus enum.

        Delta uses state ∈ {open, pending, closed, cancelled}. 'closed' means the order
        is no longer active — a full fill OR a fully cancelled/expired order — so
        disambiguate with filled_size. There is no PENDING member (referencing it was a
        hard crash on every non-filled order): a resting/unacknowledged order is NEW.
        """
        state = str(res.get("state") or "").lower()
        filled = float(res.get("filled_size", 0) or 0)
        size = float(res.get("size", 0) or 0)
        if state in ("cancelled", "canceled"):
            return OrderStatus.CANCELED
        if state == "closed":
            if size > 0 and filled >= size:
                return OrderStatus.FILLED
            if filled > 0:
                return OrderStatus.PARTIALLY_FILLED
            return OrderStatus.CANCELED
        if filled > 0 and size > 0 and filled < size:
            return OrderStatus.PARTIALLY_FILLED
        return OrderStatus.NEW

    def _to_order(self, res: dict, symbol: str, side: OrderSide, order_type: str) -> Order:
        now = datetime.now()
        return Order(
            order_id=str(res.get("id", "")),
            client_order_id=str(res.get("client_order_id") or ""),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET if "market" in order_type else OrderType.LIMIT,
            price=float(res["limit_price"]) if res.get("limit_price") else None,
            quantity=float(res.get("size", 0) or 0),
            status=self._map_state(res),
            filled_quantity=float(res.get("filled_size", 0) or 0),
            average_price=float(res.get("average_fill_price") or 0),
            created_at=now, updated_at=now,
        )

    async def place_market_order(self, symbol, side, quantity, *, reduce_only=False,
                                 position_side="BOTH", client_order_id=None) -> Order:
        return await self._order(symbol, side, quantity, "market_order",
                                 reduce_only=reduce_only, client_order_id=client_order_id)

    async def place_limit_order(self, symbol, side, quantity, price, *, reduce_only=False,
                                position_side="BOTH", client_order_id=None) -> Order:
        return await self._order(symbol, side, quantity, "limit_order", price=price,
                                 reduce_only=reduce_only, client_order_id=client_order_id)

    async def place_stop_loss_order(self, symbol, side, quantity, stop_price, *, reduce_only=True,
                                    position_side="BOTH", client_order_id=None) -> Order:
        return await self._order(symbol, side, quantity, "market_order", stop_price=stop_price,
                                 reduce_only=reduce_only, client_order_id=client_order_id)

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        product = await self._resolve_product(symbol)
        await self._request("DELETE", "/v2/orders", body={"id": int(order_id), "product_id": product["id"]})
        return True

    async def cancel_all_orders(self, symbol: str) -> bool:
        product = await self._resolve_product(symbol)
        await self._request("DELETE", "/v2/orders/all", body={"product_id": product["id"]})
        return True

    async def close_position(self, symbol, side, quantity, *, position_side="BOTH",
                             client_order_id=None) -> Order:
        return await self._order(symbol, side, quantity, "market_order", reduce_only=True,
                                 client_order_id=client_order_id)

    async def get_order_status(self, symbol: str, order_id: str) -> Order:
        res = await self._request("GET", f"/v2/orders/{order_id}")
        return self._to_order(res, symbol, OrderSide.BUY, res.get("order_type", "market_order"))

    async def get_account_balance(self) -> Dict[str, float]:
        res = await self._request("GET", "/v2/wallet/balances")
        total = sum(float(b.get("balance", 0) or 0) for b in (res or []))
        avail = sum(float(b.get("available_balance", 0) or 0) for b in (res or []))
        return {"balance": total, "available": avail, "equity": total}

    async def get_open_positions(self) -> List[Position]:
        res = await self._request("GET", "/v2/positions/margined")
        out: List[Position] = []
        for p in (res or []):
            size = float(p.get("size", 0) or 0)
            if size == 0:
                continue
            out.append(Position(
                symbol=(p.get("product_symbol") or p.get("symbol") or ""),
                side="LONG" if size > 0 else "SHORT",
                quantity=abs(size),
                entry_price=float(p.get("entry_price") or 0),
                mark_price=float(p.get("mark_price") or 0),
                unrealized_pnl=float(p.get("unrealized_pnl") or 0),
                leverage=int(float(p.get("leverage") or 1)),
            ))
        return out


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
            exchange_name: 'bingx', 'delta_india', or 'coindcx'
            api_key: API key
            api_secret: API secret
            testnet: Use testnet

        Returns:
            ExchangeClient instance
        """

        exchange_name = exchange_name.lower()

        if exchange_name == 'bingx':
            return BingXClient(api_key, api_secret, testnet)
        elif exchange_name in ('delta_india', 'delta'):
            return DeltaExchangeClient(api_key, api_secret, testnet)
        elif exchange_name == 'coindcx':
            return CoinDCXClient(api_key, api_secret, testnet)
        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
