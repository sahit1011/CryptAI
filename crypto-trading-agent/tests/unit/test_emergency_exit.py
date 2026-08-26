"""
Unit tests for Emergency Exit System
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.execution.emergency_exit import EmergencyExit
from src.execution.position_monitor import MonitoredPosition
from src.execution.exchange_client import Order, OrderSide

@pytest.fixture
def mock_components():
    exchange = AsyncMock()
    position_monitor = MagicMock()
    order_tracker = MagicMock()
    return exchange, position_monitor, order_tracker

@pytest.mark.asyncio
async def test_cancel_all_orders(mock_components):
    exchange, pm, ot = mock_components
    emergency = EmergencyExit(exchange, pm, ot)
    
    # Setup active orders
    ot.get_active_orders.return_value = [
        Order(order_id='1', symbol='BTCUSDT', client_order_id='', side='BUY', order_type='LIMIT', price=100, quantity=1, status='NEW', filled_quantity=0, average_price=0, created_at=None, updated_at=None),
        Order(order_id='2', symbol='ETHUSDT', client_order_id='', side='BUY', order_type='LIMIT', price=100, quantity=1, status='NEW', filled_quantity=0, average_price=0, created_at=None, updated_at=None)
    ]
    
    await emergency.cancel_all_orders()
    
    # Should call cancel_all_orders for each symbol
    assert exchange.cancel_all_orders.call_count == 2
    exchange.cancel_all_orders.assert_any_call('BTCUSDT')
    exchange.cancel_all_orders.assert_any_call('ETHUSDT')

@pytest.mark.asyncio
async def test_panic_close_all(mock_components):
    exchange, pm, ot = mock_components
    emergency = EmergencyExit(exchange, pm, ot)
    
    # Setup positions
    pm.get_positions.return_value = [
        MonitoredPosition(position_id='1', symbol='BTCUSDT', side='LONG', quantity=1.0, entry_price=40000, current_price=40000, stop_loss=39000, take_profit_levels=[]),
        MonitoredPosition(position_id='2', symbol='ETHUSDT', side='SHORT', quantity=10.0, entry_price=2000, current_price=2000, stop_loss=2100, take_profit_levels=[])
    ]
    
    await emergency.panic_close_all()

    # Panic close goes through the UNIFIED reduce-only interface
    # (exchange.close_position with typed OrderSide), not the old
    # place_order(..., order_type='MARKET', reduce_only=True) string API this test
    # was written against. Reduce-only is guaranteed by the method rather than by a
    # keyword the caller might forget — which is why the interface changed.
    assert exchange.close_position.call_count == 2

    # LONG closes by SELLing; SHORT closes by BUYing.
    exchange.close_position.assert_any_call(
        symbol='BTCUSDT', side=OrderSide.SELL, quantity=1.0
    )
    exchange.close_position.assert_any_call(
        symbol='ETHUSDT', side=OrderSide.BUY, quantity=10.0
    )

