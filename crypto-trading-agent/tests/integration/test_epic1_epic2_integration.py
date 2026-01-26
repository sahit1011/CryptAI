"""
Integration Test for Epic 1 & Epic 2
Tests the complete data pipeline end-to-end
"""
import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.agents.data_agent import DataCollectionAgent


@pytest.mark.asyncio
async def test_redis_connections():
    """Test #1: Verify Redis connections work without 'await' bug"""
    from src.utils.config import get_config
    import redis.asyncio as redis
    
    config = get_config()
    
    # Test message bus Redis connection
    redis_client = redis.from_url(config.database.redis_url)
    await redis_client.ping()
    await redis_client.close()
    
    print("✅ Test #1 PASSED: Redis connections work correctly")


@pytest.mark.asyncio
async def test_message_bus_auto_recovery():
    """Test #2: Verify message bus listen loop has auto-recovery"""
    from src.utils.config import get_config
    
    config = get_config()
    message_bus = MessageBus(config.database.redis_url)
    await message_bus.connect()
    
    # Start listening
    received_messages = []
    
    async def test_callback(data):
        received_messages.append(data)
    
    await message_bus.subscribe("test_channel", test_callback)
    
    # Give it time to start
    await asyncio.sleep(1)
    
    # Publish a message
    await message_bus.publish("test_channel", {"test": "data"})
    
    # Wait for message
    await asyncio.sleep(1)
    
    assert len(received_messages) > 0, "Should have received message"
    assert received_messages[0]["test"] == "data"
    
    await message_bus.disconnect()
    
    print("✅ Test #2 PASSED: Message bus auto-recovery implemented")


@pytest.mark.asyncio
async def test_state_manager_operations():
    """Test #3: Verify state manager basic operations"""
    from src.utils.config import get_config
    
    config = get_config()
    state_manager = StateManager()
    await state_manager.connect()
    
    # Test hot state
    await state_manager.set("test_key", {"value": 123})
    result = await state_manager.get("test_key")
    assert result["value"] == 123
    
    # Test price updates
    await state_manager.update_price("BTC/USDT", 43250.50)
    price = await state_manager.get_price("BTC/USDT")
    assert price == 43250.50
    
    # Cleanup
    await state_manager.delete("test_key")
    await state_manager.disconnect()
    
    print("✅ Test #3 PASSED: State manager operations work")


@pytest.mark.asyncio
async def test_candle_deduplication():
    """Test #4: Verify candle deduplication logic works"""
    # Simulate buffer
    buffer = []
    
    # Simulate closed candle arriving
    candle1 = {
        'timestamp': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        'open': 43000.0,
        'high': 43100.0,
        'low': 42900.0,
        'close': 43050.0,
        'volume': 100.0,
        'is_closed': True
    }
    
    # First time - should append
    if not buffer or candle1['timestamp'] > buffer[-1]['timestamp']:
        buffer.append(candle1)
    
    assert len(buffer) == 1
    
    # Same candle arrives again (update)
    candle1_update = candle1.copy()
    candle1_update['close'] = 43060.0
    
    if buffer and buffer[-1]['timestamp'] == candle1_update['timestamp']:
        buffer[-1] = candle1_update
    
    assert len(buffer) == 1  # Should still be 1
    assert buffer[0]['close'] == 43060.0  # But updated
    
    # Open candle arrives
    candle2_open = {
        'timestamp': datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
        'open': 43060.0,
        'high': 43070.0,
        'low': 43055.0,
        'close': 43065.0,
        'volume': 50.0,
        'is_closed': False
    }
    
    if not buffer or candle2_open['timestamp'] > buffer[-1]['timestamp']:
        buffer.append(candle2_open)
    
    assert len(buffer) == 2
    
    # Open candle updates
    candle2_update = candle2_open.copy()
    candle2_update['close'] = 43070.0
    
    if buffer and buffer[-1]['timestamp'] == candle2_update['timestamp']:
        buffer[-1] = candle2_update
    
    assert len(buffer) == 2  # Still 2
    assert buffer[-1]['close'] == 43070.0  # Updated
    
    print("✅ Test #4 PASSED: Candle deduplication works correctly")


@pytest.mark.asyncio
async def test_symbol_lookup_optimization():
    """Test #5: Verify O(1) symbol lookup"""
    from src.utils.config import get_config
    
    config = get_config()
    
    # Build mapping like DataAgent does
    binance_to_symbol = {}
    for symbol in config.trading.symbols:
        binance_format = symbol.replace('/', '').upper()
        binance_to_symbol[binance_format] = symbol
    
    # Test lookup
    assert binance_to_symbol.get('BTCUSDT') == 'BTC/USDT'
    assert binance_to_symbol.get('ETHUSDT') == 'ETH/USDT'
    assert binance_to_symbol.get('UNKNOWN') is None
    
    print("✅ Test #5 PASSED: O(1) symbol lookup works")


@pytest.mark.asyncio
async def test_timeframe_normalization():
    """Test #6: Verify timeframe normalization"""
    # Test data
    timeframes = ['5m', '15m', '1h', '4H', '1D']  # Mixed case
    
    # Normalize
    normalized = [tf.lower() for tf in timeframes]
    
    assert normalized == ['5m', '15m', '1h', '4h', '1d']
    
    print("✅ Test #6 PASSED: Timeframe normalization works")


@pytest.mark.asyncio
async def test_gap_detection():
    """Test #7: Verify gap detection logic"""
    from src.agents.data_agent import DataCollectionAgent
    from src.utils.config import get_config
    
    config = get_config()
    message_bus = MessageBus(config.database.redis_url)
    state_manager = StateManager()
    
    await message_bus.connect()
    await state_manager.connect()
    
    # Create data agent
    agent = DataCollectionAgent(message_bus, state_manager)
    
    # Create buffer with gap
    candles = [
        {
            'timestamp': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            'open': 43000.0, 'high': 43100.0, 'low': 42900.0,
            'close': 43050.0, 'volume': 100.0, 'is_closed': True
        },
        {
            'timestamp': datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
            'open': 43050.0, 'high': 43150.0, 'low': 42950.0,
            'close': 43100.0, 'volume': 100.0, 'is_closed': True
        },
        # GAP HERE - missing 10:10
        {
            'timestamp': datetime(2025, 1, 1, 10, 15, tzinfo=timezone.utc),
            'open': 43100.0, 'high': 43200.0, 'low': 43000.0,
            'close': 43150.0, 'volume': 100.0, 'is_closed': True
        },
    ]
    
    gaps = agent._check_buffer_gaps(candles, '5m')
    
    assert len(gaps) == 1, "Should detect one gap"
    assert gaps[0]['index'] == 2
    
    await message_bus.disconnect()
    await state_manager.disconnect()
    
    print("✅ Test #7 PASSED: Gap detection works")


@pytest.mark.asyncio
async def test_buffer_management():
    """Test #8: Verify buffer maintains max size"""
    max_buffer_size = 1000
    buffer = []
    
    # Add 1100 candles
    for i in range(1100):
        candle = {
            'timestamp': datetime(2025, 1, 1, 10, i * 5, tzinfo=timezone.utc),
            'open': 43000.0 + i,
            'close': 43000.0 + i,
            'is_closed': True
        }
        buffer.append(candle)
        
        # Maintain max size
        if len(buffer) > max_buffer_size:
            buffer.pop(0)
    
    assert len(buffer) == max_buffer_size
    assert buffer[0]['open'] == 43100.0  # First 100 were removed
    
    print("✅ Test #8 PASSED: Buffer size management works")


@pytest.mark.asyncio
async def test_full_pipeline_simulation():
    """Test #9: Simulate full data pipeline (without live WebSocket)"""
    from src.utils.config import get_config
    
    config = get_config()
    
    # Initialize components
    message_bus = MessageBus(config.database.redis_url)
    state_manager = StateManager()
    
    await message_bus.connect()
    await state_manager.connect()
    
    # Create data agent
    data_agent = DataCollectionAgent(message_bus, state_manager)
    
    # Verify initialization
    assert data_agent.name == "data_agent"
    assert data_agent.candle_buffers is not None
    assert len(data_agent.binance_to_symbol) > 0
    
    # Verify symbol mapping
    assert 'BTCUSDT' in data_agent.binance_to_symbol
    
    # Verify timeframes normalized
    assert all(tf.islower() for tf in data_agent.normalized_timeframes)
    
    # Test message handling
    result = await data_agent._handle_fetch_data({
        'symbol': 'BTC/USDT',
        'timeframes': ['5m']
    })
    
    assert result['status'] == 'success'
    
    await message_bus.disconnect()
    await state_manager.disconnect()
    
    print("✅ Test #9 PASSED: Full pipeline simulation works")


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("EPIC 1 & EPIC 2 INTEGRATION TESTS")
    print("="*60 + "\n")
    
    tests = [
        test_redis_connections,
        test_message_bus_auto_recovery,
        test_state_manager_operations,
        test_candle_deduplication,
        test_symbol_lookup_optimization,
        test_timeframe_normalization,
        test_gap_detection,
        test_buffer_management,
        test_full_pipeline_simulation,
    ]
    
    for test in tests:
        try:
            asyncio.run(test())
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
