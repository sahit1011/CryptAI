"""
Unit tests for Data Collection Agent
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.agents.data_agent import DataCollectionAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

@pytest.fixture
def mock_message_bus():
    bus = AsyncMock(spec=MessageBus)
    return bus

@pytest.fixture
def mock_state_manager():
    manager = AsyncMock(spec=StateManager)
    return manager

@pytest.fixture
def data_agent(mock_message_bus, mock_state_manager):
    agent = DataCollectionAgent(mock_message_bus, mock_state_manager)
    return agent

@pytest.mark.asyncio
async def test_agent_initialization(data_agent):
    """Test agent initializes correctly"""
    assert data_agent.name == "data_agent"
    assert data_agent.state == "IDLE"
    assert data_agent.candle_buffers is not None

@pytest.mark.asyncio
async def test_kline_update_processing(data_agent):
    """Test processing of kline updates"""
    kline_data = {
        's': 'BTCUSDT',
        'k': {
            't': 1699999999000,
            'i': '5m',
            'o': '43000',
            'h': '43100',
            'l': '42900',
            'c': '43050',
            'v': '100',
            'x': True  # Closed candle
        }
    }

    await data_agent._on_kline_update(kline_data)

    # Check if candle was added to buffer
    assert 'BTCUSDT' in data_agent.candle_buffers
    assert '5m' in data_agent.candle_buffers['BTCUSDT']
    assert len(data_agent.candle_buffers['BTCUSDT']['5m']) == 1

@pytest.mark.asyncio
async def test_order_book_update(data_agent):
    """Test order book depth processing"""
    depth_data = {
        's': 'BTCUSDT',
        'E': 1699999999000,
        'b': [['43000', '1.5'], ['42999', '2.0']],
        'a': [['43001', '1.2'], ['43002', '1.8']]
    }

    await data_agent._on_depth_update(depth_data)

    assert 'BTCUSDT' in data_agent.order_book_data
    assert data_agent.order_book_data['BTCUSDT']['best_bid'] == 43000
    assert data_agent.order_book_data['BTCUSDT']['best_ask'] == 43001

@pytest.mark.asyncio
async def test_funding_rate_update(data_agent, mock_state_manager):
    """Test funding rate update processing"""
    funding_data = {
        's': 'BTCUSDT',
        'r': '0.0001'
    }

    await data_agent._on_funding_update(funding_data)

    # Verify state manager was called
    mock_state_manager.set.assert_called_once()
    call_args = mock_state_manager.set.call_args
    assert call_args[0][0] == "funding_rate:BTCUSDT"
    assert 'rate' in call_args[0][1]
    assert call_args[0][1]['rate'] == 0.0001

@pytest.mark.asyncio
async def test_message_handling(data_agent, mock_message_bus):
    """Test message handling"""
    message = AgentMessage(
        id="123",
        sender="test",
        receiver="data_agent",
        type="fetch_data",
        payload={'symbol': 'BTCUSDT', 'timeframes': ['5m']}
    )

    # Setup some data
    data_agent.candle_buffers['BTCUSDT'] = {
        '5m': [{'close': 43000}]
    }

    result = await data_agent.process_message(message)

    assert result['status'] == 'success'
    assert 'data' in result

@pytest.mark.asyncio
async def test_historical_data_request(data_agent):
    """Test historical data request handling"""
    payload = {
        'symbol': 'BTC/USDT',
        'timeframes': ['1h'],
        'lookback_days': 7
    }

    # Mock the historical fetcher
    with patch.object(data_agent.historical_fetcher, 'fetch_multi_timeframe') as mock_fetch:
        mock_df = MagicMock()
        mock_df.to_dict.return_value = [{'timestamp': datetime.now(timezone.utc), 'close': 43000}]
        mock_fetch.return_value = {'1h': mock_df}

        message = AgentMessage(
            id="456",
            sender="test",
            receiver="data_agent",
            type="get_historical",
            payload=payload
        )

        result = await data_agent.process_message(message)

        assert result['status'] == 'success'
        assert 'data' in result
        mock_fetch.assert_called_once_with(
            symbol='BTC/USDT',
            timeframes=['1h'],
            lookback_days=7
        )

@pytest.mark.asyncio
async def test_invalid_symbol_request(data_agent):
    """Test request for untracked symbol"""
    message = AgentMessage(
        id="789",
        sender="test",
        receiver="data_agent",
        type="fetch_data",
        payload={'symbol': 'INVALID'}
    )

    result = await data_agent.process_message(message)

    assert result['status'] == 'error'
    assert 'Symbol INVALID not tracked' in result['message']

@pytest.mark.asyncio
async def test_unknown_message_type(data_agent):
    """Test handling of unknown message types"""
    message = AgentMessage(
        id="999",
        sender="test",
        receiver="data_agent",
        type="unknown_type",
        payload={}
    )

    result = await data_agent.process_message(message)

    assert result['status'] == 'no_handler'

@pytest.mark.asyncio
async def test_publish_market_data(data_agent, mock_message_bus, mock_state_manager):
    """Test market data publishing"""
    # Setup test data for only BTCUSDT
    data_agent.config.trading.symbols = ["BTCUSDT"]
    data_agent.candle_buffers['BTCUSDT'] = {
        '5m': [{'close': 43000}]
    }
    data_agent.order_book_data['BTCUSDT'] = {'best_bid': 42999}

    # Mock state manager get
    mock_state_manager.get.return_value = {'rate': 0.0001}

    await data_agent._publish_market_data()

    # Verify message was sent
    mock_message_bus.publish.assert_called()
    call_args = mock_message_bus.publish.call_args
    assert call_args[0][0] == "analysis_agent_inbox"
    published_data = call_args[0][1]
    assert published_data['type'] == "market_data_update"
    assert published_data['payload']['symbol'] == "BTCUSDT"

@pytest.mark.asyncio
async def test_buffer_size_limit(data_agent):
    """Test candle buffer size limiting"""
    # Add 501 candles to test limit
    for i in range(501):
        kline_data = {
            's': 'BTCUSDT',
            'k': {
                't': 1699999999000 + i * 300000,  # 5min intervals
                'i': '5m',
                'o': str(43000 + i),
                'h': str(43100 + i),
                'l': str(42900 + i),
                'c': str(43050 + i),
                'v': '100',
                'x': True
            }
        }
        await data_agent._on_kline_update(kline_data)

    # Should only keep last 500
    assert len(data_agent.candle_buffers['BTCUSDT']['5m']) == 500