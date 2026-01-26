import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.execution.execution_agent import ExecutionAgent

@pytest.mark.asyncio
async def test_simple_init():
    with patch('src.execution.execution_agent.ExchangeClientFactory') as mock_factory, \
         patch('src.execution.execution_agent.OrderManager'), \
         patch('src.execution.execution_agent.OrderTracker'), \
         patch('src.execution.execution_agent.PositionMonitor'), \
         patch('src.execution.execution_agent.RetryHandler'), \
         patch('src.execution.execution_agent.CircuitBreaker'):
        
        mock_factory.create_client.return_value = AsyncMock()
        
        agent = ExecutionAgent()
        assert agent.exchange is not None
        print("Agent initialized successfully")

@pytest.mark.asyncio
async def test_simple_start_stop():
    with patch('src.execution.execution_agent.ExchangeClientFactory') as mock_factory, \
         patch('src.execution.execution_agent.OrderManager'), \
         patch('src.execution.execution_agent.OrderTracker') as mock_tracker, \
         patch('src.execution.execution_agent.PositionMonitor'), \
         patch('src.execution.execution_agent.RetryHandler'), \
         patch('src.execution.execution_agent.CircuitBreaker'), \
         patch('src.execution.execution_agent.ExecutionAgent._price_update_loop', new_callable=AsyncMock):
        
        mock_factory.create_client.return_value = AsyncMock()
        mock_tracker_instance = AsyncMock()
        mock_tracker.return_value = mock_tracker_instance
        
        agent = ExecutionAgent()
        await agent.start()
        assert agent.is_running is True
        
        await agent.stop()
        assert agent.is_running is False
