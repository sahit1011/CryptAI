"""
Unit tests for Order Manager
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.execution.order_manager import (
    OrderManager, TradeExecution, ExecutionStrategy
)
from src.execution.exchange_client import (
    Order, OrderSide, OrderType, OrderStatus
)


@pytest.fixture
def mock_exchange():
    """Create mock exchange client"""
    exchange = AsyncMock()
    return exchange


@pytest.fixture
def order_manager(mock_exchange):
    """Create order manager with mock exchange"""
    return OrderManager(mock_exchange)


def create_mock_order(order_id: str, status: OrderStatus = OrderStatus.FILLED):
    """Helper to create mock order"""
    return Order(
        order_id=order_id,
        client_order_id='',
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=None,
        quantity=0.1,
        status=status,
        filled_quantity=0.1,
        average_price=43000.0,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


@pytest.mark.asyncio
async def test_execute_trade_setup_immediate(order_manager, mock_exchange):
    """Test immediate execution strategy (market orders)"""
    
    # Mock exchange responses
    mock_exchange.place_market_order.return_value = create_mock_order('entry_1')
    mock_exchange.place_stop_loss_order.return_value = create_mock_order('sl_1')
    mock_exchange.place_limit_order.return_value = create_mock_order('tp_1')
    
    execution = await order_manager.execute_trade_setup(
        symbol='BTCUSDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[
            {'price': 43500.0, 'size': 0.05},
            {'price': 44000.0, 'size': 0.05}
        ],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE
    )
    
    assert execution.status == 'active'
    assert execution.entry_filled is True
    assert execution.entry_order is not None
    assert execution.stop_loss_order is not None
    assert len(execution.take_profit_orders) == 2


@pytest.mark.asyncio
async def test_execute_trade_setup_patient(order_manager, mock_exchange):
    """Test patient execution strategy (limit orders)"""
    
    # Mock exchange responses
    entry_order = create_mock_order('entry_1', OrderStatus.NEW)
    mock_exchange.place_limit_order.return_value = entry_order
    mock_exchange.get_order_status.return_value = create_mock_order('entry_1', OrderStatus.FILLED)
    mock_exchange.place_stop_loss_order.return_value = create_mock_order('sl_1')
    
    execution = await order_manager.execute_trade_setup(
        symbol='BTCUSDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[
            {'price': 43500.0, 'size': 0.1}
        ],
        total_quantity=0.1,
        strategy=ExecutionStrategy.PATIENT
    )
    
    assert execution.status == 'active'
    assert execution.entry_filled is True


@pytest.mark.asyncio
async def test_execute_short_trade(order_manager, mock_exchange):
    """Test short trade execution"""
    
    mock_exchange.place_market_order.return_value = create_mock_order('entry_1')
    mock_exchange.place_stop_loss_order.return_value = create_mock_order('sl_1')
    mock_exchange.place_limit_order.return_value = create_mock_order('tp_1')
    
    execution = await order_manager.execute_trade_setup(
        symbol='BTCUSDT',
        direction='SHORT',
        entry_price=43000.0,
        stop_loss_price=43500.0,  # Higher for short
        take_profit_levels=[
            {'price': 42500.0, 'size': 0.1}
        ],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE
    )
    
    assert execution.direction == 'SHORT'
    assert execution.status == 'active'


@pytest.mark.asyncio
async def test_execution_failure_and_rollback(order_manager, mock_exchange):
    """Test execution failure triggers rollback"""
    
    # Entry succeeds
    mock_exchange.place_market_order.return_value = create_mock_order('entry_1')
    
    # Stop-loss fails
    mock_exchange.place_stop_loss_order.side_effect = Exception("API Error")
    
    # Rollback should cancel entry
    mock_exchange.cancel_order.return_value = True
    
    execution = await order_manager.execute_trade_setup(
        symbol='BTCUSDT',
        direction='LONG',
        entry_price=43000.0,
        stop_loss_price=42500.0,
        take_profit_levels=[],
        total_quantity=0.1,
        strategy=ExecutionStrategy.IMMEDIATE
    )
    
    assert execution.status == 'failed'
    # Verify rollback was attempted
    assert mock_exchange.cancel_order.called


@pytest.mark.asyncio
async def test_wait_for_fill_timeout(order_manager, mock_exchange):
    """Test order fill timeout"""
    
    order = create_mock_order('test_1', OrderStatus.NEW)
    mock_exchange.get_order_status.return_value = order
    
    filled = await order_manager._wait_for_fill(order, timeout=2, check_interval=1)
    
    assert filled is False


@pytest.mark.asyncio
async def test_wait_for_fill_success(order_manager, mock_exchange):
    """Test successful order fill"""
    
    order = create_mock_order('test_1', OrderStatus.NEW)
    filled_order = create_mock_order('test_1', OrderStatus.FILLED)
    mock_exchange.get_order_status.return_value = filled_order
    
    filled = await order_manager._wait_for_fill(order, timeout=5, check_interval=1)
    
    assert filled is True


def test_get_execution(order_manager):
    """Test getting execution by ID"""
    
    execution = TradeExecution(
        execution_id='test_123',
        symbol='BTCUSDT',
        direction='LONG'
    )
    order_manager.active_executions['test_123'] = execution
    
    retrieved = order_manager.get_execution('test_123')
    
    assert retrieved is not None
    assert retrieved.execution_id == 'test_123'


def test_get_active_executions(order_manager):
    """Test getting all active executions"""
    
    exec1 = TradeExecution(execution_id='1', symbol='BTCUSDT', direction='LONG')
    exec2 = TradeExecution(execution_id='2', symbol='ETHUSDT', direction='SHORT')
    
    order_manager.active_executions['1'] = exec1
    order_manager.active_executions['2'] = exec2
    
    active = order_manager.get_active_executions()
    
    assert len(active) == 2
