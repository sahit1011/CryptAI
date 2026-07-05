"""Portfolio tracker locking + daily-roll regression tests.

Guards the non-reentrant-lock deadlock: check_correlation / reset_daily_stats held
self._lock and then awaited get_current_snapshot() (which re-acquires it), so the
correlation check always timed out after 5s and the limit was never enforced.
"""
import asyncio
import datetime as dt

import pytest

from src.risk.portfolio_state_tracker import PortfolioStateTracker


def _tracker(tmp_path):
    return PortfolioStateTracker(initial_balance=10000.0, snapshot_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_check_correlation_does_not_deadlock(tmp_path):
    t = _tracker(tmp_path)
    await t.add_position(
        position_id="p1", symbol="BTCUSDT", direction="LONG", entry_price=60000,
        position_size=0.1, stop_loss=59000, take_profit_levels=[62000],
        risk_amount=100.0,
    )
    # Must return well under the caller's 5s timeout (was deadlocking -> timeout).
    result = await asyncio.wait_for(t.check_correlation("ETHUSDT", "LONG"), timeout=1.0)
    assert result["has_correlation"] is True  # BTC/ETH are a correlated pair
    assert result["total_correlated_exposure"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_reset_daily_stats_does_not_deadlock(tmp_path):
    t = _tracker(tmp_path)
    await asyncio.wait_for(t.reset_daily_stats(), timeout=1.0)
    assert t.daily_trades == 0
    assert t.daily_start_equity == pytest.approx(10000.0)


@pytest.mark.asyncio
async def test_daily_roll_resets_on_new_day(tmp_path):
    t = _tracker(tmp_path)
    t.daily_trades = 5
    t.daily_start_date = dt.date(2000, 1, 1)  # force a stale day
    snap = await t.get_current_snapshot()      # triggers the day-boundary roll
    assert t.daily_trades == 0
    assert t.daily_start_date == dt.datetime.now().date()
    assert snap.daily_start_equity == pytest.approx(10000.0)
