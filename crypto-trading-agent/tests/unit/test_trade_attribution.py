"""Trade rows must carry their owner.

Lives apart from test_trade_history.py because that file is quarantined wholesale; this
regression must actually run. The tenancy regression it pins: store_trade dropped
user_id, so daemon-booked trades were written with user_id NULL — invisible to their
owner's scoped /api/trades reads and pooled into unscoped service reads.
"""
from datetime import datetime

import pytest

from src.memory.trade_history_manager import TradeHistoryManager


@pytest.fixture
def trade_manager(tmp_path):
    # File-backed, not :memory: — the manager's pooled create_engine passes max_overflow,
    # which SQLite's in-memory SingletonThreadPool rejects (the very drift that got
    # test_trade_history.py quarantined).
    return TradeHistoryManager(f"sqlite:///{tmp_path}/trades.db")


def _store(mgr, trade_id, user_id=None):
    return mgr.store_trade(
        trade_id=trade_id,
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=50000.0,
        entry_time=datetime.now(),
        position_size=0.1,
        stop_loss=49000.0,
        take_profit_levels=[51000.0],
        risk_amount=100.0,
        user_id=user_id,
    )


def test_stored_trade_is_attributed_to_its_owner(trade_manager):
    _store(trade_manager, "trade_owned", user_id="userA")

    mine = trade_manager.get_recent_trades(user_id="userA")
    assert [t.trade_id for t in mine] == ["trade_owned"]
    # Another tenant's scoped read must not see it.
    assert trade_manager.get_recent_trades(user_id="userB") == []


def test_unattributed_rows_stay_invisible_to_scoped_reads(trade_manager):
    """A NULL-user row (legacy single-bot path) must never leak into a tenant's view."""
    _store(trade_manager, "trade_legacy", user_id=None)
    assert trade_manager.get_recent_trades(user_id="userA") == []
