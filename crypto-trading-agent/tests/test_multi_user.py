"""Multi-user engine: shared analysis once, per-user portfolios, strict isolation.

No Redis/Postgres/network needed — sessions use isolated in-memory paper engines
(message_bus/state_manager=None), so this runs anywhere.
"""
import pytest

from src.core.multi_user import (
    UserRegistry, MultiUserExecutor, MultiUserCoordinator, UserRiskConfig,
)

SETUP = {
    "symbol": "BTCUSDT", "direction": "LONG", "entry_price": 64000.0, "stop_loss": 62000.0,
    "take_profit_levels": [{"price": 68000.0, "size": 1.0}],
    "recommended_position_size": 0.05, "risk_amount": 100.0, "confidence_score": 0.72,
    "market_regime": "TRENDING_BULLISH",
}


class AllScanning:
    """Every tenant has a live session.

    `book_for_all` only fans out to paper users who are personally in a session
    (see tests/test_consent_gates.py for why). These tests are about fault
    isolation and analysis-runs-once, so they opt every tenant in explicitly
    rather than relying on a default that no longer books.
    """

    @staticmethod
    def get_active(user_id):
        return {"session_id": f"s-{user_id}"}


def _registry():
    return UserRegistry(
        config_for=lambda uid: UserRiskConfig(
            initial_balance=10000.0 if uid == "userA" else 50000.0
        )
    )


async def _seed_price(session, symbol="BTCUSDT", price=64000.0):
    """Engines refuse to fill without a live price (the honest-fills contract —
    the old $85k fantasy fallback is gone), so tests seed one exactly like the
    daemon's price-tick loop does in production."""
    await session.engine.check_limit_orders(symbol, price)


@pytest.mark.asyncio
async def test_shared_setup_books_to_every_tenant():
    reg = _registry()
    await _seed_price(reg.session("userA"))
    await _seed_price(reg.session("userB"))
    # AllScanning: this test is about per-tenant ISOLATION of one shared setup, so
    # both tenants opt in. Consent gating is covered in tests/test_consent_gates.py.
    results = await MultiUserExecutor(
        reg, session_manager=AllScanning()).book_for_all(SETUP)  # one setup -> all
    assert {r["user_id"] for r in results} == {"userA", "userB"}
    assert all(r["approved"] for r in results)
    # Each tenant booked into their OWN engine.
    assert len(reg.session("userA").engine.get_positions()) == 1
    assert len(reg.session("userB").engine.get_positions()) == 1


@pytest.mark.asyncio
async def test_portfolios_are_isolated():
    reg = _registry()
    a, b = reg.session("userA"), reg.session("userB")
    assert a.engine is not b.engine
    assert a.engine.initial_balance == 10000.0 and b.engine.initial_balance == 50000.0

    # Book for A only; B must be untouched.
    await _seed_price(a)
    await a.evaluate_and_book(SETUP)
    assert len(a.engine.get_positions()) == 1
    assert len(b.engine.get_positions()) == 0


@pytest.mark.asyncio
async def test_per_user_engine_stamps_user_id():
    reg = _registry()
    a = reg.session("userA")
    # The engine carries its owner so published/persisted state is namespaced per tenant.
    assert a.engine.user_id == "userA"
    assert reg.session("userB").engine.user_id == "userB"


@pytest.mark.asyncio
async def test_booked_trade_feeds_the_risk_tracker():
    """The tracker regression: bookings never reached PortfolioStateTracker, so every
    portfolio-level limit (heat, position count, daily loss) validated an empty book."""
    reg = _registry()
    a = reg.session("userA")
    await _seed_price(a)
    result = await a.evaluate_and_book(SETUP)
    assert result["approved"]
    assert await a.portfolio.get_position_count() == 1

    # And the ids join: the tracker holds the engine's position id, so the close-side
    # hook (keyed by position_id) and memory update (position_id minus POS_) resolve.
    engine_pos = a.engine.positions["BTCUSDT"]
    assert engine_pos.position_id in a.portfolio.positions


@pytest.mark.asyncio
async def test_position_count_limit_is_binding_once_tracker_is_fed():
    from src.risk.deterministic_risk_calculator import RiskParameters

    reg = UserRegistry(
        config_for=lambda uid: UserRiskConfig(
            risk_params=RiskParameters(max_concurrent_positions=1)
        )
    )
    a = reg.session("userA")
    await _seed_price(a)
    first = await a.evaluate_and_book(SETUP)
    assert first["approved"]

    second_setup = {**SETUP, "symbol": "ETHUSDT", "entry_price": 2500.0,
                    "stop_loss": 2400.0,
                    "take_profit_levels": [{"price": 2700.0, "size": 1.0}]}
    await _seed_price(a, symbol="ETHUSDT", price=2500.0)
    second = await a.evaluate_and_book(second_setup)
    assert not second["approved"]
    assert any("concurrent positions" in r.lower() for r in second["reasons"])


@pytest.mark.asyncio
async def test_closing_a_position_flows_back_to_the_tracker():
    from src.execution.paper_trading_engine import OrderSide

    reg = _registry()
    a = reg.session("userA")
    await _seed_price(a)
    await a.evaluate_and_book(SETUP)
    assert await a.portfolio.get_position_count() == 1

    qty = a.engine.positions["BTCUSDT"].quantity
    await a.engine.close_position(symbol="BTCUSDT", side=OrderSide.SELL, quantity=qty)

    assert await a.portfolio.get_position_count() == 0
    # close_position is also what advances the daily-trade counter the cap reads.
    assert a.portfolio.daily_trades == 1


@pytest.mark.asyncio
async def test_daily_trade_cap_rejects_through_the_full_validate_path():
    """The attribute regression: the cap read snapshot.daily_trades_count, which does not
    exist, so getattr returned 0 forever and max_daily_trades never rejected anything."""
    from src.execution.paper_trading_engine import OrderSide
    from src.risk.deterministic_risk_calculator import RiskParameters

    reg = UserRegistry(
        config_for=lambda uid: UserRiskConfig(
            risk_params=RiskParameters(max_daily_trades=1)
        )
    )
    a = reg.session("userA")
    await _seed_price(a)
    assert (await a.evaluate_and_book(SETUP))["approved"]
    qty = a.engine.positions["BTCUSDT"].quantity
    await a.engine.close_position(symbol="BTCUSDT", side=OrderSide.SELL, quantity=qty)

    again = await a.evaluate_and_book(SETUP)
    assert not again["approved"]
    assert any("daily trade limit" in r.lower() for r in again["reasons"])


@pytest.mark.asyncio
async def test_booking_publishes_a_joinable_log_trade_entry():
    """The memory regression: daemon-booked trades never sent log_trade, so the exit-side
    update_trade hit 'Trade not found' and the learning loop accumulated nothing."""
    class FakeBus:
        def __init__(self):
            self.published = []

        async def publish(self, channel, message):
            self.published.append((channel, message))

    bus = FakeBus()
    reg = UserRegistry(message_bus=bus, config_for=lambda uid: UserRiskConfig())
    a = reg.session("userA")
    await _seed_price(a)
    result = await a.evaluate_and_book(SETUP)
    assert result["approved"]

    log_msgs = [m for ch, m in bus.published
                if ch == "memory_agent_inbox" and m.get("type") == "log_trade"]
    assert len(log_msgs) == 1
    payload = log_msgs[0]["payload"]
    # The id the exit side will use: engine position_id with the POS_ prefix stripped.
    expected = a.engine.positions["BTCUSDT"].position_id.replace("POS_", "")
    assert payload["trade_id"] == expected
    assert payload["user_id"] == "userA"
    assert payload["entry_price"] > 0 and payload["position_size"] > 0


@pytest.mark.asyncio
async def test_tracker_snapshots_are_namespaced_per_user():
    """A shared snapshot dir would have every tenant overwriting one stable filename —
    and each hydrating whichever tenant wrote last on restart."""
    reg = _registry()
    a, b = reg.session("userA"), reg.session("userB")
    assert a.portfolio.snapshot_dir != b.portfolio.snapshot_dir
    assert "userA" in str(a.portfolio.snapshot_dir)

    # And a booking actually lands a snapshot in the per-user directory.
    await _seed_price(a)
    await a.evaluate_and_book(SETUP)
    assert (a.portfolio.snapshot_dir / "portfolio_latest.json").exists()


@pytest.mark.asyncio
async def test_missing_risk_amount_is_derived_and_close_survives():
    """The zero-risk regression: a setup without risk_amount (hand-sized ticket) booked
    a 0-risk tracker position, and close_position then divided by it — crashing the hook
    and skipping snapshot persistence, so a restart would resurrect the position."""
    from src.execution.paper_trading_engine import OrderSide

    reg = _registry()
    a = reg.session("userA")
    await _seed_price(a)
    setup = {k: v for k, v in SETUP.items() if k != "risk_amount"}
    result = await a.evaluate_and_book(setup)
    assert result["approved"]

    engine_pos = a.engine.positions["BTCUSDT"]
    tracked = a.portfolio.positions[engine_pos.position_id]
    # Derived from the bracket at the ACTUAL fill (slippage included), not the nominal
    # entry: size * |fill - stop|.
    expected = 0.05 * abs(engine_pos.entry_price - 62000.0)
    assert tracked.risk_amount == pytest.approx(expected)
    assert tracked.risk_amount > 0

    qty = a.engine.positions["BTCUSDT"].quantity
    await a.engine.close_position(symbol="BTCUSDT", side=OrderSide.SELL, quantity=qty)
    assert await a.portfolio.get_position_count() == 0
    assert a.portfolio.daily_trades == 1  # the close reached the tracker, no crash


@pytest.mark.asyncio
async def test_close_position_survives_a_zero_risk_position():
    """Defense in depth for the division itself, should a 0-risk position ever be fed
    directly (bypassing the derivation)."""
    from src.risk.portfolio_state_tracker import PortfolioStateTracker

    tracker = PortfolioStateTracker(initial_balance=10_000.0)
    await tracker.add_position(
        position_id="P0", symbol="BTCUSDT", direction="LONG", entry_price=64000.0,
        position_size=0.05, stop_loss=62000.0, take_profit_levels=[68000.0],
        risk_amount=0.0,
    )
    result = await tracker.close_position("P0", exit_price=65000.0, reason="manual")
    assert result["pnl_percentage"] == 0.0
    assert tracker.daily_trades == 1


@pytest.mark.asyncio
async def test_one_tenant_failure_does_not_abort_others():
    reg = _registry()
    reg.session("userA")
    reg.session("userB")
    # A malformed setup (missing stop_loss) fails risk/exec but must not raise; both
    # tenants get a captured result.
    bad = {k: v for k, v in SETUP.items() if k != "stop_loss"}
    results = await MultiUserExecutor(reg, session_manager=AllScanning()).book_for_all(bad)
    assert len(results) == 2
    assert all(r["approved"] is False for r in results)


@pytest.mark.asyncio
async def test_analysis_runs_once_per_cycle_regardless_of_tenant_count():
    """The expensive shared analysis is computed ONCE and reused for every tenant."""
    reg = _registry()
    for uid in ("userA", "userB", "u3", "u4", "u5"):
        reg.session(uid)
    calls = {"n": 0}

    async def analysis_provider():
        calls["n"] += 1          # counts how many times analysis ran this cycle
        return [SETUP]

    coord = MultiUserCoordinator(reg, session_manager=AllScanning())
    per_setup_results = await coord.run_cycle(analysis_provider)
    assert calls["n"] == 1                      # analysis computed ONCE...
    assert len(per_setup_results) == 1          # one setup
    assert len(per_setup_results[0]) == 5       # ...booked to all 5 tenants
