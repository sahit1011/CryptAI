"""Paper brackets self-manage: price ticks fill SL/TP legs and sweep the OCO twin.

No Redis/bus/network — bare in-memory paper engines through the same UserSession
booking path the daemon uses (the test_multi_user.py pattern).
"""
import pytest

from src.core.multi_user import UserSession, UserRiskConfig
from src.core.paper_tick import process_engine_tick, sweep_orphaned_legs
from src.risk.deterministic_risk_calculator import RiskParameters


def _session() -> UserSession:
    # Generous limits so the risk gate approves the tiny test brackets.
    params = RiskParameters(max_risk_per_trade=0.05, min_risk_reward_ratio=0.1)
    return UserSession("tick-user", config=UserRiskConfig(initial_balance=100_000.0, risk_params=params))


async def _book_long(session: UserSession, entry=100.0, stop=95.0, tp=103.0):
    engine = session.engine
    # Seed the live price (fresh engines refuse to fill without one — by design).
    await engine.check_limit_orders("BTCUSDT", entry)
    result = await session.evaluate_and_book({
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit_levels": [tp],
        "confidence_score": 0.9,
        "recommended_position_size": 10.0,  # 10 units @ ~$100 = $1k notional
        "risk_amount": 50.0,
    })
    assert result.get("approved"), f"booking rejected: {result}"
    return engine


@pytest.mark.asyncio
async def test_tp_fill_closes_position_and_sweep_kills_sl():
    # Arrange — a LONG bracket with both legs resting.
    session = _session()
    engine = await _book_long(session)
    assert "BTCUSDT" in engine.positions
    assert len(engine.get_open_orders()) == 2  # SL + TP

    balance_before = engine.balance

    # Act — price crosses the take-profit.
    changed = await process_engine_tick(engine, {"BTCUSDT": 103.5})
    swept = await sweep_orphaned_legs(engine)

    # Assert — position closed at TP, profit realized, orphan SL swept.
    assert changed is True
    assert "BTCUSDT" not in engine.positions
    assert engine.balance > balance_before  # ~(103-100)*qty realized
    assert swept == 1
    assert engine.get_open_orders() == []
    assert engine.total_trades >= 1


@pytest.mark.asyncio
async def test_sl_trigger_closes_position_and_sweep_kills_tp():
    # Arrange
    session = _session()
    engine = await _book_long(session)
    balance_before = engine.balance

    # Act — price crashes through the stop.
    changed = await process_engine_tick(engine, {"BTCUSDT": 94.5})
    swept = await sweep_orphaned_legs(engine)

    # Assert — stop triggered, loss realized honestly, orphan TP swept.
    assert changed is True
    assert "BTCUSDT" not in engine.positions
    assert engine.balance < balance_before
    assert swept == 1
    assert engine.get_open_orders() == []


@pytest.mark.asyncio
async def test_uncrossed_tick_marks_to_market_without_fills():
    # Arrange
    session = _session()
    engine = await _book_long(session)

    # Act — price drifts but crosses nothing.
    changed = await process_engine_tick(engine, {"BTCUSDT": 101.0})

    # Assert — no fills, both legs resting, position marked to the new price.
    assert changed is False
    assert len(engine.get_open_orders()) == 2
    position = engine.positions["BTCUSDT"]
    assert position.current_price == pytest.approx(101.0)
    assert position.unrealized_pnl > 0  # long, price above entry


@pytest.mark.asyncio
async def test_junk_prices_and_foreign_symbols_are_ignored():
    session = _session()
    engine = await _book_long(session)

    changed = await process_engine_tick(engine, {"ETHUSDT": 2000.0, "BTCUSDT": "junk", "XAUTUSDT": -5})

    assert changed is False
    assert "BTCUSDT" in engine.positions
    assert len(engine.get_open_orders()) == 2


@pytest.mark.asyncio
async def test_sweep_leaves_legs_of_open_positions_alone():
    # A resting bracket whose position is still open must never be swept.
    session = _session()
    engine = await _book_long(session)

    swept = await sweep_orphaned_legs(engine)

    assert swept == 0
    assert len(engine.get_open_orders()) == 2
