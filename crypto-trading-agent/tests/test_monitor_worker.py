"""Per-position monitors: the dynamic stay-in vs exit decision (vision point 6).

Two layers:
  * evaluate_position — pure, exhaustive over the gates (no engine, no clock).
  * PositionMonitorWorker / MonitorSupervisor — against a real UserSession with an
    isolated paper engine (no Redis/Postgres), injected clock for the time stop.
"""
from datetime import datetime, timedelta

import pytest

from src.core.monitor_worker import (
    EXIT,
    EXIT_STATUS_TTL_SECONDS,
    HOLD,
    REASON_CONDITIONS,
    REASON_PROFIT_PROTECT,
    REASON_TIME_STOP,
    STATUS_TTL_SECONDS,
    MonitorConfig,
    MonitorState,
    MonitorSupervisor,
    PositionMonitorWorker,
    evaluate_position,
    favorable_return,
    monitor_status_key,
)
from src.core.multi_user import UserRegistry, UserRiskConfig, UserSession
from src.execution.paper_trading_engine import OrderSide

NOW = datetime(2026, 8, 3, 12, 0, 0)
CFG = MonitorConfig()

SETUP = {
    "symbol": "BTCUSDT", "direction": "LONG", "entry_price": 64000.0, "stop_loss": 62000.0,
    "take_profit_levels": [{"price": 68000.0, "size": 1.0}],
    "recommended_position_size": 0.05, "risk_amount": 100.0, "confidence_score": 0.72,
    "strategy_type": "SCALP",
}


# --- favorable_return --------------------------------------------------------

def test_favorable_return_is_direction_aware():
    assert favorable_return("LONG", 100.0, 101.0) == pytest.approx(0.01)
    assert favorable_return("LONG", 100.0, 99.0) == pytest.approx(-0.01)
    assert favorable_return("SHORT", 100.0, 99.0) == pytest.approx(0.01)
    assert favorable_return("SHORT", 100.0, 101.0) == pytest.approx(-0.01)
    assert favorable_return("LONG", 0.0, 101.0) == 0.0  # no divide-by-zero


# --- evaluate_position: the gates -------------------------------------------

def _eval(**kw):
    base = dict(
        direction="LONG", entry_price=64000.0, current_price=64000.0,
        opened_at=NOW, now=NOW, horizon="SCALP", pulse=None,
        state=MonitorState(), config=CFG,
    )
    base.update(kw)
    return evaluate_position(**base)


def test_holds_a_fresh_flat_position():
    decision, _ = _eval()
    assert decision.action == HOLD


def test_time_stop_fires_past_the_horizon_limit():
    # SCALP max hold is 30 min; 31 minutes in, still flat -> exit.
    decision, _ = _eval(now=NOW + timedelta(minutes=31))
    assert decision.action == EXIT
    assert decision.reason == REASON_TIME_STOP


def test_time_stop_respects_a_longer_horizon():
    # Same 31 minutes, but a SWING position is nowhere near its limit.
    decision, _ = _eval(horizon="SWING", now=NOW + timedelta(minutes=31))
    assert decision.action == HOLD


def test_missing_opened_at_disables_only_the_time_stop():
    decision, _ = _eval(opened_at=None, now=NOW + timedelta(days=30))
    assert decision.action == HOLD  # no time stop without an open time; other gates still run


def test_profit_protect_books_a_given_back_peak():
    # Run to +2% (arms the guard), then give back to +1.4% (>0.5% off the peak) -> exit.
    state = MonitorState()
    _, state = _eval(current_price=64000.0 * 1.02, state=state)
    assert state.peak_fav == pytest.approx(0.02)
    decision, _ = _eval(current_price=64000.0 * 1.014, state=state)
    assert decision.action == EXIT
    assert decision.reason == REASON_PROFIT_PROTECT


def test_profit_protect_does_not_arm_below_the_lock_threshold():
    # Peak only +0.5% (below the 0.8% lock), then flat: no exit.
    state = MonitorState()
    _, state = _eval(current_price=64000.0 * 1.005, state=state)
    decision, _ = _eval(current_price=64000.0, state=state)
    assert decision.action == HOLD


def test_a_small_wobble_after_a_peak_still_holds():
    state = MonitorState()
    _, state = _eval(current_price=64000.0 * 1.02, state=state)
    # Give back only 0.2% (< 0.5% threshold): stay in.
    decision, _ = _eval(current_price=64000.0 * 1.018, state=state)
    assert decision.action == HOLD


def test_deteriorating_conditions_exit_after_persistent_adverse_pulse():
    veto = {"vetoes": ["spread_too_wide"], "tradability": 0}
    state = MonitorState()
    for _ in range(CFG.adverse_exit_checks - 1):
        decision, state = _eval(pulse=veto, state=state)
        assert decision.action == HOLD  # streak building, not yet decisive
    decision, state = _eval(pulse=veto, state=state)
    assert decision.action == EXIT
    assert decision.reason == REASON_CONDITIONS


def test_a_single_adverse_read_does_not_exit():
    decision, state = _eval(pulse={"vetoes": ["x"]}, state=MonitorState())
    assert decision.action == HOLD
    assert state.adverse_streak == 1


def test_adverse_streak_resets_when_conditions_recover():
    state = MonitorState()
    _, state = _eval(pulse={"vetoes": ["x"]}, state=state)
    _, state = _eval(pulse={"vetoes": ["x"]}, state=state)
    assert state.adverse_streak == 2
    _, state = _eval(pulse={"vetoes": [], "tradability": 80}, state=state)
    assert state.adverse_streak == 0


def test_low_tradability_counts_as_adverse_even_without_a_veto():
    low = {"vetoes": [], "tradability": 10}  # below the 25 floor
    _, state = _eval(pulse=low, state=MonitorState())
    assert state.adverse_streak == 1


def test_a_missing_pulse_is_never_adverse():
    # The monitor must not exit on data it cannot see.
    _, state = _eval(pulse=None, state=MonitorState())
    assert state.adverse_streak == 0


# --- the worker against a real paper engine ---------------------------------

@pytest.fixture
def session():
    return UserSession("user-mon", config=UserRiskConfig(initial_balance=10_000.0))


async def _book(session, price=64000.0, setup=SETUP):
    await session.engine.check_limit_orders(setup["symbol"], price)  # seed a live price
    result = await session.evaluate_and_book(setup)
    assert result["approved"]


@pytest.mark.asyncio
async def test_worker_reports_closed_when_there_is_no_position(session):
    worker = PositionMonitorWorker(session, "BTCUSDT")
    assert await worker.check_once() == "closed"


@pytest.mark.asyncio
async def test_worker_holds_a_healthy_position(session):
    await _book(session)
    worker = PositionMonitorWorker(session, "BTCUSDT", now_fn=lambda: NOW)
    # Give it an opened_at inside the clock we injected so the time stop is inert.
    session.portfolio.positions[list(session.portfolio.positions)[0]].opened_at = NOW
    assert await worker.check_once() == "hold"
    assert len(session.engine.get_positions()) == 1


@pytest.mark.asyncio
async def test_worker_exits_a_stale_position_and_the_engine_settles_it(session):
    await _book(session)
    pos_id = list(session.portfolio.positions)[0]
    session.portfolio.positions[pos_id].opened_at = NOW
    # 40 minutes later — past the SCALP time stop.
    worker = PositionMonitorWorker(session, "BTCUSDT", now_fn=lambda: NOW + timedelta(minutes=40))

    assert await worker.check_once() == "exit"
    # The engine's reduce-only close settled the position, and the M1 close hook flowed
    # it back into the tracker.
    assert session.engine.get_positions() == []
    assert await session.portfolio.get_position_count() == 0


@pytest.mark.asyncio
async def test_worker_skips_when_there_is_no_live_price(session):
    # Book, then wipe the engine's last price so the worker cannot evaluate.
    await _book(session)
    session.engine.current_prices.clear()
    session.engine.positions["BTCUSDT"].current_price = 0.0
    worker = PositionMonitorWorker(session, "BTCUSDT")
    assert await worker.check_once() == "skipped"
    assert len(session.engine.get_positions()) == 1  # untouched


@pytest.mark.asyncio
async def test_state_resets_when_a_new_position_reuses_the_symbol(session):
    """The bleed regression: a monitor keyed by (user, symbol) carried the closed
    position's profit peak into a fresh position on the same symbol, exiting it on its
    first tick. Reproduces the exact sequence: run to a peak, close, reopen, check."""
    await _book(session)
    worker = PositionMonitorWorker(session, "BTCUSDT", now_fn=lambda: NOW)
    first_id = session.engine.positions["BTCUSDT"].position_id
    session.portfolio.positions[first_id].opened_at = NOW

    # Position A runs to a ~+2% peak.
    session.engine.current_prices["BTCUSDT"] = 64000.0 * 1.02
    session.engine.positions["BTCUSDT"].current_price = 64000.0 * 1.02
    assert await worker.check_once() == "hold"
    assert worker.state.peak_fav > 0.015

    # A closes; a brand-new B opens on the same symbol, healthy at ~+0.1%.
    qty = session.engine.positions["BTCUSDT"].quantity
    await session.engine.close_position("BTCUSDT", OrderSide.SELL, qty)
    await session.engine.check_limit_orders("BTCUSDT", 64000.0)
    await session.evaluate_and_book(SETUP)
    second_id = session.engine.positions["BTCUSDT"].position_id
    assert second_id != first_id
    session.portfolio.positions[second_id].opened_at = NOW
    session.engine.current_prices["BTCUSDT"] = 64000.0 * 1.001
    session.engine.positions["BTCUSDT"].current_price = 64000.0 * 1.001

    # The monitor's first observation of B must HOLD — the old peak was reset, not
    # carried, so profit_protect does not fire on a fresh healthy position.
    assert await worker.check_once() == "hold"
    assert len(session.engine.get_positions()) == 1
    assert worker.state.peak_fav < 0.01  # B's own small peak, not A's


@pytest.mark.asyncio
async def test_worker_exits_short_positions_with_a_buy(session):
    short = {**SETUP, "direction": "SHORT", "entry_price": 64000.0,
             "stop_loss": 66000.0, "take_profit_levels": [{"price": 60000.0, "size": 1.0}]}
    await _book(session, setup=short)
    pos_id = list(session.portfolio.positions)[0]
    session.portfolio.positions[pos_id].opened_at = NOW
    worker = PositionMonitorWorker(session, "BTCUSDT", now_fn=lambda: NOW + timedelta(minutes=40))
    assert await worker.check_once() == "exit"
    assert session.engine.get_positions() == []


# --- status publishing -------------------------------------------------------

class _FakeState:
    """Records set() calls the way StateManager stores them (key without the state: prefix)."""

    def __init__(self):
        self.store: dict = {}
        self.writes: list = []

    async def set(self, key, value, ttl=None):
        self.store[key] = value
        self.writes.append((key, value, ttl))

    async def get(self, key):
        return self.store.get(key)


@pytest.mark.asyncio
async def test_worker_publishes_a_hold_status(session):
    await _book(session)
    pos_id = list(session.portfolio.positions)[0]
    session.portfolio.positions[pos_id].opened_at = NOW
    state = _FakeState()
    worker = PositionMonitorWorker(session, "BTCUSDT", now_fn=lambda: NOW, state_manager=state)

    assert await worker.check_once() == "hold"
    key = monitor_status_key("user-mon", "BTCUSDT")
    status = state.store[key]
    assert status["decision"] == "hold"
    assert status["reason"] is None
    assert status["symbol"] == "BTCUSDT"
    assert status["checks"] == 1
    # A live hold status carries the short TTL so a dead worker goes stale, not stuck-on.
    assert state.writes[-1][2] == STATUS_TTL_SECONDS


@pytest.mark.asyncio
async def test_worker_publishes_an_exit_status_with_reason_and_longer_ttl(session):
    await _book(session)
    pos_id = list(session.portfolio.positions)[0]
    session.portfolio.positions[pos_id].opened_at = NOW
    state = _FakeState()
    worker = PositionMonitorWorker(
        session, "BTCUSDT", now_fn=lambda: NOW + timedelta(minutes=40), state_manager=state
    )

    assert await worker.check_once() == "exit"
    status = state.store[monitor_status_key("user-mon", "BTCUSDT")]
    assert status["decision"] == "exit"
    assert status["reason"] == REASON_TIME_STOP
    # Exit status lingers past the position it closed so the UI can show why.
    assert state.writes[-1][2] == EXIT_STATUS_TTL_SECONDS


@pytest.mark.asyncio
async def test_publishing_is_best_effort(session):
    """A status-write failure must never affect the monitoring decision."""
    class _BrokenState:
        async def set(self, *a, **k):
            raise RuntimeError("redis down")

    await _book(session)
    pos_id = list(session.portfolio.positions)[0]
    session.portfolio.positions[pos_id].opened_at = NOW
    worker = PositionMonitorWorker(
        session, "BTCUSDT", now_fn=lambda: NOW, state_manager=_BrokenState()
    )
    assert await worker.check_once() == "hold"  # decision still made, no raise


# --- the supervisor ----------------------------------------------------------

@pytest.mark.asyncio
async def test_supervisor_spawns_one_monitor_per_open_position():
    reg = UserRegistry(config_for=lambda uid: UserRiskConfig(initial_balance=10_000.0))
    a = reg.session("userA")
    await _book(a)
    sup = MonitorSupervisor(reg)

    live = await sup.discover_once()
    assert live == 1
    assert "userA:BTCUSDT" in sup.monitors

    # Idempotent: a second pass does not double-spawn.
    assert await sup.discover_once() == 1
    await sup.stop()


@pytest.mark.asyncio
async def test_supervisor_reaps_a_monitor_once_its_position_closes():
    reg = UserRegistry(config_for=lambda uid: UserRiskConfig(initial_balance=10_000.0))
    a = reg.session("userA")
    await _book(a)
    sup = MonitorSupervisor(reg)
    await sup.discover_once()

    # Close the position out from under the monitor (as the SL/TP tick would).
    qty = a.engine.positions["BTCUSDT"].quantity
    await a.engine.close_position("BTCUSDT", OrderSide.SELL, qty)
    # Let the worker's next check observe the empty book and finish.
    task = sup.monitors["userA:BTCUSDT"]
    await task

    assert await sup.discover_once() == 0
    assert sup.monitors == {}
    await sup.stop()


@pytest.mark.asyncio
async def test_supervisor_handles_a_live_engine_with_no_discoverable_positions():
    """LiveExecutionEngine.get_positions() is still a stub returning []. A live-mode
    tenant must not spawn a monitor and must not crash the pass — and the gap is warned
    once, not every discovery tick."""
    from types import SimpleNamespace

    class _LiveEngine:
        def get_positions(self):
            return []

    live_session = SimpleNamespace(
        user_id="live-user", engine=_LiveEngine(), portfolio=None, is_live=True
    )

    class _Reg:
        def active_user_ids(self):
            return ["live-user"]

        def session(self, uid):
            return live_session

    sup = MonitorSupervisor(_Reg())
    assert await sup.discover_once() == 0
    assert sup.monitors == {}
    assert "live-user" in sup._unmonitorable_warned  # gap made visible
    assert await sup.discover_once() == 0  # idempotent, no re-warn/crash
    await sup.stop()


@pytest.mark.asyncio
async def test_supervisor_isolates_tenants():
    reg = UserRegistry(config_for=lambda uid: UserRiskConfig(initial_balance=10_000.0))
    a = reg.session("userA")
    reg.session("userB")  # materialized but no position
    await _book(a)
    sup = MonitorSupervisor(reg)
    await sup.discover_once()
    assert set(sup.monitors) == {"userA:BTCUSDT"}
    await sup.stop()
