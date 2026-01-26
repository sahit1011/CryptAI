"""
Unit tests for Order Tracker
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.execution.order_tracker import (
    OrderTracker, OrderUpdate
)
from src.execution.exchange_client import (
    Order, OrderSide, OrderType, OrderStatus
)


@pytest.fixture
def mock_exchange():
    """Create mock exchange client"""
    return AsyncMock()


@pytest.fixture
def order_tracker(mock_exchange):
    """Create order tracker with mock exchange"""
    return OrderTracker(
        exchange_client=mock_exchange,
        polling_interval=1,
        enable_websocket=False  # Disable WebSocket for tests
    )


def create_test_order(order_id: str, status: OrderStatus = OrderStatus.NEW):
    """Helper to create test order"""
    return Order(
        order_id=order_id,
        client_order_id='',
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=43000.0,
        quantity=0.1,
        status=status,
        filled_quantity=0.0,
        average_price=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


def test_track_order(order_tracker):
    """Test adding order to tracking"""
    
    order = create_test_order('test_1')
    order_tracker.track_order(order)
    
    assert 'test_1' in order_tracker.tracked_orders
    assert order_tracker.get_order_status('test_1') == order


def test_untrack_order(order_tracker):
    """Test removing order from tracking"""
    
    order = create_test_order('test_1')
    order_tracker.track_order(order)
    order_tracker.untrack_order('test_1')
    
    assert 'test_1' not in order_tracker.tracked_orders


def test_register_callbacks(order_tracker):
    """Test callback registration"""
    
    def on_fill(order):
        pass
    
    def on_cancel(order):
        pass
    
    order_tracker.register_on_fill(on_fill)
    order_tracker.register_on_cancel(on_cancel)
    
    assert on_fill in order_tracker.on_fill_callbacks
    assert on_cancel in order_tracker.on_cancel_callbacks


@pytest.mark.asyncio
async def test_poll_orders_status_change(order_tracker, mock_exchange):
    """Test polling detects status changes"""
    
    # Track an order
    order = create_test_order('test_1', OrderStatus.NEW)
    order_tracker.track_order(order)
    
    # Mock exchange returns filled order
    filled_order = create_test_order('test_1', OrderStatus.FILLED)
    filled_order.filled_quantity = 0.1
    filled_order.average_price = 43000.0
    mock_exchange.get_order_status.return_value = filled_order
    
    # Poll orders
    await order_tracker._poll_orders()
    
    # Order should be removed from tracking (filled)
    assert 'test_1' not in order_tracker.tracked_orders


@pytest.mark.asyncio
async def test_poll_orders_partial_fill(order_tracker, mock_exchange):
    """Test polling detects partial fills"""
    
    order = create_test_order('test_1', OrderStatus.NEW)
    order_tracker.track_order(order)
    
    # Mock partial fill
    partial_order = create_test_order('test_1', OrderStatus.PARTIALLY_FILLED)
    partial_order.filled_quantity = 0.05
    mock_exchange.get_order_status.return_value = partial_order
    
    await order_tracker._poll_orders()
    
    # Order should still be tracked
    assert 'test_1' in order_tracker.tracked_orders


@pytest.mark.asyncio
async def test_callback_on_fill(order_tracker, mock_exchange):
    """Test fill callback is triggered"""
    
    fill_called = False
    filled_order_ref = None
    
    async def on_fill(order):
        nonlocal fill_called, filled_order_ref
        fill_called = True
        filled_order_ref = order
    
    order_tracker.register_on_fill(on_fill)
    
    order = create_test_order('test_1', OrderStatus.NEW)
    order_tracker.track_order(order)
    
    filled_order = create_test_order('test_1', OrderStatus.FILLED)
    filled_order.filled_quantity = 0.1
    mock_exchange.get_order_status.return_value = filled_order
    
    await order_tracker._poll_orders()
    
    assert fill_called is True
    assert filled_order_ref is not None


@pytest.mark.asyncio
async def test_callback_on_cancel(order_tracker, mock_exchange):
    """Test cancel callback is triggered"""
    
    cancel_called = False
    
    async def on_cancel(order):
        nonlocal cancel_called
        cancel_called = True
    
    order_tracker.register_on_cancel(on_cancel)
    
    order = create_test_order('test_1', OrderStatus.NEW)
    order_tracker.track_order(order)
    
    canceled_order = create_test_order('test_1', OrderStatus.CANCELED)
    mock_exchange.get_order_status.return_value = canceled_order
    
    await order_tracker._poll_orders()
    
    assert cancel_called is True


@pytest.mark.asyncio
async def test_start_stop_tracker(order_tracker):
    """Test starting and stopping tracker"""
    
    await order_tracker.start()
    assert order_tracker.is_running is True
    assert order_tracker.polling_task is not None
    
    await order_tracker.stop()
    assert order_tracker.is_running is False


def test_get_tracked_orders(order_tracker):
    """Test getting all tracked orders"""
    
    order1 = create_test_order('test_1')
    order2 = create_test_order('test_2')
    
    order_tracker.track_order(order1)
    order_tracker.track_order(order2)
    
    tracked = order_tracker.get_tracked_orders()
    
    assert len(tracked) == 2


def test_get_recent_updates(order_tracker):
    """Test getting recent order updates"""
    
    update1 = OrderUpdate(
        order_id='test_1',
        symbol='BTCUSDT',
        status=OrderStatus.FILLED,
        filled_quantity=0.1,
        average_price=43000.0,
        timestamp=datetime.now()
    )
    
    order_tracker.order_updates.append(update1)
    
    recent = order_tracker.get_recent_updates(limit=10)
    
    assert len(recent) == 1
    assert recent[0].order_id == 'test_1'
