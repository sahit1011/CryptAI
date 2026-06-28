"""
Unit tests for PortfolioStateTracker persistence + startup reconciliation.

Covers the Phase 1b fix where risk/portfolio state was kept only in memory and
silently reset to zero on restart (bypassing risk limits / dangling positions).
"""
import pytest
from datetime import datetime
from types import SimpleNamespace

from src.risk.portfolio_state_tracker import PortfolioStateTracker


def _exchange_position(symbol, side, quantity, entry_price, mark_price=None,
                       unrealized_pnl=0.0, leverage=1):
    """Build an object shaped like exchange_client.Position (duck-typed)."""
    return SimpleNamespace(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        mark_price=mark_price if mark_price is not None else entry_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
    )


class _MockExchange:
    """Minimal mock exposing get_open_positions()."""

    def __init__(self, positions):
        self._positions = positions
        self.calls = 0

    async def get_open_positions(self):
        self.calls += 1
        return list(self._positions)


@pytest.fixture
def tracker(tmp_path):
    """Tracker with an isolated snapshot dir per test."""
    return PortfolioStateTracker(
        initial_balance=10000.0,
        snapshot_dir=str(tmp_path / "snapshots")
    )


@pytest.mark.asyncio
async def test_mutation_persists_latest_snapshot(tracker):
    """Adding a position should write the stable 'latest' snapshot file."""
    await tracker.add_position(
        position_id='pos_1', symbol='BTCUSDT', direction='LONG',
        entry_price=40000, position_size=0.1, stop_loss=39000,
        take_profit_levels=[42000], risk_amount=100,
    )
    latest = tracker.snapshot_dir / PortfolioStateTracker.LATEST_SNAPSHOT_FILENAME
    assert latest.exists()


@pytest.mark.asyncio
async def test_reload_restores_open_positions(tracker, tmp_path):
    """A fresh tracker should reload open positions from the persisted snapshot."""
    await tracker.add_position(
        position_id='pos_1', symbol='BTCUSDT', direction='LONG',
        entry_price=40000, position_size=0.1, stop_loss=39000,
        take_profit_levels=[42000], risk_amount=100,
    )
    assert await tracker.get_position_count() == 1

    # Simulate restart: brand-new tracker pointing at same snapshot dir.
    restarted = PortfolioStateTracker(
        initial_balance=10000.0,
        snapshot_dir=str(tracker.snapshot_dir)
    )
    assert await restarted.get_position_count() == 0  # nothing loaded yet

    summary = await restarted.reconcile_on_startup(live_mode=False)
    assert summary['snapshot_loaded'] is True
    assert summary['exchange_queried'] is False  # paper mode: no exchange call
    assert await restarted.get_position_count() == 1


@pytest.mark.asyncio
async def test_paper_mode_does_not_call_exchange(tracker):
    """Paper-mode reconciliation must never touch the exchange."""
    exch = _MockExchange([_exchange_position('ETHUSDT', 'LONG', 1, 2000)])
    tracker.set_exchange(exch)
    summary = await tracker.reconcile_on_startup(live_mode=False)
    assert exch.calls == 0
    assert summary['exchange_queried'] is False


@pytest.mark.asyncio
async def test_live_reconcile_detects_ghost_and_missing(tracker):
    """LIVE mode: rebuild from exchange and report drift in both directions."""
    # Snapshot has BTC (ghost: not on exchange) ...
    await tracker.add_position(
        position_id='pos_btc', symbol='BTCUSDT', direction='LONG',
        entry_price=40000, position_size=0.1, stop_loss=39000,
        take_profit_levels=[42000], risk_amount=100,
    )
    # ... exchange reports ETH instead (missing from snapshot).
    exch = _MockExchange([
        _exchange_position('ETHUSDT', 'LONG', 1.0, 2000, mark_price=2100,
                           unrealized_pnl=100.0)
    ])
    tracker.set_exchange(exch)

    summary = await tracker.reconcile_on_startup(live_mode=True)

    assert exch.calls == 1
    assert summary['exchange_queried'] is True
    assert summary['drift_detected'] is True
    assert 'BTCUSDT' in summary['ghost_positions']
    assert 'ETHUSDT' in summary['missing_positions']

    # Authoritative state now mirrors the exchange: only ETH, no ghost BTC.
    symbols = {p.symbol for p in tracker.positions.values()}
    assert symbols == {'ETHUSDT'}


@pytest.mark.asyncio
async def test_live_reconcile_preserves_matching_risk_metadata(tracker):
    """When a symbol matches, keep snapshot risk metadata, refresh live price/PnL."""
    await tracker.add_position(
        position_id='pos_eth', symbol='ETHUSDT', direction='LONG',
        entry_price=2000, position_size=1.0, stop_loss=1900,
        take_profit_levels=[2200], risk_amount=100,
    )
    exch = _MockExchange([
        _exchange_position('ETHUSDT', 'LONG', 1.0, 2000, mark_price=2050,
                           unrealized_pnl=50.0)
    ])
    tracker.set_exchange(exch)

    summary = await tracker.reconcile_on_startup(live_mode=True)
    assert summary['drift_detected'] is False

    pos = next(iter(tracker.positions.values()))
    assert pos.stop_loss == 1900          # preserved from snapshot
    assert pos.risk_amount == 100         # preserved from snapshot
    assert pos.current_price == 2050      # refreshed from exchange
    assert pos.unrealized_pnl == 50.0     # refreshed from exchange


@pytest.mark.asyncio
async def test_reconcile_never_raises_on_exchange_failure(tracker):
    """A failing exchange call must not crash startup; error is captured."""
    class _BrokenExchange:
        async def get_open_positions(self):
            raise RuntimeError("network down")

    tracker.set_exchange(_BrokenExchange())
    summary = await tracker.reconcile_on_startup(live_mode=True)
    assert summary['error'] is not None  # captured, not raised
