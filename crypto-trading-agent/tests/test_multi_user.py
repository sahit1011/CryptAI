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
    results = await MultiUserExecutor(reg).book_for_all(SETUP)  # one shared setup -> all
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
async def test_one_tenant_failure_does_not_abort_others():
    reg = _registry()
    reg.session("userA")
    reg.session("userB")
    # A malformed setup (missing stop_loss) fails risk/exec but must not raise; both
    # tenants get a captured result.
    bad = {k: v for k, v in SETUP.items() if k != "stop_loss"}
    results = await MultiUserExecutor(reg).book_for_all(bad)
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

    coord = MultiUserCoordinator(reg)
    per_setup_results = await coord.run_cycle(analysis_provider)
    assert calls["n"] == 1                      # analysis computed ONCE...
    assert len(per_setup_results) == 1          # one setup
    assert len(per_setup_results[0]) == 5       # ...booked to all 5 tenants
