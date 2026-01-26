"""
Integration Test: Execution Agent Full Flow
Verifies the end-to-end workflow from trade setup to emergency exit.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.execution.execution_agent import ExecutionAgent
from src.execution.exchange_client import Order, OrderSide, OrderType, OrderStatus


@pytest.fixture
def mock_exchange_client():
    """Create a mock exchange client with realistic behavior"""
    client = AsyncMock()
    
    # Mock order placement to return valid Order objects
    async def place_order_side_effect(**kwargs):
        return Order(
            order_id=f"ord_{datetime.now().timestamp()}",
            symbol=kwargs.get('symbol'),
            side=kwargs.get('side'),
            order_type=kwargs.get('order_type'),
            price=kwargs.get('price', 0),
            quantity=kwargs.get('quantity'),
            status=OrderStatus.NEW,
            filled_quantity=0,
            average_price=0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    client.place_order.side_effect = place_order_side_effect
    
    # Mock cancel order
    client.cancel_order.return_value = True
    client.cancel_all_orders.return_value = True
    
    return client


@pytest.mark.asyncio
async def test_execution_agent_full_flow(mock_exchange_client):
    """
    Test the complete lifecycle of the Execution Agent:
    1. Start Agent
    2. Receive Trade Setup
    3. Execute Entry & Orders
    4. Monitor Position (Simulated Price Update)
    5. Trigger Take Profit
    6. Verify SL Move
    7. Panic Close
    8. Stop Agent
    """
    
    # 1. Setup Agent with Mock Exchange
    with patch('src.execution.execution_agent.ExchangeClientFactory') as mock_factory, \
         patch('src.execution.execution_agent.ExecutionAgent._price_update_loop', new_callable=AsyncMock):
        
        mock_factory.create_client.return_value = mock_exchange_client
        
        agent = ExecutionAgent()
        await agent.start()
        assert agent.is_running is True
        
        # 2. Receive Trade Setup
        setup = {
            'symbol': 'BTCUSDT',
            'direction': 'LONG',
            'entry_price': 40000.0,
            'stop_loss': 39000.0,
            'take_profits': [{'price': 41000.0, 'size': 0.1}],
            'position_size': 0.1,
            'trailing_stop_distance': 500.0
        }
        
        # 3. Execute Trade
        result = await agent.execute_trade(setup)
        
        assert result['status'] == 'success'
        execution_id = result['execution_id']
        
        # Verify orders placed (Entry + SL + TP)
        # Entry: Market or Limit (Strategy default is IMMEDIATE -> Market)
        # SL: Stop Market/Limit
        # TP: Limit
        assert mock_exchange_client.place_order.call_count >= 3
        
        # Verify Position Monitor has the position
        position = agent.position_monitor.get_position(execution_id)
        assert position is not None
        assert position.symbol == 'BTCUSDT'
        assert position.stop_loss == 39000.0
        
        # 4. Simulate Price Update (Move to Profit)
        # Manually update price to trigger TP
        agent.position_monitor.update_price('BTCUSDT', 41000.0)
        
        # Wait for async callbacks
        await asyncio.sleep(0.1)
        
        # 5. Verify TP Triggered
        # Position monitor should have detected TP hit
        # And called agent._handle_tp_trigger -> order_manager.on_take_profit_fill
        
        # 6. Verify SL Move (Break-even)
        # Since TP was hit, SL should move to entry (40000)
        # We need to check if cancel_order and place_order were called for SL update
        
        # Note: In our mock, on_take_profit_fill calls move_stop_loss
        # which calls cancel_order and place_order
        
        # We can check the position's stop_loss in OrderManager
        execution = agent.order_manager.get_execution(execution_id)
        # The logic updates execution.stop_loss_price
        assert execution.stop_loss_price == 40000.0
        
        # 7. Panic Close
        await agent.panic_close()
        
        # Verify panic close actions
        # Should call cancel_all_orders and place market close orders
        assert mock_exchange_client.cancel_all_orders.called
        # Should place SELL order for BTCUSDT (closing LONG)
        # We can check the last call to place_order
        args, kwargs = mock_exchange_client.place_order.call_args
        assert kwargs['symbol'] == 'BTCUSDT'
        assert kwargs['side'] == OrderSide.SELL
        assert kwargs['reduce_only'] is True
        
        # 8. Stop Agent
        await agent.stop()
        assert agent.is_running is False
