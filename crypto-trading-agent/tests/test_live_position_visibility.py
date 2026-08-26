"""Live positions must be VISIBLE to the monitor — or honestly reported as unknown.

The hole this closes: `LiveExecutionEngine.get_positions()` was a stub returning `[]`,
and both monitor discovery and rehydration are position-driven. So an auto+keys user's
position had no time stop, no profit protection, and vanished from the engine's view on
restart. The venue always had the data (`ExchangeClient.get_open_positions`); nothing
read it.

The design rule under test: **a position list we cannot confirm is reported as nothing,
never as stale truth.** Managing a phantom that was already closed at the venue is worse
than admitting we do not know — and `/api/monitors` already renders "we don't know" as
`monitored: false`.
"""
from unittest.mock import AsyncMock

import pytest

from src.execution.exchange_client import Position
from src.execution.live_execution_engine import LiveExecutionEngine, POSITION_CACHE_TTL_S


def _engine(client) -> LiveExecutionEngine:
    e = LiveExecutionEngine.__new__(LiveExecutionEngine)
    e.user_id = "live-user"
    e.exchange_name = "bingx"
    e.message_bus = None
    e.state_manager = None
    e.client = client
    e._positions_cache = []
    e._positions_cached_at = 0.0
    return e


def _position(symbol="BTCUSDT", qty=0.5, side="LONG"):
    return Position(symbol=symbol, side=side, quantity=qty, entry_price=64000.0,
                    mark_price=64500.0, unrealized_pnl=250.0, leverage=5)


@pytest.mark.asyncio
async def test_venue_positions_become_visible_in_the_paper_engine_shape():
    client = AsyncMock()
    client.get_open_positions.return_value = [_position()]
    e = _engine(client)

    assert e.get_positions() == [], "nothing is known before the first refresh"
    assert await e.refresh_positions() == 1

    pos = e.get_positions()
    assert len(pos) == 1
    # Same shape the paper engine publishes, so the monitor and dashboard need no
    # per-engine special cases.
    assert pos[0]["symbol"] == "BTCUSDT"
    assert pos[0]["positionSide"] == "LONG"
    assert float(pos[0]["positionAmt"]) == 0.5
    assert float(pos[0]["entryPrice"]) == 64000.0
    assert pos[0]["live"] is True
    assert pos[0]["position_id"]  # monitors key on this


@pytest.mark.asyncio
async def test_a_stale_cache_reports_nothing_rather_than_a_possible_phantom():
    import time as _time

    client = AsyncMock()
    client.get_open_positions.return_value = [_position()]
    e = _engine(client)
    await e.refresh_positions()
    assert len(e.get_positions()) == 1

    # Age the cache past its TTL.
    e._positions_cached_at = _time.monotonic() - (POSITION_CACHE_TTL_S + 1)
    assert e.get_positions() == [], "an unconfirmable position must not be managed"


@pytest.mark.asyncio
async def test_a_transient_venue_error_does_not_erase_known_positions():
    """Clearing the cache on a blip would tell the monitor 'nothing to watch' — the
    exact silence this work removes. The cache ages out instead."""
    client = AsyncMock()
    client.get_open_positions.return_value = [_position()]
    e = _engine(client)
    await e.refresh_positions()

    client.get_open_positions.side_effect = ConnectionError("venue timeout")
    assert await e.refresh_positions() == 1        # reports what it still holds
    assert len(e.get_positions()) == 1             # and keeps serving it while fresh


@pytest.mark.asyncio
async def test_flat_positions_are_not_reported_as_open():
    client = AsyncMock()
    client.get_open_positions.return_value = [_position(qty=0.0), _position(symbol="ETHUSDT")]
    e = _engine(client)
    assert await e.refresh_positions() == 1
    assert [p["symbol"] for p in e.get_positions()] == ["ETHUSDT"]


@pytest.mark.asyncio
async def test_rehydration_reconciles_a_live_session_from_the_venue():
    """A restart mid-position must not leave a blind window: the boot pass pulls the
    venue's open positions instead of skipping live sessions outright."""
    from src.multi_user_daemon import MultiUserTradingDaemon

    client = AsyncMock()
    client.get_open_positions.return_value = [_position()]
    engine = _engine(client)

    session = type("S", (), {})()
    session.user_id = "live-user"
    session.engine = engine
    session.is_live = True
    session.rehydrated = False

    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d.trade_manager = None
    d.state_manager = None
    await d._rehydrate_one(session)

    assert session.rehydrated is True
    assert len(engine.get_positions()) == 1, "the venue read must have happened at boot"
