"""
Integration tests for Execution Flow
Tests complete order execution flow with mocked exchange
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.execution.exchange_client import (
    BingXClient, Order, OrderSide, OrderType, OrderStatus
)
from src.execution.order_manager import (
    OrderManager, ExecutionStrategy
)
from src.execution.order_tracker import OrderTracker
from src.execution.error_handler import (
    CircuitBreaker, RetryHandler, NetworkException
)


@pytest.fixture
def mock_bingx_client():
    """Create mock BingX client"""
    client = AsyncMock(spec=BingXClient)
    return client


def create_order_response(order_id: str, status: str = 'FILLED'):
    """Helper to create order response"""
    return Order(
        order_id=order_id,
        client_order_id='',
        symbol='BTC-USDT',
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=None,
        quantity=0.1,
        status=OrderStatus[status],
        filled_quantity=0.1 if status == 'FILLED' else 0.0,
        average_price=43000.0 if status == 'FILLED' else 0.0,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


@pytest.mark.asyncio
async def test_complete_trade_execution_flow(mock_bingx_client):
    """Test complete trade execution from entry to take-profit"""
    
    # Setup mock responses
    mock_bingx_client.place_market_order.return_value = create_order_response('entry_001')
    mock_bingx_client.place_stop_loss_order.return_value = create_order_response('sl_001')
    mock_bingx_client.place_limit_order.return_value = create_order_response('tp_001')
    
    # Create order manager
    manager = OrderManager(mock_bingx_client)
    
    # Execute trade setup
    execution = await manager.execute_trade_setup(
        symbol='BTC-USDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[
            {'price': 43500.0, 'size': 0.05},
            {'price': 44000.0, 'size': 0.05}
        ],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE,
        metadata={'strategy_type': 'SCALP', 'confidence_score': 0.85}
    )
    
    # Verify execution
    assert execution.status == 'active'
    assert execution.entry_filled is True
    assert execution.entry_order.order_id == 'entry_001'
    assert execution.stop_loss_order.order_id == 'sl_001'
    assert len(execution.take_profit_orders) == 2
    
    # Verify all orders were placed
    assert mock_bingx_client.place_market_order.called
    assert mock_bingx_client.place_stop_loss_order.called
    assert mock_bingx_client.place_limit_order.call_count == 2


@pytest.mark.asyncio
async def test_order_tracking_integration(mock_bingx_client):
    """Test order tracking with order manager"""
    
    # Setup
    mock_bingx_client.place_market_order.return_value = create_order_response('entry_001')
    mock_bingx_client.place_stop_loss_order.return_value = create_order_response('sl_001')
    mock_bingx_client.get_order_status.return_value = create_order_response('entry_001', 'FILLED')
    
    manager = OrderManager(mock_bingx_client)
    tracker = OrderTracker(mock_bingx_client, polling_interval=1, enable_websocket=False)
    
    # Execute trade
    execution = await manager.execute_trade_setup(
        symbol='BTC-USDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE
    )
    
    # Track entry order
    tracker.track_order(execution.entry_order)
    
    # Verify tracking
    assert tracker.get_order_status('entry_001') is not None


@pytest.mark.asyncio
async def test_error_recovery_with_retry(mock_bingx_client):
    """Test error recovery with retry handler"""
    
    retry_handler = RetryHandler(max_retries=2, base_delay=0.1)
    
    call_count = 0
    
    async def flaky_order_placement():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise NetworkException("Temporary network error")
        return create_order_response('entry_001')
    
    # Should succeed after retry
    order = await retry_handler.execute_with_retry(flaky_order_placement)
    
    assert order.order_id == 'entry_001'
    assert call_count == 2


@pytest.mark.asyncio
async def test_circuit_breaker_integration(mock_bingx_client):
    """Test circuit breaker prevents cascading failures"""
    
    circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
    
    # Simulate failures
    for _ in range(3):
        circuit_breaker.record_failure()
    
    # Circuit should be open
    assert circuit_breaker.can_execute() is False
    
    # Wait for recovery
    await asyncio.sleep(1.1)
    
    # Should transition to half-open
    assert circuit_breaker.can_execute() is True


@pytest.mark.asyncio
async def test_rollback_on_partial_failure(mock_bingx_client):
    """Test rollback when stop-loss placement fails"""
    
    # Entry succeeds
    mock_bingx_client.place_market_order.return_value = create_order_response('entry_001')
    
    # Stop-loss fails
    mock_bingx_client.place_stop_loss_order.side_effect = Exception("API Error")
    
    # Cancel should be called for rollback
    mock_bingx_client.cancel_order.return_value = True
    
    manager = OrderManager(mock_bingx_client)
    
    execution = await manager.execute_trade_setup(
        symbol='BTC-USDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE
    )
    
    # Execution should fail
    assert execution.status == 'failed'
    
    # Rollback should have been attempted
    assert mock_bingx_client.cancel_order.called


@pytest.mark.asyncio
async def test_multiple_concurrent_executions(mock_bingx_client):
    """Test handling multiple concurrent trade executions"""
    
    mock_bingx_client.place_market_order.return_value = create_order_response('entry_001')
    mock_bingx_client.place_stop_loss_order.return_value = create_order_response('sl_001')
    mock_bingx_client.place_limit_order.return_value = create_order_response('tp_001')
    
    manager = OrderManager(mock_bingx_client)
    
    # Execute multiple trades concurrently
    tasks = [
        manager.execute_trade_setup(
            symbol='BTC-USDT',
            direction='LONG',
            entry_price=43000.0,
            stop_loss_price=42500.0,
            take_profit_levels=[{'price': 43500.0, 'size': 0.1}],
            total_quantity=0.1,
            strategy=ExecutionStrategy.IMMEDIATE
        )
        for _ in range(3)
    ]
    
    executions = await asyncio.gather(*tasks)
    
    # All should succeed
    assert all(e.status == 'active' for e in executions)
    assert len(manager.get_active_executions()) == 3


@pytest.mark.asyncio
async def test_order_callback_notifications(mock_bingx_client):
    """Test order status callbacks are triggered"""
    
    mock_bingx_client.get_order_status.return_value = create_order_response('test_001', 'FILLED')
    
    tracker = OrderTracker(mock_bingx_client, polling_interval=1, enable_websocket=False)
    
    fill_called = False
    
    async def on_fill(order):
        nonlocal fill_called
        fill_called = True
    
    tracker.register_on_fill(on_fill)
    
    # Track order
    order = create_order_response('test_001', 'NEW')
    tracker.track_order(order)
    
    # Poll should detect fill
    await tracker._poll_orders()
    
    assert fill_called is True
