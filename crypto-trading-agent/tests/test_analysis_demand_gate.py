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
        _last_analysis_at=None,
        cycle_interval=600,
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
async def test_the_capacity_switch_alone_does_not_keep_analysis_running(monkeypatch):
    """The gap this pins: keep-warm used to BE the capacity switch, and that switch must
    be ON for anyone to start a scan at all — so the 'override' was true in every usable
    configuration and analysis ran every cycle regardless of demand. The gate only did
    something in states where the product was unusable."""
    monkeypatch.delenv("ANALYSIS_KEEP_WARM", raising=False)
    host, orch = _host(switch_on=True, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 0, "capacity being available is not a reason to burn LLM calls"


@pytest.mark.asyncio
async def test_keep_warm_is_its_own_opt_in(monkeypatch):
    """Keeping setups warm with nobody scanning is still possible — deliberately, and
    separately from whether users are allowed to scan."""
    monkeypatch.setenv("ANALYSIS_KEEP_WARM", "true")
    host, orch = _host(switch_on=False, sessions=0)
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
async def test_demand_is_always_consulted(monkeypatch):
    """Demand must be checked FIRST. Short-circuiting it behind the switch is exactly how
    the gate became decorative."""
    monkeypatch.delenv("ANALYSIS_KEEP_WARM", raising=False)
    host, orch = _host(switch_on=True, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host.session_manager.calls == 1


@pytest.mark.asyncio
async def test_idle_time_does_not_count_against_the_cadence(monkeypatch):
    """A quiet spell must not make the first scanner wait out a window the system spent
    asleep — idle skips deliberately leave the cadence clock untouched."""
    monkeypatch.delenv("ANALYSIS_KEEP_WARM", raising=False)
    host, orch = _host(switch_on=True, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)   # idle
    assert host._last_analysis_at is None
    host.session_manager = _Sessions(1)                          # a user starts scanning
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 1, "the first scan after idle had to wait for the cadence"


@pytest.mark.asyncio
async def test_the_expensive_cycle_is_paced_even_under_constant_demand(monkeypatch):
    """The loop polls fast so demand is noticed quickly; the LLM work still runs no more
    often than the cadence."""
    monkeypatch.delenv("ANALYSIS_KEEP_WARM", raising=False)
    host, orch = _host(switch_on=True, sessions=1)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert orch.cycles == 1, "a fast poll turned into fast LLM spend"


@pytest.mark.asyncio
async def test_idle_transition_is_logged_once_not_every_cycle():
    """A 600s idle loop must not write a log line per cycle forever."""
    host, orch = _host(switch_on=False, sessions=0)
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host._was_on is False
    await MultiUserTradingDaemon._analysis_with_signals(host)
    assert host._was_on is False  # still idle, no flapping
    assert orch.cycles == 0
