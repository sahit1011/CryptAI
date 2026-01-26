"""
Unit tests for Execution Agent
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from src.execution.execution_agent import ExecutionAgent
from src.execution.order_manager import TradeExecution
from src.execution.exchange_client import Order


@pytest.fixture
def mock_components():
    """Mock all internal components"""
    with patch('src.execution.execution_agent.ExchangeClientFactory') as mock_factory, \
         patch('src.execution.execution_agent.OrderManager') as mock_om, \
         patch('src.execution.execution_agent.OrderTracker') as mock_ot, \
         patch('src.execution.execution_agent.PositionMonitor') as mock_pm:
        
        # Setup mocks
        mock_exchange = AsyncMock()
        mock_factory.create_client.return_value = mock_exchange
        
        mock_om_instance = AsyncMock()
        mock_om.return_value = mock_om_instance
        
        mock_ot_instance = AsyncMock()
        mock_ot.return_value = mock_ot_instance
        
        mock_pm_instance = MagicMock()
        mock_pm_instance.get_positions.return_value = []
        mock_pm.return_value = mock_pm_instance
        
        with patch('src.execution.execution_agent.ExecutionAgent._price_update_loop', new_callable=AsyncMock):
            yield {
                'exchange': mock_exchange,
                'order_manager': mock_om_instance,
                'order_tracker': mock_ot_instance,
                'position_monitor': mock_pm_instance
            }


@pytest.mark.asyncio
async def test_agent_initialization(mock_components):
    """Test agent initialization"""
    
    agent = ExecutionAgent({'EXCHANGE_NAME': 'bingx', 'USE_TESTNET': True})
    
    assert agent.exchange is not None
    assert agent.order_manager is not None
    assert agent.position_monitor is not None
    assert agent.is_running is False


@pytest.mark.asyncio
async def test_agent_start_stop(mock_components):
    """Test agent start/stop lifecycle"""
    
    agent = ExecutionAgent()
    
    await agent.start()
    assert agent.is_running is True
    mock_components['order_tracker'].start.assert_called_once()
    
    await agent.stop()
    assert agent.is_running is False
    mock_components['order_tracker'].stop.assert_called_once()
    mock_components['exchange'].close.assert_called_once()


@pytest.mark.asyncio
async def test_execute_trade_success(mock_components):
    """Test successful trade execution"""
    
    agent = ExecutionAgent()
    await agent.start()
    
    # Mock execution result
    execution = MagicMock(spec=TradeExecution)
    execution.execution_id = 'exec_1'
    execution.symbol = 'BTCUSDT'
    execution.direction = 'LONG'
    execution.entry_order = MagicMock(spec=Order)
    execution.entry_order.average_price = 43000.0
    execution.stop_loss_order = MagicMock(spec=Order)
    execution.take_profit_orders = []
    execution.stop_loss_price = 42000.0
    execution.take_profit_prices = [44000.0]
    
    mock_components['order_manager'].execute_trade_setup.return_value = execution
    
    setup = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry_price': 43000.0,
        'stop_loss': 42000.0,
        'take_profits': [{'price': 44000.0, 'size': 0.1}],
        'position_size': 0.1
    }
    
    result = await agent.execute_trade(setup)
    
    assert result['status'] == 'success'
    assert result['execution_id'] == 'exec_1'
    
    # Verify interactions
    mock_components['order_manager'].execute_trade_setup.assert_called_once()
    mock_components['position_monitor'].add_position.assert_called_once()
    mock_components['order_tracker'].track_order.assert_called()


@pytest.mark.asyncio
async def test_execute_trade_failure(mock_components):
    """Test trade execution failure"""
    
    agent = ExecutionAgent()
    await agent.start()
    
    # Mock failure
    mock_components['order_manager'].execute_trade_setup.side_effect = Exception("API Error")
    
    setup = {
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'entry_price': 43000.0,
        'stop_loss': 42000.0,
        'take_profits': [],
        'position_size': 0.1
    }
    
    result = await agent.execute_trade(setup)
    
    assert result['status'] == 'failed'
    assert 'API Error' in result['error']
    
    # Verify circuit breaker recorded failure
    assert agent.circuit_breaker.failure_count == 1


@pytest.mark.asyncio
async def test_execute_trade_circuit_breaker_open(mock_components):
    """Test execution blocked when circuit breaker open"""
    
    agent = ExecutionAgent()
    await agent.start()
    
    # Open circuit breaker
    agent.circuit_breaker._open()
    
    setup = {'symbol': 'BTCUSDT'}
    
    with pytest.raises(RuntimeError, match="Circuit breaker open"):
        await agent.execute_trade(setup)
