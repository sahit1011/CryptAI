"""
Unit tests for Partial Profit Taking in Order Manager
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


def create_mock_order(order_id: str, price: float = 43000.0, quantity: float = 0.1):
    """Helper to create mock order"""
    return Order(
        order_id=order_id,
        client_order_id='',
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=price,
        quantity=quantity,
        status=OrderStatus.FILLED,
        filled_quantity=quantity,
        average_price=price,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


@pytest.mark.asyncio
async def test_move_stop_loss(order_manager, mock_exchange):
    """Test moving stop loss"""
    
    # Setup execution
    execution = TradeExecution(
        execution_id='exec_1',
        symbol='BTCUSDT',
        direction='LONG',
        stop_loss_price=42000.0
    )
    
    sl_order = create_mock_order('sl_1', 42000.0)
    execution.stop_loss_order = sl_order
    order_manager.active_executions['exec_1'] = execution
    
    # Mock exchange responses
    mock_exchange.cancel_order.return_value = True
    mock_exchange.place_stop_loss_order.return_value = create_mock_order('sl_2', 42500.0)
    
    # Move SL
    new_order = await order_manager.move_stop_loss('exec_1', 42500.0)
    
    assert new_order.order_id == 'sl_2'
    assert execution.stop_loss_price == 42500.0
    assert execution.stop_loss_order.order_id == 'sl_2'
    assert mock_exchange.cancel_order.called
    assert mock_exchange.place_stop_loss_order.called


@pytest.mark.asyncio
async def test_on_take_profit_fill_moves_sl_to_breakeven(order_manager, mock_exchange):
    """Test TP fill triggers SL move to breakeven"""
    
    # Setup execution
    execution = TradeExecution(
        execution_id='exec_1',
        symbol='BTCUSDT',
        direction='LONG',
        stop_loss_price=42000.0
    )
    
    entry_order = create_mock_order('entry_1', 43000.0)
    sl_order = create_mock_order('sl_1', 42000.0)
    
    execution.entry_order = entry_order
    execution.stop_loss_order = sl_order
    order_manager.active_executions['exec_1'] = execution
    
    # Mock exchange responses
    mock_exchange.place_stop_loss_order.return_value = create_mock_order('sl_2', 43000.0)
    
    # Trigger TP fill
    await order_manager.on_take_profit_fill('exec_1', 'tp_1', 44000.0)
    
    # SL should be moved to entry price (43000)
    assert execution.stop_loss_price == 43000.0
    assert mock_exchange.cancel_order.called
    assert mock_exchange.place_stop_loss_order.called


@pytest.mark.asyncio
async def test_on_take_profit_fill_no_move_if_already_better(order_manager, mock_exchange):
    """Test TP fill does NOT move SL if current SL is already better than breakeven"""
    
    # Setup execution with SL already in profit
    execution = TradeExecution(
        execution_id='exec_1',
        symbol='BTCUSDT',
        direction='LONG',
        stop_loss_price=43500.0  # Higher than entry
    )
    
    entry_order = create_mock_order('entry_1', 43000.0)
    sl_order = create_mock_order('sl_1', 43500.0)
    
    execution.entry_order = entry_order
    execution.stop_loss_order = sl_order
    order_manager.active_executions['exec_1'] = execution
    
    # Trigger TP fill
    await order_manager.on_take_profit_fill('exec_1', 'tp_1', 44000.0)
    
    # SL should NOT change
    assert execution.stop_loss_price == 43500.0
    assert not mock_exchange.cancel_order.called
