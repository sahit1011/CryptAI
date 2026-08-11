"""Shared analysis runs on DEMAND, not on a clock.

The bug this pins: the analysis loop was a blind timer whose only gate was the owner's
engine switch. Left on with nobody scanning, it called the LLM every cycle forever — the
free tier's whole cost model depends on that not happening. And because the same switch
also gated the session worker pool, flipping it off silently starved a running scan while
the user's metered clock kept burning.

`_analysis_with_signals` is exercised on a stub host: it reads only `engine_switch`,
`session_manager`, `_was_on`, `symbols`, `orchestrator` and `setup_cache`, so no Redis,
Postgres, agents or LLM are involved.
"""
from types import SimpleNamespace

import pytest

from src.multi_user_daemon import MultiUserTradingDaemon


class _Switch:
    def __init__(self, on):
        self._on = on

    async def is_on(self):
        return self._on


class _Sessions:
    """Stands in for SessionManager.active_sessions (called via asyncio.to_thread)."""

    def __init__(self, count=0, raises=False):
        self._count = count
        self._raises = raises
        self.calls = 0

    def active_sessions(self, limit=200):
        self.calls += 1
        if self._raises:
            raise RuntimeError("session store down")
        return [{"session_id": f"s{i}", "user_id": f"u{i}"} for i in range(self._count)]


class _Orchestrator:
    def __init__(self):
        self.cycles = 0

    async def run_analysis_cycle(self, symbol):
        self.cycles += 1
        return [{"symbol": symbol, "direction": "LONG", "entry_price": 1.0,
                 "stop_loss": 0.9, "take_profit_levels": [1.2]}]


def _host(*, switch_on=False, sessions=0, sessions_raise=False):
    orch = _Orchestrator()
    host = SimpleNamespace(
        engine_switch=_Switch(switch_on),
        session_manager=_Sessions(sessions, sessions_raise),
        orchestrator=orch,
        symbols=["BTCUSDT"],
        setup_cache=None,
        _was_on=None,
    )
    # _publish_setups touches the bus; the gate is what we're testing.
    async def _publish(setups):
        return None
    host._publish_setups = _publish
    # Bind the REAL demand check to the stub — testing the gate against a fake predicate
    # would only prove the fake works.
    host._has_scan_demand = lambda: MultiUserTradingDaemon._has_scan_demand(host)
    return host, orch


@pytest.mark.asyncio
async def test_no_demand_and_no_override_means_no_llm_call():
    """The money test: nobody scanning, switch off -> the LLM is never called."""
    host, orch = _host(switch_on=False, sessions=0)
    result = await MultiUserTradingDaemon._analysis_with_signals(host)
    assert result == []
    assert orch.cycles == 0, "analysis ran with zero demand — this is the burn bug"


@pytest.mark.asyncio
async def test_an_active_scan_is_demand_enough():
    """A user scanning is the whole reason analysis exists — no owner switch required."""
    host, orch = _host(switch_on=False, sessions=1)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 1


@pytest.mark.asyncio
async def test_owner_override_runs_analysis_with_nobody_scanning():
    """The switch survives as an override for keeping setups warm."""
    host, orch = _host(switch_on=True, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 1


@pytest.mark.asyncio
async def test_switch_off_does_not_starve_a_live_scan():
    """The two-switch bug: a scan already running must still get analysis. Refusing new
    scans is the emergency stop (capacity gate on session start); silently starving one
    that is already metering the user is not."""
    host, orch = _host(switch_on=False, sessions=1)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 1


@pytest.mark.asyncio
async def test_demand_check_fails_closed_when_the_session_store_is_down():
    """The safe error is not spending money."""
    host, orch = _host(switch_on=False, sessions_raise=True)
    result = await MultiUserTradingDaemon._analysis_with_signals(host)
    assert result == []
    assert orch.cycles == 0


@pytest.mark.asyncio
async def test_override_short_circuits_the_demand_query():
    """With the override on the answer cannot change, so don't pay for the lookup."""
    host, orch = _host(switch_on=True, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host.session_manager.calls == 0


@pytest.mark.asyncio
async def test_idle_transition_is_logged_once_not_every_cycle():
    """A 600s idle loop must not write a log line per cycle forever."""
    host, orch = _host(switch_on=False, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host._was_on is False
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host._was_on is False  # still idle, no flapping
    assert orch.cycles == 0
