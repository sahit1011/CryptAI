"""
Unit tests for Trade History Manager
"""
import pytest
from datetime import datetime, timedelta
from src.memory.trade_history_manager import TradeHistoryManager, TradeStats

@pytest.fixture
def trade_manager():
    """Create a TradeHistoryManager with in-memory SQLite"""
    return TradeHistoryManager("sqlite:///:memory:")

def test_store_and_retrieve_trade(trade_manager):
    """Test storing and retrieving a trade"""
    entry_time = datetime.now()
    
    trade = trade_manager.store_trade(
        trade_id="trade_1",
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=50000.0,
        entry_time=entry_time,
        position_size=0.1,
        stop_loss=49000.0,
        take_profit_levels=[51000.0, 52000.0],
        risk_amount=100.0,
        strategy_type="SCALP",
        confidence_score=0.85,
        confluence_count=4
    )
    
    assert trade.trade_id == "trade_1"
    assert trade.symbol == "BTCUSDT"
    
    # Retrieve
    retrieved = trade_manager.get_trade("trade_1")
    assert retrieved is not None
    assert retrieved.entry_price == 50000.0
    assert retrieved.take_profit_levels == [51000.0, 52000.0]

def test_update_trade_exit(trade_manager):
    """Test updating trade exit"""
    entry_time = datetime.now() - timedelta(minutes=60)
    
    trade_manager.store_trade(
        trade_id="trade_2",
        symbol="ETHUSDT",
        direction="SHORT",
        entry_price=3000.0,
        entry_time=entry_time,
        position_size=1.0,
        stop_loss=3100.0,
        take_profit_levels=[2900.0],
        risk_amount=100.0
    )
    
    exit_time = datetime.now()
    updated = trade_manager.update_trade_exit(
        trade_id="trade_2",
        exit_price=2900.0,
        exit_time=exit_time,
        exit_reason="take_profit"
    )
    
    assert updated.exit_price == 2900.0
    assert updated.pnl == 100.0  # (3000 - 2900) * 1.0
    assert updated.is_winner is True
    assert updated.duration_minutes > 59.0

def test_calculate_stats(trade_manager):
    """Test statistics calculation"""
    base_time = datetime.now()
    
    # Trade 1: Win
    trade_manager.store_trade(
        trade_id="t1", symbol="BTC", direction="LONG",
        entry_price=100, entry_time=base_time, position_size=1,
        stop_loss=90, take_profit_levels=[110], risk_amount=10
    )
    trade_manager.update_trade_exit(
        trade_id="t1", exit_price=120, exit_time=base_time + timedelta(minutes=10),
        exit_reason="tp"
    )
    
    # Trade 2: Loss
    trade_manager.store_trade(
        trade_id="t2", symbol="BTC", direction="LONG",
        entry_price=100, entry_time=base_time, position_size=1,
        stop_loss=90, take_profit_levels=[110], risk_amount=10
    )
    trade_manager.update_trade_exit(
        trade_id="t2", exit_price=90, exit_time=base_time + timedelta(minutes=5),
        exit_reason="sl"
    )
    
    stats = trade_manager.calculate_stats()
    
    assert stats.total_trades == 2
    assert stats.winning_trades == 1
    assert stats.losing_trades == 1
    assert stats.win_rate == 0.5
    assert stats.total_pnl == 10.0  # 20 - 10
    assert stats.average_win == 20.0
    assert stats.average_loss == -10.0
    assert stats.profit_factor == 2.0  # 20 / 10
