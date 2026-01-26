"""
Unit tests for Binance WebSocket Client
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.data.binance_client import BinanceWebSocketClient


@pytest.fixture
def ws_client():
    """Create BinanceWebSocketClient instance"""
    return BinanceWebSocketClient()


@pytest.mark.asyncio
async def test_client_initialization(ws_client):
    """Test client initializes correctly"""
    assert ws_client.ws is None
    assert ws_client.subscriptions == []
    assert ws_client.callbacks == {}
    assert ws_client.running == False
    assert ws_client.reconnect_attempts == 0
    assert ws_client.max_reconnect_attempts == 10


@pytest.mark.asyncio
async def test_subscribe_kline(ws_client):
    """Test kline subscription"""
    callback = AsyncMock()

    await ws_client.subscribe_kline(
        symbol="btcusdt",
        intervals=["5m", "15m"],
        callback=callback
    )

    assert "btcusdt@kline_5m" in ws_client.subscriptions
    assert "btcusdt@kline_15m" in ws_client.subscriptions
    assert "btcusdt@kline_5m" in ws_client.callbacks
    assert "btcusdt@kline_15m" in ws_client.callbacks
    assert callback in ws_client.callbacks["btcusdt@kline_5m"]
    assert callback in ws_client.callbacks["btcusdt@kline_15m"]


@pytest.mark.asyncio
async def test_subscribe_depth(ws_client):
    """Test depth subscription"""
    callback = AsyncMock()

    await ws_client.subscribe_depth(
        symbol="btcusdt",
        levels=20,
        update_speed="100ms",
        callback=callback
    )

    assert "btcusdt@depth20@100ms" in ws_client.subscriptions
    assert callback in ws_client.callbacks["btcusdt@depth20@100ms"]


@pytest.mark.asyncio
async def test_subscribe_funding_rate(ws_client):
    """Test funding rate subscription"""
    callback = AsyncMock()

    await ws_client.subscribe_funding_rate("btcusdt", callback)

    assert "btcusdt@markPrice@1s" in ws_client.subscriptions
    assert callback in ws_client.callbacks["btcusdt@markPrice@1s"]


@pytest.mark.asyncio
async def test_handle_event_kline(ws_client):
    """Test handling kline events"""
    callback = AsyncMock()

    # Setup subscription
    await ws_client.subscribe_kline("btcusdt", ["5m"], callback)

    # Mock kline data
    kline_data = {
        'e': 'kline',
        's': 'BTCUSDT',
        'k': {
            't': 1699999999000,
            'i': '5m',
            'o': '43000',
            'h': '43100',
            'l': '42900',
            'c': '43050',
            'v': '100',
            'x': True
        }
    }

    await ws_client._handle_event(kline_data)

    # Verify callback was called
    callback.assert_called_once_with(kline_data)


@pytest.mark.asyncio
async def test_handle_event_depth(ws_client):
    """Test handling depth events"""
    callback = AsyncMock()

    # Setup subscription
    await ws_client.subscribe_depth("btcusdt", callback=callback)

    # Mock depth data
    depth_data = {
        'e': 'depthUpdate',
        's': 'BTCUSDT',
        'E': 1699999999000,
        'b': [['43000', '1.5'], ['42999', '2.0']],
        'a': [['43001', '1.2'], ['43002', '1.8']]
    }

    await ws_client._handle_event(depth_data)

    # Verify callback was called
    callback.assert_called_once_with(depth_data)


@pytest.mark.asyncio
async def test_handle_event_funding_rate(ws_client):
    """Test handling funding rate events"""
    callback = AsyncMock()

    # Setup subscription
    await ws_client.subscribe_funding_rate("btcusdt", callback)

    # Mock funding rate data
    funding_data = {
        'e': 'markPriceUpdate',
        's': 'BTCUSDT',
        'r': '0.00010000'
    }

    await ws_client._handle_event(funding_data)

    # Verify callback was called
    callback.assert_called_once_with(funding_data)


@pytest.mark.asyncio
async def test_reconnect_logic(ws_client):
    """Test reconnection logic"""
    with patch('asyncio.sleep') as mock_sleep, \
         patch.object(ws_client, 'connect', new_callable=AsyncMock) as mock_connect, \
         patch.object(ws_client, 'disconnect', new_callable=AsyncMock) as mock_disconnect:

        # Set up initial state
        ws_client.reconnect_attempts = 0
        ws_client.running = True

        # Call reconnect handler
        await ws_client._handle_reconnect()

        # Verify disconnect was called
        mock_disconnect.assert_called_once()

        # Verify sleep was called with exponential backoff (2^1 = 2)
        mock_sleep.assert_called_once_with(2)

        # Verify connect was called
        mock_connect.assert_called_once()


@pytest.mark.asyncio
async def test_max_reconnect_attempts(ws_client):
    """Test max reconnection attempts"""
    with patch('asyncio.sleep') as mock_sleep, \
         patch.object(ws_client, 'disconnect', new_callable=AsyncMock) as mock_disconnect:

        # Set max attempts reached
        ws_client.reconnect_attempts = ws_client.max_reconnect_attempts
        ws_client.running = True

        await ws_client._handle_reconnect()

        # Verify running was set to False (disconnect not called in this case)
        assert ws_client.running == False

        # Verify sleep was not called (early return)
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_send_ping(ws_client):
    """Test ping functionality"""
    # Mock websocket
    mock_ws = AsyncMock()
    ws_client.ws = mock_ws

    await ws_client._send_ping()

    # Verify ping was called
    mock_ws.ping.assert_called_once()


@pytest.mark.asyncio
async def test_send_ping_error(ws_client):
    """Test ping error handling"""
    # Mock websocket that raises exception
    mock_ws = AsyncMock()
    mock_ws.ping.side_effect = Exception("Ping failed")
    ws_client.ws = mock_ws

    # Should not raise exception
    await ws_client._send_ping()

    # Verify ping was attempted
    mock_ws.ping.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_message_format(ws_client):
    """Test subscription message format"""
    # Mock websocket
    mock_ws = AsyncMock()
    ws_client.ws = mock_ws

    streams = ["btcusdt@kline_5m", "btcusdt@depth20@100ms"]

    await ws_client._subscribe(streams)

    # Verify send was called
    mock_ws.send.assert_called_once()

    # Get the sent message
    call_args = mock_ws.send.call_args[0][0]
    message = json.loads(call_args)

    # Verify message structure
    assert message['method'] == 'SUBSCRIBE'
    assert message['params'] == streams
    assert 'id' in message
    assert isinstance(message['id'], int)