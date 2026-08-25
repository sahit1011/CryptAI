"""Nobody gets traded without asking — the three consent holes found 2026-08-25.

All three were the same class of bug: a mode or plan flag that the product PROMISES
is enforced, but which some path didn't read. They are grouped here because they are
one contract: *an account is only traded when its owner asked for it.*

1. `paper` is the DEFAULT mode and the fan-out is driven by a deployment-GLOBAL
   "is anybody scanning" signal — so one user's session booked trades into every
   other paper user's desk. People who never started a session found positions.
2. `/api/execute-setup` never read trading_mode, so `off` meant "the daemon won't
   auto-trade you", not "don't trade my account".
3. `plan.allow_live` was defined and unit-tested but read nowhere, so a free-tier
   user could set themselves to `auto`.
"""
from unittest.mock import MagicMock

import pytest

from src.core.multi_user import MultiUserExecutor, UserRegistry


class FakeSessionManager:
    """Only what the executor needs: who currently has a live session."""

    def __init__(self, active_users=()):
        self.active = set(active_users)
        self.raise_on_get = False

    def get_active(self, user_id):
        if self.raise_on_get:
            raise ConnectionError("session store down")
        return {"session_id": f"s-{user_id}"} if user_id in self.active else None


def _executor(modes: dict, session_manager=None) -> MultiUserExecutor:
    registry = UserRegistry(seed_user_ids=list(modes), mode_for=lambda uid: modes[uid])
    ex = MultiUserExecutor(registry, session_manager=session_manager)
    # Stub the per-user booking so these tests are about WHO is booked, not how.
    booked = []
    for uid in modes:
        s = registry.session(uid)

        async def _book(setup, _uid=uid):
            booked.append(_uid)
            return {"user_id": _uid, "approved": True}
        s.evaluate_and_book = _book
    ex.booked = booked
    return ex


SETUP = {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": 100.0,
         "stop_loss": 95.0, "take_profit_levels": [103.0]}


# --------------------------------------------------------------------------- #
# 1. the paper fan-out
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_paper_user_without_a_session_is_not_traded():
    """THE bug: user B never started a session, but A scanning booked into B's desk."""
    ex = _executor({"scanner": "paper", "bystander": "paper"},
                   FakeSessionManager(active_users=["scanner"]))
    await ex.book_for_all(SETUP)
    assert ex.booked == ["scanner"], "a paper user with no live session must be skipped"


@pytest.mark.asyncio
async def test_auto_is_traded_continuously_because_that_is_what_auto_means():
    ex = _executor({"a": "auto"}, FakeSessionManager(active_users=[]))
    await ex.book_for_all(SETUP)
    assert ex.booked == ["a"]


@pytest.mark.asyncio
async def test_off_and_manual_are_still_skipped():
    ex = _executor({"o": "off", "m": "manual"}, FakeSessionManager(active_users=["o", "m"]))
    await ex.book_for_all(SETUP)
    assert ex.booked == [], "an explicit opt-out outranks having a session open"


@pytest.mark.asyncio
async def test_no_session_store_means_no_paper_bookings():
    """Absent session plane -> the safe direction (quiet), never 'trade everyone'."""
    ex = _executor({"p": "paper"}, session_manager=None)
    await ex.book_for_all(SETUP)
    assert ex.booked == []


@pytest.mark.asyncio
async def test_an_unreadable_session_store_fails_closed():
    sm = FakeSessionManager(active_users=["p"])
    sm.raise_on_get = True
    ex = _executor({"p": "paper"}, sm)
    await ex.book_for_all(SETUP)
    assert ex.booked == [], "a DB error must not authorize a booking"


# --------------------------------------------------------------------------- #
# 2. /api/execute-setup honors mode=off
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_execute_setup_refuses_when_trading_is_off(monkeypatch):
    from fastapi import HTTPException

    from src.api import server as srv

    store = MagicMock()
    store.get.return_value = {"trading_mode": "off", "active_exchange": "bingx"}
    monkeypatch.setattr(srv, "user_settings_store", store)

    body = srv.ExecuteSetupBody(symbol="BTCUSDT", direction="LONG", entry_price=100.0,
                                stop_loss=95.0, take_profit_levels=[103.0])
    with pytest.raises(HTTPException) as err:
        await srv.execute_setup(body, user_id="opted-out")
    assert err.value.status_code == 409
    assert "switched off" in str(err.value.detail).lower()


@pytest.mark.asyncio
async def test_execute_setup_falls_back_to_paper_when_settings_unreadable(monkeypatch):
    """An unreadable store must not read as `off` (locking users out) nor as `auto`
    (routing to live). It falls back to the safe default and proceeds."""
    from src.api import server as srv

    store = MagicMock()
    store.get.side_effect = ConnectionError("db down")
    monkeypatch.setattr(srv, "user_settings_store", store)
    monkeypatch.setattr(srv, "message_bus", None)
    monkeypatch.setattr(srv, "state_manager", None)

    body = srv.ExecuteSetupBody(symbol="BTCUSDT", direction="LONG", entry_price=100.0,
                               stop_loss=95.0, take_profit_levels=[103.0])
    # Proceeds past the mode gate (it fails on later infra, not on a 409).
    try:
        await srv.execute_setup(body, user_id="u")
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            assert e.status_code != 409, "must not lock the user out over a DB blip"


# --------------------------------------------------------------------------- #
# 3. plan.allow_live gates `auto`
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_free_tier_cannot_switch_itself_to_auto(monkeypatch):
    from fastapi import HTTPException

    from src.api import server as srv

    monkeypatch.setattr(srv, "user_settings_store", MagicMock())
    monkeypatch.setenv("DEFAULT_PLAN_TIER", "free")

    body = srv.SettingsBody(trading_mode="auto")
    with pytest.raises(HTTPException) as err:
        await srv.set_settings(body, user_id="free-user")
    assert err.value.status_code == 403
    assert err.value.detail["code"] == "auto_not_permitted"


@pytest.mark.asyncio
async def test_a_permitted_tier_may_choose_auto(monkeypatch):
    from src.api import server as srv

    store = MagicMock()
    store.set.return_value = {"trading_mode": "auto"}
    monkeypatch.setattr(srv, "user_settings_store", store)
    monkeypatch.setenv("DEFAULT_PLAN_TIER", "pro")

    out = await srv.set_settings(srv.SettingsBody(trading_mode="auto"), user_id="pro-user")
    assert out["trading_mode"] == "auto"


@pytest.mark.asyncio
async def test_unresolvable_plan_refuses_auto(monkeypatch):
    """Fails CLOSED — the money law forbids widening a gate to get past an error."""
    from fastapi import HTTPException

    from src.api import server as srv
    import src.billing as billing

    monkeypatch.setattr(srv, "user_settings_store", MagicMock())
    monkeypatch.setattr(billing, "plan_for_user",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no plan")))

    with pytest.raises(HTTPException) as err:
        await srv.set_settings(srv.SettingsBody(trading_mode="auto"), user_id="u")
    assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_paper_and_manual_need_no_plan_permission(monkeypatch):
    from src.api import server as srv

    store = MagicMock()
    store.set.return_value = {"trading_mode": "manual"}
    monkeypatch.setattr(srv, "user_settings_store", store)
    monkeypatch.setenv("DEFAULT_PLAN_TIER", "free")

    out = await srv.set_settings(srv.SettingsBody(trading_mode="manual"), user_id="free")
    assert out["trading_mode"] == "manual"
