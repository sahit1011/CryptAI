"""Per-user trading-mode branching in the multi-user executor.

off/manual users are skipped by the auto-booking loop (manual users act via
/api/execute-setup); paper/auto users get the setup booked. In-memory engines only —
no Redis/DB/network.
"""
import pytest

from src.core.multi_user import UserRegistry, MultiUserExecutor, UserRiskConfig

SETUP = {
    "symbol": "BTCUSDT", "direction": "LONG", "entry_price": 64000.0, "stop_loss": 62000.0,
    "take_profit_levels": [{"price": 68000.0, "size": 1.0}],
    "recommended_position_size": 0.05, "risk_amount": 100.0, "confidence_score": 0.72,
    "market_regime": "TRENDING_BULLISH",
}


def _registry(modes):
    return UserRegistry(
        config_for=lambda uid: UserRiskConfig(initial_balance=10000.0),
        mode_for=lambda uid: modes[uid],
        seed_user_ids=list(modes),
    )


@pytest.mark.asyncio
async def test_off_and_manual_are_skipped_paper_and_auto_book():
    modes = {"paper_u": "paper", "off_u": "off", "manual_u": "manual", "auto_u": "auto"}
    reg = _registry(modes)
    results = await MultiUserExecutor(reg).book_for_all(SETUP)
    booked = {r["user_id"] for r in results}
    # off + manual skipped entirely; paper + auto attempted
    assert booked == {"paper_u", "auto_u"}
    assert all(r.get("mode") in ("paper", "auto") for r in results)


@pytest.mark.asyncio
async def test_auto_without_exchange_builder_falls_back_to_paper():
    reg = _registry({"auto_u": "auto"})  # no exchange_builder -> paper engine
    reg.session("auto_u")
    assert reg.session("auto_u").is_live is False


@pytest.mark.asyncio
async def test_mode_default_is_paper():
    reg = UserRegistry(seed_user_ids=["x"])  # no mode_for -> default paper
    assert reg.mode_for("x") == "paper"
    results = await MultiUserExecutor(reg).book_for_all(SETUP)
    assert {r["user_id"] for r in results} == {"x"}
