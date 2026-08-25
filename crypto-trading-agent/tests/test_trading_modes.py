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
async def test_only_auto_and_scanning_paper_users_are_booked():
    """The mode contract, tightened 2026-08-25.

    Previously `paper` booked unconditionally, which meant one user's session
    booked trades into every other paper user's desk — people who never started a
    session, never saw a proposal, never approved. `paper` is now session-gated;
    `auto` still books continuously because that is what auto means. off/manual
    unchanged. See tests/test_consent_gates.py for the full contract.
    """
    modes = {"paper_scanning": "paper", "paper_idle": "paper",
             "off_u": "off", "manual_u": "manual", "auto_u": "auto"}
    reg = _registry(modes)
    sessions = type("S", (), {"get_active": staticmethod(
        lambda uid: {"session_id": uid} if uid == "paper_scanning" else None)})()
    results = await MultiUserExecutor(reg, session_manager=sessions).book_for_all(SETUP)
    booked = {r["user_id"] for r in results}
    assert booked == {"paper_scanning", "auto_u"}
    assert "paper_idle" not in booked, "an idle paper desk must not be traded"
    assert all(r.get("mode") in ("paper", "auto") for r in results)


@pytest.mark.asyncio
async def test_auto_without_exchange_builder_falls_back_to_paper():
    reg = _registry({"auto_u": "auto"})  # no exchange_builder -> paper engine
    reg.session("auto_u")
    assert reg.session("auto_u").is_live is False


@pytest.mark.asyncio
async def test_mode_default_is_paper_and_the_default_does_not_trade_you():
    """paper is the default, so the default must be QUIET. A brand-new user who has
    not started a session gets no positions from anyone else's scan."""
    reg = UserRegistry(seed_user_ids=["x"])  # no mode_for -> default paper
    assert reg.mode_for("x") == "paper"

    idle = type("S", (), {"get_active": staticmethod(lambda uid: None)})()
    assert await MultiUserExecutor(reg, session_manager=idle).book_for_all(SETUP) == []

    scanning = type("S", (), {"get_active": staticmethod(lambda uid: {"session_id": uid})})()
    results = await MultiUserExecutor(reg, session_manager=scanning).book_for_all(SETUP)
    assert {r["user_id"] for r in results} == {"x"}
