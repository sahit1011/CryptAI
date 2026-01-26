"""
Unit tests for Position Monitor
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.execution.position_monitor import (
    PositionMonitor, MonitoredPosition
)


@pytest.fixture
def position_monitor():
    """Create position monitor"""
    return PositionMonitor()


def test_add_position(position_monitor):
    """Test adding position"""
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=43000.0,
        stop_loss=42000.0,
        take_profit_levels=[44000.0]
    )
    
    assert 'pos_1' in position_monitor.positions
    pos = position_monitor.get_position('pos_1')
    assert pos.symbol == 'BTCUSDT'
    assert pos.entry_price == 43000.0


@pytest.mark.asyncio
async def test_calculate_pnl_long(position_monitor):
    """Test P&L calculation for LONG position"""
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[41000.0]
    )
    
    # Price moves up 1000 (Profit)
    position_monitor.update_price('BTCUSDT', 41000.0)
    
    # Allow async task to run (even if we don't check result)
    await asyncio.sleep(0)
    
    pos = position_monitor.get_position('pos_1')
    assert pos.unrealized_pnl == 100.0  # (41000 - 40000) * 0.1
    assert pos.unrealized_pnl_pct == 2.5  # (100 / 4000) * 100


@pytest.mark.asyncio
async def test_calculate_pnl_short(position_monitor):
    """Test P&L calculation for SHORT position"""
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='SHORT',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=41000.0,
        take_profit_levels=[39000.0]
    )
    
    # Price moves down 1000 (Profit)
    position_monitor.update_price('BTCUSDT', 39000.0)
    
    await asyncio.sleep(0)
    
    pos = position_monitor.get_position('pos_1')
    assert pos.unrealized_pnl == 100.0  # (40000 - 39000) * 0.1
    assert pos.unrealized_pnl_pct == 2.5


@pytest.mark.asyncio
async def test_stop_loss_trigger(position_monitor):
    """Test stop-loss trigger"""
    
    sl_triggered = False
    
    async def on_sl(position):
        nonlocal sl_triggered
        sl_triggered = True
    
    position_monitor.on_stop_loss(on_sl)
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[41000.0]
    )
    
    # Trigger SL
    position_monitor.update_price('BTCUSDT', 38900.0)
    
    # Allow async task to run
    await asyncio.sleep(0.1)
    
    assert sl_triggered is True


@pytest.mark.asyncio
async def test_take_profit_trigger(position_monitor):
    """Test take-profit trigger"""
    
    tp_triggered = False
    
    async def on_tp(position, price):
        nonlocal tp_triggered
        tp_triggered = True
    
    position_monitor.on_take_profit(on_tp)
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[41000.0, 42000.0]
    )
    
    # Trigger TP1
    position_monitor.update_price('BTCUSDT', 41000.0)
    
    # Allow async task to run
    await asyncio.sleep(0.1)
    
    assert tp_triggered is True


@pytest.mark.asyncio
async def test_trailing_stop_update(position_monitor):
    """Test trailing stop update"""
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[42000.0],
        trailing_stop_distance=1000.0
    )
    
    # Price moves up to 41000
    # New stop should be 41000 - 1000 = 40000
    position_monitor.update_price('BTCUSDT', 41000.0)
    await asyncio.sleep(0)
    
    pos = position_monitor.get_position('pos_1')
    assert pos.stop_loss == 40000.0
    
    # Price drops to 40500
    # Stop should NOT move down
    position_monitor.update_price('BTCUSDT', 40500.0)
    await asyncio.sleep(0)
    assert pos.stop_loss == 40000.0


def test_remove_position(position_monitor):
    """Test removing position"""
    
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[41000.0]
    )
    
    position_monitor.remove_position('pos_1')
    assert 'pos_1' not in position_monitor.positions


@pytest.mark.asyncio
async def test_get_total_pnl(position_monitor):
    """Test total P&L calculation"""
    
    # Pos 1: +100
    position_monitor.add_position(
        position_id='pos_1',
        symbol='BTCUSDT',
        side='LONG',
        quantity=0.1,
        entry_price=40000.0,
        stop_loss=39000.0,
        take_profit_levels=[41000.0]
    )
    
    # Pos 2: -50
    position_monitor.add_position(
        position_id='pos_2',
        symbol='ETHUSDT',
        side='LONG',
        quantity=1.0,
        entry_price=2000.0,
        stop_loss=1900.0,
        take_profit_levels=[2100.0]
    )
    
    position_monitor.update_price('BTCUSDT', 41000.0)  # +100
    position_monitor.update_price('ETHUSDT', 1950.0)   # -50
    
    await asyncio.sleep(0)
    
    assert position_monitor.get_total_pnl() == 50.0
