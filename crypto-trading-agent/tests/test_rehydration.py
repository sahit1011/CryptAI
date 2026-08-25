"""R2.1 — open paper positions and their brackets survive a process restart.

The doctrine under test: persisted `trades` rows are the source of truth; the
engine is rebuilt from them; trading stays refused until a user's pass completes;
and the restored SL/TP legs actually FIRE — a restored position that can't close
itself is the orphan this task exists to end.

The "restart" is real: trades are booked through UserSession into engine A and
persisted through the real TradeLedgerConsumer into sqlite (the same consumer that
fixes the P0 found during scoping — production dropped every trade row because
only the disabled MemoryAgent subscribed to the inbox). Then a FRESH UserSession B
rehydrates from those rows. No Redis, no bus beyond a capture stub, no Postgres.
"""
import inspect

import pytest

from src.core.multi_user import UserRegistry, UserRiskConfig, UserSession
from src.core.paper_tick import process_engine_tick, sweep_orphaned_legs
from src.core.rehydration import diff_mirror, load_trades
from src.core.trade_ledger import TradeLedgerConsumer
from src.memory.trade_history_manager import TradeHistoryManager
from src.risk.deterministic_risk_calculator import RiskParameters


class CaptureBus:
    """Collects publishes; lets tests pump memory_agent_inbox into the ledger."""

    def __init__(self):
        self.messages = []

    async def publish(self, channel, message):
        self.messages.append((channel, message))

    def drain_inbox(self):
        out = [m for c, m in self.messages if c == "memory_agent_inbox"]
        self.messages = [(c, m) for c, m in self.messages if c != "memory_agent_inbox"]
        return out


@pytest.fixture()
def store(tmp_path):
    return TradeHistoryManager(f"sqlite:///{tmp_path}/trades.db")


@pytest.fixture()
def ledger(store):
    consumer = TradeLedgerConsumer.__new__(TradeLedgerConsumer)
    consumer.trade_history = store
    consumer.rows_written = 0
    consumer.rows_updated = 0
    return consumer


def _session(user_id="rehydrate-user", bus=None) -> UserSession:
    params = RiskParameters(max_risk_per_trade=0.05, min_risk_reward_ratio=0.1)
    return UserSession(
        user_id,
        message_bus=bus,
        config=UserRiskConfig(initial_balance=100_000.0, risk_params=params, leverage=7),
    )


async def _pump(bus: CaptureBus, ledger: TradeLedgerConsumer):
    for message in bus.drain_inbox():
        await ledger.handle(message)


async def _book_long(session, entry=100.0, stop=95.0, tps=None, symbol="BTCUSDT"):
    await session.engine.check_limit_orders(symbol, entry)
    result = await session.evaluate_and_book({
        "symbol": symbol,
        "direction": "LONG",
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit_levels": tps or [{"price": 103.0, "size": 1.0}],
        "confidence_score": 0.9,
        "recommended_position_size": 10.0,
        "risk_amount": 50.0,
    })
    assert result.get("approved"), f"booking rejected: {result}"


async def _restart(store, user_id="rehydrate-user", bus=None) -> UserSession:
    """A fresh process: new session, empty engine, rehydrated from rows."""
    fresh = _session(user_id, bus=bus)
    fresh.rehydrated = False
    await fresh.rehydrate(store)
    assert fresh.rehydrated is True
    return fresh


# --------------------------------------------------------------------------- #
# the ledger itself (the P0: rows must persist without the memory agent)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_ledger_persists_booking_and_exit(store, ledger):
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session)
    await _pump(bus, ledger)

    rows = store.get_recent_trades(user_id="rehydrate-user")
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "OPEN" and row.exit_time is None
    assert row.leverage == 7                      # threaded, not fabricated
    assert row.entry_order_id and row.sl_order_id  # bracket identity persisted
    assert row.tp_order_ids and row.tp_order_ids[0]["size"] == pytest.approx(1.0)

    # close via the engine's own stop path -> update_trade -> ledger -> CLOSED row
    await process_engine_tick(session.engine, {"BTCUSDT": 94.0})
    await _pump(bus, ledger)
    row = store.get_recent_trades(user_id="rehydrate-user")[0]
    assert row.status == "CLOSED" and row.exit_time is not None
    assert row.pnl < 0


@pytest.mark.asyncio
async def test_ledger_survives_garbage(ledger):
    await ledger.handle({"type": "update_trade", "payload": {"trade_id": "missing"}})
    await ledger.handle({"type": "something_else", "payload": {}})
    await ledger.handle({})  # never raises — the bus loop must outlive bad messages


# --------------------------------------------------------------------------- #
# the restart itself
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_open_position_rebuilt_from_rows(store, ledger):
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session)
    await _pump(bus, ledger)
    booked = session.engine.positions["BTCUSDT"]

    fresh = await _restart(store)
    restored = fresh.engine.positions["BTCUSDT"]
    assert restored.side == "LONG"
    assert restored.quantity == pytest.approx(booked.quantity)
    assert restored.entry_price == pytest.approx(booked.entry_price)
    assert restored.leverage == 7
    assert restored.position_id == booked.position_id  # POS_{trade_id} — close path joins on it
    assert restored.opened_at is not None


@pytest.mark.asyncio
async def test_rehydrated_stop_actually_fires(store, ledger):
    """THE acceptance test: the restored SL leg closes the position on a tick,
    P&L books, the surviving TP twin is swept, and the ROW records the exit."""
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session, entry=100.0, stop=95.0)
    await _pump(bus, ledger)

    fresh_bus = CaptureBus()
    fresh = await _restart(store, bus=fresh_bus)
    legs = fresh.engine.get_open_orders()
    assert len(legs) == 2 and all(o["reduceOnly"] for o in legs)

    balance_before = fresh.engine.balance
    changed = await process_engine_tick(fresh.engine, {"BTCUSDT": 94.0})
    swept = await sweep_orphaned_legs(fresh.engine)
    assert changed is True
    assert "BTCUSDT" not in fresh.engine.positions
    assert fresh.engine.balance < balance_before  # the loss actually settled
    assert swept == 1 and fresh.engine.get_open_orders() == []

    await _pump(fresh_bus, ledger)  # the close flowed to the ledger like any other
    row = store.get_recent_trades(user_id="rehydrate-user")[0]
    assert row.status == "CLOSED" and row.exit_price is not None


@pytest.mark.asyncio
async def test_rehydrated_tp_fills_and_sibling_sl_swept(store, ledger):
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session, tps=[{"price": 103.0, "size": 0.6}, {"price": 106.0, "size": 0.4}])
    await _pump(bus, ledger)

    fresh = await _restart(store)
    tp_legs = [o for o in fresh.engine.get_open_orders() if o["type"] == "LIMIT"]
    assert sorted(float(o["origQty"]) for o in tp_legs) == pytest.approx(
        sorted([0.4 * 10.0, 0.6 * 10.0])
    )  # per-leg QUANTITY FRACTIONS survived the restart — not an even split

    await process_engine_tick(fresh.engine, {"BTCUSDT": 103.5})   # first TP fills
    assert fresh.engine.positions["BTCUSDT"].quantity == pytest.approx(4.0)
    await process_engine_tick(fresh.engine, {"BTCUSDT": 106.5})   # second TP closes
    swept = await sweep_orphaned_legs(fresh.engine)
    assert "BTCUSDT" not in fresh.engine.positions
    assert swept == 1  # the SL twin is gone


@pytest.mark.asyncio
async def test_closed_trades_are_not_resurrected(store, ledger):
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session)
    await process_engine_tick(session.engine, {"BTCUSDT": 94.0})  # closed pre-restart
    await _pump(bus, ledger)

    fresh = await _restart(store)
    assert fresh.engine.positions == {}
    assert fresh.engine.get_open_orders() == []
    assert fresh.engine.total_trades == 1  # counted in history, not re-opened


@pytest.mark.asyncio
async def test_rehydration_is_user_scoped(store, ledger):
    for uid in ("tenant-a", "tenant-b"):
        bus = CaptureBus()
        s = _session(uid, bus=bus)
        await _book_long(s, symbol="BTCUSDT" if uid == "tenant-a" else "ETHUSDT")
        await _pump(bus, ledger)

    fresh_a = await _restart(store, "tenant-a")
    assert set(fresh_a.engine.positions) == {"BTCUSDT"}  # never tenant-b's ETH

    with pytest.raises(ValueError):
        load_trades(store, None)  # unscoped loads are opt-in, legacy-only (G6)


@pytest.mark.asyncio
async def test_balance_and_counters_reconstructed(store, ledger):
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session, entry=100.0, stop=95.0)
    await process_engine_tick(session.engine, {"BTCUSDT": 103.5})  # win
    await sweep_orphaned_legs(session.engine)
    await _pump(bus, ledger)

    fresh = await _restart(store)
    assert fresh.engine.total_trades == 1
    assert fresh.engine.winning_trades == 1
    # Commission is ESTIMATED (no commission column yet), so compare loosely:
    # the reconstructed balance reflects the win, not a reset.
    assert fresh.engine.balance > fresh.engine.initial_balance
    assert fresh.engine.balance == pytest.approx(session.engine.balance, rel=0.01)


@pytest.mark.asyncio
async def test_zombie_mirror_positions_are_reported():
    class Row:
        symbol = "BTCUSDT"
    zombies = diff_mirror([Row()], [{"symbol": "BTCUSDT"}, {"symbol": "DOGEUSDT"}])
    assert zombies == ["DOGEUSDT"]  # in the mirror, not in the rows -> named, then dropped


@pytest.mark.asyncio
async def test_booking_refused_until_rehydrated(store, ledger):
    session = _session()
    session.rehydrated = False  # what the daemon/registry sets at materialization
    result = await session.evaluate_and_book({
        "symbol": "BTCUSDT", "direction": "LONG", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit_levels": [103.0],
        "recommended_position_size": 10.0, "risk_amount": 50.0,
    })
    assert result["approved"] is False
    assert "rehydrat" in " ".join(result["reasons"]).lower()

    await session.rehydrate(store)  # empty store — completes, unblocks
    await session.engine.check_limit_orders("BTCUSDT", 100.0)
    result = await session.evaluate_and_book({
        "symbol": "BTCUSDT", "direction": "LONG", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit_levels": [103.0],
        "confidence_score": 0.9, "recommended_position_size": 10.0, "risk_amount": 50.0,
    })
    assert result.get("approved") is True


@pytest.mark.asyncio
async def test_registry_hook_blocks_new_sessions_and_schedules_rehydration():
    registry = UserRegistry(seed_user_ids=["late-user"])
    scheduled = []
    registry.on_session_created = scheduled.append
    s = registry.session("late-user")
    assert s.rehydrated is False  # blocked SYNCHRONOUSLY, before any async pass
    assert scheduled == [s]


@pytest.mark.asyncio
async def test_scheduled_passes_are_strongly_referenced(store):
    """A bare create_task can be GC'd mid-flight, stranding that user
    booking-blocked with no error. The daemon must hold the reference."""
    import asyncio as aio

    from src.multi_user_daemon import MultiUserTradingDaemon

    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d.registry = UserRegistry(seed_user_ids=["late-user"])
    d.state_manager = None
    d.trade_manager = store
    d._rehydrate_tasks = set()

    def hook(session):
        task = aio.get_running_loop().create_task(d._rehydrate_one(session))
        d._rehydrate_tasks.add(task)
        task.add_done_callback(d._rehydrate_tasks.discard)
    d.registry.on_session_created = hook

    s = d.registry.session("late-user")
    assert len(d._rehydrate_tasks) == 1  # referenced while pending
    await aio.gather(*d._rehydrate_tasks)
    assert s.rehydrated is True
    assert d._rehydrate_tasks == set()   # and released when done


@pytest.mark.asyncio
async def test_failure_is_isolated_per_user(store, ledger, monkeypatch):
    """One tenant's broken pass leaves THEM blocked; the other tenant trades."""
    from src.multi_user_daemon import MultiUserTradingDaemon

    bus = CaptureBus()
    ok = _session("tenant-ok", bus=bus)
    await _book_long(ok)
    await _pump(bus, ledger)

    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d.registry = UserRegistry(seed_user_ids=["tenant-ok", "tenant-broken"])
    d.state_manager = None
    d.trade_manager = store
    broken = d.registry.session("tenant-broken")
    fine = d.registry.session("tenant-ok")
    for s in (broken, fine):
        s.rehydrated = False

    async def explode(_mgr):
        raise RuntimeError("malformed row")
    monkeypatch.setattr(broken, "rehydrate", explode)

    await d._rehydrate_one(broken)
    await d._rehydrate_one(fine)
    assert broken.rehydrated is False   # fail-closed: still booking-blocked
    assert fine.rehydrated is True
    assert set(fine.engine.positions) == {"BTCUSDT"}


@pytest.mark.asyncio
async def test_tracker_keeps_original_entry_time(store, ledger):
    """The monitor's time stop must measure from the real open, not from boot."""
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session)
    await _pump(bus, ledger)
    row = store.get_recent_trades(user_id="rehydrate-user")[0]

    fresh = await _restart(store)
    tracked = list(fresh.portfolio.positions.values())
    assert len(tracked) == 1
    assert tracked[0].opened_at == row.entry_time
    assert tracked[0].position_id == f"POS_{row.trade_id}"


def test_boot_ordering_is_wired():
    """Wiring-law tripwire: rehydration must run before the command channel and the
    tick/stream/monitor tasks — the ordering the whole design depends on."""
    from src.multi_user_daemon import MultiUserTradingDaemon

    src = inspect.getsource(MultiUserTradingDaemon.start)
    rehydrate_at = src.index("_rehydrate_engines")
    assert rehydrate_at < src.index('subscribe("user_commands"')
    assert rehydrate_at < src.index("_price_tick_loop")
    assert rehydrate_at < src.index("MonitorSupervisor(")  # the construction, not prose


@pytest.mark.asyncio
async def test_unprotected_row_restores_with_loud_warning(store, ledger):
    """A row without a stop still restores (the position exists and must be seen),
    but the report says UNPROTECTED — silence here would hide a naked position."""
    from datetime import datetime
    store.store_trade(
        trade_id="LEGACY_1", symbol="SOLUSDT", direction="LONG", entry_price=50.0,
        entry_time=datetime.now(), position_size=2.0, stop_loss=0.0,
        take_profit_levels=[], risk_amount=10.0, user_id="legacy-user",
    )
    fresh = _session("legacy-user")
    fresh.rehydrated = False
    report = await fresh.rehydrate(store)
    assert report.positions_restored == 1
    assert fresh.engine.get_open_orders() == []  # nothing to arm — and we said so
    assert any("UNPROTECTED" in w for w in report.warnings)


# --------------------------------------------------------------------------- #
# exit reasons are OBSERVED, not inferred from P&L (honesty law)
# --------------------------------------------------------------------------- #

def test_exit_reason_comes_from_the_filling_order():
    from src.execution.paper_trading_engine import OrderType, _exit_reason_for

    class O:
        def __init__(self, t):
            self.type = t

    assert _exit_reason_for(O(OrderType.STOP_MARKET)) == "SL_HIT"
    assert _exit_reason_for(O(OrderType.LIMIT)) == "TP_HIT"
    assert _exit_reason_for(O(OrderType.TAKE_PROFIT_MARKET)) == "TP_HIT"
    assert _exit_reason_for(O(OrderType.MARKET)) == "MANUAL"
    assert _exit_reason_for(O("something_new")) == "UNKNOWN"  # honest gap, not a guess


@pytest.mark.asyncio
async def test_a_profitable_stop_is_still_recorded_as_a_stop(store, ledger):
    """The case the old `TP_HIT if pnl > 0` heuristic got WRONG: a stop that fills
    in profit (gap through, or a stop moved to lock gains) is a stop, not a target.
    Every outcome-attribution query depends on this column telling the truth."""
    bus = CaptureBus()
    session = _session(bus=bus)
    await _book_long(session, entry=100.0, stop=95.0, tps=[{"price": 130.0, "size": 1.0}])
    await _pump(bus, ledger)
    engine = session.engine

    # Move the stop above entry (lock-in), then let price cross it: a WINNING stop.
    sl = next(o for o in engine.orders.values()
              if o.type.value == "STOP_MARKET" and o.status.value == "OPEN")
    sl.stop_price = 110.0
    await process_engine_tick(engine, {"BTCUSDT": 109.0})

    assert "BTCUSDT" not in engine.positions
    assert engine.balance > 100_000.0  # it closed in profit...
    await _pump(bus, ledger)
    row = store.get_recent_trades(user_id="rehydrate-user")[0]
    assert row.pnl > 0
    assert row.exit_reason == "SL_HIT"  # ...and is still, truthfully, a stop


# --------------------------------------------------------------------------- #
# same-direction add-ons are refused, not silently swallowed (money law)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_addon_order_is_rejected_and_costs_nothing():
    """The old path let an add-on fall through every branch of _update_position:
    position unchanged, commission still charged, order still booked FILLED — a
    phantom fill the user paid for. Averaging in isn't the fix either (the existing
    bracket is sized for the original quantity), so it must fail closed."""
    from src.execution.paper_trading_engine import (
        OrderSide, OrderType, PaperTradingEngine,
    )

    e = PaperTradingEngine(initial_balance=100_000.0, enable_realistic_fills=False)
    await e.check_limit_orders("BTCUSDT", 100.0)
    entry = await e.place_order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert entry["status"] == "FILLED"

    balance, commission = e.balance, e.total_commission
    addon = await e.place_order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)

    assert addon["status"] == "REJECTED"
    assert e.positions["BTCUSDT"].quantity == pytest.approx(1.0)  # unchanged...
    assert e.total_commission == commission                        # ...and free
    assert e.balance == balance
    assert addon["orderId"] not in e.orders  # never booked

    # reduce-only closes are unaffected by the guard
    close = await e.place_order("BTCUSDT", OrderSide.SELL, OrderType.MARKET, 1.0,
                                reduce_only=True)
    assert close["status"] == "FILLED"
    assert e.positions == {}
