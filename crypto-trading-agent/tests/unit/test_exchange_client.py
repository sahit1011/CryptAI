"""
Unit tests for Exchange Client
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.execution.exchange_client import (
    BingXClient, OrderSide, OrderType, OrderStatus,
    ExchangeClientFactory, Order
)


@pytest.fixture
def bingx_client():
    """Create BingX client for testing"""
    return BingXClient(
        api_key='test_key',
        api_secret='test_secret',
        testnet=True
    )


def test_client_initialization(bingx_client):
    """Test client initialization"""
    assert bingx_client.api_key == 'test_key'
    assert bingx_client.api_secret == 'test_secret'
    assert bingx_client.testnet is True
    assert bingx_client.base_url == "https://open-api-vst.bingx.com"


def test_signature_generation(bingx_client):
    """Test API signature generation"""
    params = {
        'symbol': 'BTCUSDT',
        'quantity': 0.1,
        'timestamp': 1234567890
    }
    
    signature = bingx_client._sign_request(params)
    
    assert signature is not None
    assert isinstance(signature, str)
    assert len(signature) == 64  # HMAC SHA256 is 64 chars hex


def test_rate_limiting(bingx_client):
    """Test rate limiting mechanism"""
    import time
    
    # Add many timestamps
    now = time.time()
    bingx_client.request_timestamps = [now - i for i in range(1200)]
    
    # This should trigger rate limiting
    start = time.time()
    bingx_client._check_rate_limit()
    elapsed = time.time() - start
    
    # Should have slept
    assert elapsed > 0


@pytest.mark.asyncio
async def test_place_market_order(bingx_client):
    """Test market order placement"""
    
    # Mock the _request method
    bingx_client._request = AsyncMock(return_value={
        'orderId': '12345',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'type': 'MARKET',
        'origQty': '0.1',
        'status': 'FILLED',
        'executedQty': '0.1',
        'avgPrice': '43000',
        'time': 1234567890000,
        'updateTime': 1234567890000
    })
    
    order = await bingx_client.place_market_order(
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        quantity=0.1
    )
    
    assert order.order_id == '12345'
    assert order.symbol == 'BTCUSDT'
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.quantity == 0.1


@pytest.mark.asyncio
async def test_place_limit_order(bingx_client):
    """Test limit order placement"""
    
    bingx_client._request = AsyncMock(return_value={
        'orderId': '12346',
        'symbol': 'BTCUSDT',
        'side': 'SELL',
        'type': 'LIMIT',
        'price': '44000',
        'origQty': '0.1',
        'status': 'NEW',
        'executedQty': '0',
        'avgPrice': '0',
        'time': 1234567890000,
        'updateTime': 1234567890000
    })
    
    order = await bingx_client.place_limit_order(
        symbol='BTCUSDT',
        side=OrderSide.SELL,
        quantity=0.1,
        price=44000.0
    )
    
    assert order.order_id == '12346'
    assert order.side == OrderSide.SELL
    assert order.order_type == OrderType.LIMIT
    assert order.price == 44000.0


@pytest.mark.asyncio
async def test_place_stop_loss_order(bingx_client):
    """Test stop-loss order placement"""
    
    bingx_client._request = AsyncMock(return_value={
        'orderId': '12347',
        'symbol': 'BTCUSDT',
        'side': 'SELL',
        'type': 'STOP_MARKET',
        'stopPrice': '42000',
        'origQty': '0.1',
        'status': 'NEW',
        'executedQty': '0',
        'avgPrice': '0',
        'time': 1234567890000,
        'updateTime': 1234567890000
    })
    
    order = await bingx_client.place_stop_loss_order(
        symbol='BTCUSDT',
        side=OrderSide.SELL,
        quantity=0.1,
        stop_price=42000.0
    )
    
    assert order.order_id == '12347'
    # The venue says STOP_MARKET; our canonical member is STOP_LOSS. It used to fall
    # through to OrderType.MARKET, which silently turned a stop-loss into an ordinary
    # market order — see _ORDER_TYPE_ALIASES in src/execution/exchange_client.py.
    assert order.order_type == OrderType.STOP_LOSS


@pytest.mark.asyncio
async def test_cancel_order(bingx_client):
    """Test order cancellation"""
    
    bingx_client._request = AsyncMock(return_value={'code': 0})
    
    result = await bingx_client.cancel_order(
        symbol='BTCUSDT',
        order_id='12345'
    )
    
    assert result is True


@pytest.mark.asyncio
async def test_get_order_status(bingx_client):
    """Test order status query"""
    
    bingx_client._request = AsyncMock(return_value={
        'orderId': '12345',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'type': 'MARKET',
        'origQty': '0.1',
        'status': 'FILLED',
        'executedQty': '0.1',
        'avgPrice': '43000',
        'time': 1234567890000,
        'updateTime': 1234567890000
    })
    
    order = await bingx_client.get_order_status(
        symbol='BTCUSDT',
        order_id='12345'
    )
    
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 0.1


@pytest.mark.asyncio
async def test_get_account_balance(bingx_client):
    """Test account balance retrieval"""
    
    bingx_client._request = AsyncMock(return_value={
        'balance': [
            {'asset': 'USDT', 'balance': '10000.00'},
            {'asset': 'BTC', 'balance': '0.5'}
        ]
    })
    
    balances = await bingx_client.get_account_balance()
    
    assert 'USDT' in balances
    assert balances['USDT'] == 10000.0
    assert balances['BTC'] == 0.5


@pytest.mark.asyncio
async def test_get_open_positions(bingx_client):
    """Test open positions retrieval"""
    
    bingx_client._request = AsyncMock(return_value=[
        {
            'symbol': 'BTCUSDT',
            'positionAmt': '0.1',
            'entryPrice': '43000',
            'markPrice': '43500',
            'unRealizedProfit': '50',
            'leverage': '10'
        }
    ])
    
    positions = await bingx_client.get_open_positions()
    
    assert len(positions) == 1
    assert positions[0].symbol == 'BTCUSDT'
    assert positions[0].side == 'LONG'
    assert positions[0].quantity == 0.1


def test_exchange_factory():
    """Test exchange client factory"""
    
    client = ExchangeClientFactory.create_client(
        exchange_name='bingx',
        api_key='test',
        api_secret='test',
        testnet=True
    )
    
    assert isinstance(client, BingXClient)


def test_exchange_factory_invalid():
    """Test factory with invalid exchange"""
    
    with pytest.raises(ValueError):
        ExchangeClientFactory.create_client(
            exchange_name='invalid',
            api_key='test',
            api_secret='test'
        )


@pytest.mark.asyncio
async def test_session_management(bingx_client):
    """Test session creation and cleanup"""
    
    await bingx_client._ensure_session()
    assert bingx_client.session is not None
    
    await bingx_client.close()
    assert bingx_client.session.closed


def test_venue_order_type_aliases_resolve_not_silently_downgrade():
    """A protective leg must never be parsed as a plain market order.

    Venues disagree on names for the same order (STOP_MARKET vs STOP_LOSS). The old
    parse downgraded every unknown spelling to MARKET, so a live stop-loss fill was
    recorded as an ordinary market order and exit attribution read "manual close"
    instead of "stopped out".
    """
    from src.execution.exchange_client import OrderType, parse_order_type

    assert parse_order_type("STOP_MARKET") == OrderType.STOP_LOSS
    assert parse_order_type("stop_market") == OrderType.STOP_LOSS
    assert parse_order_type("TAKE_PROFIT_MARKET") == OrderType.TAKE_PROFIT
    assert parse_order_type("STOP_LIMIT") == OrderType.STOP_LOSS_LIMIT
    # canonical members still work
    assert parse_order_type("LIMIT") == OrderType.LIMIT
    assert parse_order_type("STOP_LOSS") == OrderType.STOP_LOSS
    # genuinely unknown -> MARKET, but loudly (see the warning in parse_order_type)
    assert parse_order_type("SOMETHING_NEW") == OrderType.MARKET
    assert parse_order_type("") == OrderType.MARKET
