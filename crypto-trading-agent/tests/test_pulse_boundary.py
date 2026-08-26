"""The pulse boundary is dict-shaped, and a dead plane refuses — never drains (R1.3).

PulseClient.get_many returns frozen Pulse dataclasses; everything downstream
(_pulse_allows, ProposalService, synthesis) consumes plain dicts via .get().
The old tests faked get_many with dicts, so enabling SIGNAL_PLANE_ENABLED against
a LIVE engine failed every metered cycle on AttributeError while the user's clock
drained. These tests feed REAL Pulse objects through the boundary.

The second half pins the capacity rule: when the signal plane is demanded, a
stale/absent plane refuses new sessions at the door (503, no row, no clock) —
because a session started against a dead plane meters minutes into skipped_stale
cycles the user cannot get back.
"""
from unittest.mock import MagicMock

import pytest

from src.core.session_pipeline import _pulse_allows
from src.core.session_worker import SessionWorker
from src.signals.pulse_client import Pulse


def real_pulse(**over) -> Pulse:
    """A Pulse exactly as PulseClient constructs it — frozen dataclass, not a dict."""
    base = dict(
        v=1, symbol="BTCUSDT", ts=1_700_000_000_000, feed_ts=1_700_000_000_000,
        regime="Ranging", tradability=64, vetoes=[],
        factors={"liquidity_window": 1.0}, structure={}, context={"spread_bps": 0.5},
        reference_price=67000.0,
    )
    base.update(over)
    return Pulse(**base)


class FakePulseClient:
    def __init__(self, pulses):
        self._pulses = pulses

    async def get_many(self, symbols):
        return self._pulses


def make_worker(pulse_client) -> SessionWorker:
    w = SessionWorker.__new__(SessionWorker)
    w.pulse_client = pulse_client
    w.session_id = "s-test"
    return w


# --- the boundary: real Pulse objects in, dicts out ---------------------------

@pytest.mark.asyncio
async def test_fresh_pulses_normalizes_real_pulse_objects_to_dicts():
    """THE R1.3 property. Downstream calls .get() on every pulse; a Pulse dataclass
    leaking through fails every metered cycle the moment the engine is live."""
    w = make_worker(FakePulseClient({"BTCUSDT": real_pulse()}))

    out = await w._fresh_pulses(["BTCUSDT"])

    assert isinstance(out["BTCUSDT"], dict)
    assert out["BTCUSDT"]["tradability"] == 64
    assert out["BTCUSDT"].get("vetoes") == []  # the exact call that used to raise


@pytest.mark.asyncio
async def test_normalized_pulse_flows_through_the_pipeline_gate():
    """End-to-end shape check: a real engine pulse, normalized, drives _pulse_allows
    both ways — clean pulse allows, vetoed pulse blocks."""
    clean = make_worker(FakePulseClient({"BTCUSDT": real_pulse()}))
    vetoed = make_worker(FakePulseClient({"BTCUSDT": real_pulse(vetoes=["StaleFeed"], tradability=0)}))

    assert _pulse_allows((await clean._fresh_pulses(["BTCUSDT"]))["BTCUSDT"]) is True
    assert _pulse_allows((await vetoed._fresh_pulses(["BTCUSDT"]))["BTCUSDT"]) is False


@pytest.mark.asyncio
async def test_dict_pulses_still_pass_through_unchanged():
    """The daemon's tests and any future dict-shaped source keep working."""
    w = make_worker(FakePulseClient({"ETHUSDT": {"tradability": 10, "vetoes": []}}))
    out = await w._fresh_pulses(["ETHUSDT"])
    assert out == {"ETHUSDT": {"tradability": 10, "vetoes": []}}


@pytest.mark.asyncio
async def test_unusable_pulse_shapes_are_skipped_not_crashed():
    """A garbage entry must not take down the cycle — and all-garbage reads as
    'no market data' (None), which fail-closes the cycle upstream."""
    w = make_worker(FakePulseClient({"BTCUSDT": 42, "ETHUSDT": real_pulse(symbol="ETHUSDT")}))
    out = await w._fresh_pulses(["BTCUSDT", "ETHUSDT"])
    assert set(out) == {"ETHUSDT"}

    w_all_bad = make_worker(FakePulseClient({"BTCUSDT": 42}))
    assert await w_all_bad._fresh_pulses(["BTCUSDT"]) is None


# --- the capacity gate: a demanded-but-dead plane refuses at the door ----------

@pytest.fixture
def capacity(monkeypatch):
    """server._analysis_capacity with model key + engine switch satisfied, so only
    the pulse-plane clause is under test."""
    from src.api import server as srv

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PLATFORM_SYMBOLS", "BTCUSDT")
    monkeypatch.setattr(srv, "_engine_switch", lambda: None)  # no switch = fail-open, as the pool does
    monkeypatch.setattr(srv, "_pulse_probe", None)
    return srv


@pytest.mark.asyncio
async def test_capacity_ignores_the_pulse_plane_when_not_demanded(capacity, monkeypatch):
    monkeypatch.delenv("SIGNAL_PLANE_ENABLED", raising=False)
    result = await capacity._analysis_capacity()
    assert result["available"] is True


@pytest.mark.asyncio
async def test_capacity_refuses_when_plane_demanded_but_unprobeable(capacity, monkeypatch):
    """SIGNAL_PLANE_ENABLED=true with no Redis to probe = every cycle would be
    skipped_stale. Refusing at the door costs a blocked tap; admitting costs quota."""
    monkeypatch.setenv("SIGNAL_PLANE_ENABLED", "true")
    monkeypatch.setattr(capacity, "state_manager", None)
    result = await capacity._analysis_capacity()
    assert result["available"] is False
    assert result["reason"] == capacity.CAPACITY_SIGNAL_STALE


@pytest.mark.asyncio
async def test_capacity_refuses_when_no_pulse_is_fresh(capacity, monkeypatch):
    monkeypatch.setenv("SIGNAL_PLANE_ENABLED", "true")
    monkeypatch.setattr(capacity, "_pulse_probe_client", lambda: FakePulseClient({}))
    result = await capacity._analysis_capacity()
    assert result["available"] is False
    assert result["reason"] == capacity.CAPACITY_SIGNAL_STALE


@pytest.mark.asyncio
async def test_capacity_available_when_the_plane_is_fresh(capacity, monkeypatch):
    monkeypatch.setenv("SIGNAL_PLANE_ENABLED", "true")
    monkeypatch.setattr(
        capacity, "_pulse_probe_client",
        lambda: FakePulseClient({"BTCUSDT": real_pulse()}),
    )
    result = await capacity._analysis_capacity()
    assert result["available"] is True


@pytest.mark.asyncio
async def test_probe_failure_fails_closed(capacity, monkeypatch):
    class ExplodingClient:
        async def get_many(self, symbols):
            raise ConnectionError("redis gone")

    monkeypatch.setenv("SIGNAL_PLANE_ENABLED", "true")
    monkeypatch.setattr(capacity, "_pulse_probe_client", lambda: ExplodingClient())
    result = await capacity._analysis_capacity()
    assert result["available"] is False
    assert result["reason"] == capacity.CAPACITY_SIGNAL_STALE
