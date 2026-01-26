"""
Unit tests for State Manager
"""
import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.state_manager import StateManager
from src.data.data_models import AgentState, Trade


@pytest.fixture
def state_manager():
    """State manager fixture with mocked Redis and PostgreSQL"""
    manager = StateManager()

    # Mock Redis
    manager.redis = AsyncMock()

    # Mock PostgreSQL session
    mock_session = AsyncMock()
    manager.async_session = MagicMock(return_value=mock_session)

    return manager


@pytest.mark.asyncio
async def test_connect_disconnect(state_manager):
    """Test connection management"""
    # Mock Redis connection
    state_manager.redis = None
    mock_redis = AsyncMock()
    with patch('src.core.state_manager.redis.from_url', return_value=mock_redis):
        await state_manager.connect()
        assert state_manager.redis == mock_redis

    await state_manager.disconnect()
    mock_redis.close.assert_called_once()


@pytest.mark.asyncio
async def test_hot_state_operations(state_manager):
    """Test Redis hot state operations"""
    # Test set/get
    await state_manager.set("test_key", {"data": "value"})
    state_manager.redis.set.assert_called_once()

    state_manager.redis.get.return_value = b'{"data": "value"}'
    result = await state_manager.get("test_key")
    assert result == {"data": "value"}

    # Test hash operations
    await state_manager.set_hash("portfolio", "balance", 10000)
    state_manager.redis.hset.assert_called_once()

    state_manager.redis.hget.return_value = b'10000'
    result = await state_manager.get_hash("portfolio", "balance")
    assert result == b'10000'


@pytest.mark.asyncio
async def test_portfolio_operations(state_manager):
    """Test portfolio state operations"""
    # Mock hash data
    state_manager.redis.hgetall.return_value = {
        b"balance": b'10000',
        b"equity": b'9500'
    }

    portfolio = await state_manager.get_portfolio_state()
    assert portfolio == {"balance": 10000, "equity": 9500}

    await state_manager.update_portfolio({"balance": 11000})
    state_manager.redis.hset.assert_called()


@pytest.mark.asyncio
async def test_position_operations(state_manager):
    """Test position operations"""
    positions_data = [
        {"id": "pos1", "symbol": "BTCUSDT", "size": 0.1},
        {"id": "pos2", "symbol": "ETHUSDT", "size": 0.5}
    ]

    # Mock Redis lrange
    state_manager.redis.lrange.return_value = [
        json.dumps(pos).encode() for pos in positions_data
    ]

    positions = await state_manager.get_positions()
    assert len(positions) == 2
    assert positions[0]["symbol"] == "BTCUSDT"

    # Test add position
    await state_manager.add_position({"id": "pos3", "symbol": "ADAUSDT"})
    state_manager.redis.lpush.assert_called_once()

    # Test remove position
    await state_manager.remove_position("pos1")
    assert state_manager.redis.delete.called
    assert state_manager.redis.lpush.call_count == 2  # 2 remaining positions


@pytest.mark.asyncio
async def test_agent_state_operations(state_manager):
    """Test agent state operations"""
    agent_name = "test_agent"
    state = "ACTIVE"
    heartbeat = datetime.now(timezone.utc)

    # Mock session and query
    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = None  # Agent doesn't exist

    state_manager.async_session.return_value = mock_session

    # Test update (create new)
    await state_manager.update_agent_state(agent_name, state, heartbeat)

    # Verify new AgentState was created and added
    mock_session.add.assert_called_once()
    args, kwargs = mock_session.add.call_args
    new_state = args[0]
    assert isinstance(new_state, AgentState)
    assert new_state.agent_name == agent_name
    assert new_state.state == state

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_agent_state_update_existing(state_manager):
    """Test updating existing agent state"""
    agent_name = "test_agent"
    state = "PROCESSING"
    heartbeat = datetime.now(timezone.utc)

    # Mock existing agent state
    existing_state = MagicMock()
    existing_state.state = "IDLE"
    existing_state.last_heartbeat = datetime.now(timezone.utc)
    existing_state.state_data = {}

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = existing_state

    state_manager.async_session.return_value = mock_session

    # Test update existing
    await state_manager.update_agent_state(agent_name, state, heartbeat, {"key": "value"})

    # Verify existing state was updated
    assert existing_state.state == state
    assert existing_state.last_heartbeat == heartbeat
    assert existing_state.state_data == {"key": "value"}

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_agent_state(state_manager):
    """Test getting agent state"""
    agent_name = "test_agent"

    # Mock agent state
    mock_agent_state = MagicMock()
    mock_agent_state.agent_name = agent_name
    mock_agent_state.state = "ACTIVE"
    mock_agent_state.last_heartbeat = datetime.now(timezone.utc)
    mock_agent_state.state_data = {"key": "value"}

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = mock_agent_state

    state_manager.async_session.return_value = mock_session

    result = await state_manager.get_agent_state(agent_name)

    assert result["agent_name"] == agent_name
    assert result["state"] == "ACTIVE"
    assert "last_heartbeat" in result


@pytest.mark.asyncio
async def test_log_error(state_manager):
    """Test error logging"""
    agent_name = "test_agent"
    error_msg = "Test error"

    # Mock agent state
    mock_agent_state = MagicMock()
    mock_agent_state.error_count = 0
    mock_agent_state.last_error = None
    mock_agent_state.last_error_time = None

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = mock_agent_state

    state_manager.async_session.return_value = mock_session

    await state_manager.log_error(agent_name, error_msg)

    assert mock_agent_state.error_count == 1
    assert mock_agent_state.last_error == error_msg
    assert mock_agent_state.last_error_time is not None

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_market_price_operations(state_manager):
    """Test market price operations"""
    symbol = "BTCUSDT"
    price = 45000.0

    # Test update price
    await state_manager.update_price(symbol, price)
    state_manager.redis.hset.assert_called_with("state:current_prices", symbol, json.dumps(price, default=str))

    # Test get price
    state_manager.redis.hget.return_value = json.dumps(price).encode()
    result = await state_manager.get_price(symbol)
    assert result == price

    # Test get all prices
    state_manager.redis.hgetall.return_value = {
        b"BTCUSDT": json.dumps(45000.0).encode(),
        b"ETHUSDT": json.dumps(3000.0).encode()
    }
    prices = await state_manager.get_all_prices()
    assert prices["BTCUSDT"] == 45000.0
    assert prices["ETHUSDT"] == 3000.0


@pytest.mark.asyncio
async def test_trade_operations(state_manager):
    """Test trade persistence operations"""
    trade_data = {
        "trade_id": "trade_123",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": 45000.0,
        "position_size": 0.1,
        "stop_loss": 44000.0
    }

    # Mock session
    mock_session = AsyncMock()
    mock_trade = MagicMock()
    mock_trade.trade_id = "trade_123"
    mock_session.add.return_value = None
    mock_session.commit.return_value = None
    mock_session.refresh.return_value = None

    state_manager.async_session.return_value = mock_session

    # Test save trade
    trade_id = await state_manager.save_trade(trade_data)
    assert trade_id == "trade_123"

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_update_trade(state_manager):
    """Test trade update"""
    trade_id = "trade_123"
    updates = {"exit_price": 46000.0, "status": "CLOSED"}

    # Mock existing trade
    mock_trade = MagicMock()
    mock_trade.exit_price = None
    mock_trade.status = "OPEN"

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = mock_trade

    state_manager.async_session.return_value = mock_session

    await state_manager.update_trade(trade_id, updates)

    assert mock_trade.exit_price == 46000.0
    assert mock_trade.status == "CLOSED"
    assert mock_trade.updated_at is not None

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_trade(state_manager):
    """Test getting trade by ID"""
    trade_id = "trade_123"

    # Mock trade object
    mock_trade = MagicMock()
    mock_trade.id = 1
    mock_trade.trade_id = trade_id
    mock_trade.symbol = "BTCUSDT"
    mock_trade.direction = "LONG"
    mock_trade.entry_price = 45000.0
    mock_trade.position_size = 0.1
    mock_trade.status = "OPEN"
    mock_trade.created_at = datetime.now(timezone.utc)
    mock_trade.updated_at = datetime.now(timezone.utc)

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = mock_trade

    state_manager.async_session.return_value = mock_session

    result = await state_manager.get_trade(trade_id)

    assert result["trade_id"] == trade_id
    assert result["symbol"] == "BTCUSDT"
    assert result["direction"] == "LONG"


@pytest.mark.asyncio
async def test_state_recovery_operations(state_manager):
    """Test state recovery operations"""
    # Mock agent states
    mock_agent_state = MagicMock()
    mock_agent_state.agent_name = "test_agent"
    mock_agent_state.state = "ACTIVE"
    mock_agent_state.last_heartbeat = datetime.now(timezone.utc)
    mock_agent_state.state_data = {"key": "value"}
    mock_agent_state.error_count = 0
    mock_agent_state.last_error = None
    mock_agent_state.last_error_time = None

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_agent_state]
    mock_result.scalars.return_value = mock_scalars
    mock_session.query.return_value = mock_query
    mock_session.execute.return_value = mock_result

    state_manager.async_session.return_value = mock_session

    # Mock Redis data
    state_manager.redis.hgetall.side_effect = [
        {b"balance": b'10000'},  # portfolio
        [],  # positions (empty)
        {b"BTCUSDT": json.dumps(45000.0).encode()}  # prices
    ]

    # Test recover agent states
    agent_states = await state_manager.recover_agent_states()
    assert "test_agent" in agent_states
    assert agent_states["test_agent"]["state"] == "ACTIVE"

    # Test recover portfolio
    portfolio = await state_manager.recover_portfolio_state()
    assert portfolio == {"balance": 10000}

    # Test recover positions
    positions = await state_manager.recover_positions()
    assert positions == []

    # Test recover prices
    prices = await state_manager.recover_market_prices()
    assert prices == {"BTCUSDT": 45000.0}

    # Test complete recovery
    recovery_data = await state_manager.perform_state_recovery()
    assert "agent_states" in recovery_data
    assert "portfolio" in recovery_data
    assert "positions" in recovery_data
    assert "prices" in recovery_data
    assert "recovery_timestamp" in recovery_data


@pytest.mark.asyncio
async def test_atomic_operations(state_manager):
    """Test atomic operations for critical updates"""
    # Test that operations use proper async context managers
    agent_name = "test_agent"

    mock_session = AsyncMock()
    mock_query = MagicMock()
    mock_filtered_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filtered_query
    mock_filtered_query.scalar_one_or_none.return_value = None

    state_manager.async_session.return_value = mock_session

    # Test agent state update uses transaction
    await state_manager.update_agent_state(agent_name, "ACTIVE", datetime.now(timezone.utc))

    # Verify session was used as async context manager
    mock_session.__aenter__.assert_called()
    mock_session.__aexit__.assert_called()
    mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_error_handling(state_manager):
    """Test error handling in state operations"""
    # Test Redis operation failure
    state_manager.redis.get.side_effect = Exception("Redis connection failed")

    with pytest.raises(Exception):
        await state_manager.get("test_key")

    # Test database operation failure
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("Database error")
    state_manager.async_session.return_value = mock_session

    with pytest.raises(Exception):
        await state_manager.get_agent_state("test_agent")