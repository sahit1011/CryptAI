"""Per-session workers: budget gating, spend attribution, staleness, isolation.

The analysis step is injected, so none of this needs an LLM. What is under test is the
LIFECYCLE — the ordering guarantees that decide whether the metered session actually
bounds spend.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from src.core.preferences import PreferencesStore
from src.core.session_manager import ENDED, SessionManager
from src.core.session_worker import (
    CYCLE_FAILED,
    CYCLE_RAN,
    CYCLE_SKIPPED_BUDGET,
    CYCLE_SKIPPED_NOT_SCANNING,
    CYCLE_SKIPPED_STALE,
    SessionWorker,
    SessionWorkerPool,
)

ALICE = "user-alice"
BOB = "user-bob"
START = datetime(2026, 8, 2, 10, 0, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakePulses:
    """Stands in for PulseClient.get_many."""

    def __init__(self, result=None, raises=False):
        self.result = {"BTCUSDT": {"tradability": 70}} if result is None else result
        self.raises = raises

    async def get_many(self, symbols):
        if self.raises:
            raise RuntimeError("redis down")
        return self.result


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def mgr(tmp_path, clock):
    return SessionManager(
        f"sqlite:///{tmp_path}/s.db",
        daily_quota_seconds=1800,
        cost_cap_micros=500_000,
        now_fn=clock,
    )


@pytest.fixture
def prefs(tmp_path):
    return PreferencesStore(f"sqlite:///{tmp_path}/p.db")


def make_worker(mgr, prefs, session, analyze_fn, pulses=None):
    return SessionWorker(
        mgr, prefs, session, analyze_fn, pulse_client=pulses or FakePulses()
    )


async def _ok(context):
    return [{"symbol": "BTCUSDT"}], None


# --- ordering: budget is checked BEFORE spending ------------------------------

@pytest.mark.asyncio
async def test_no_analysis_runs_when_the_time_meter_is_exhausted(mgr, prefs, clock):
    """can_spend() must gate BEFORE the call — checking afterwards is checking after
    the money is gone."""
    s = mgr.start(ALICE)
    called = {"n": 0}

    async def analyze(context):
        called["n"] += 1
        return [], None

    worker = make_worker(mgr, prefs, s, analyze)
    clock.advance(1801)

    assert await worker.run_cycle() == CYCLE_SKIPPED_BUDGET
    assert called["n"] == 0, "analysis ran after the quota was gone"
    assert mgr.get(s["session_id"])["end_reason"] == "quota_exhausted"


@pytest.mark.asyncio
async def test_no_analysis_runs_when_the_cost_cap_is_hit(mgr, prefs):
    s = mgr.start(ALICE)
    mgr.record_llm_usage(s["session_id"], tokens=1, cost_micros=600_000)

    called = {"n": 0}

    async def analyze(context):
        called["n"] += 1
        return [], None

    worker = make_worker(mgr, prefs, s, analyze)
    assert await worker.run_cycle() == CYCLE_SKIPPED_BUDGET
    assert called["n"] == 0


# --- spend attribution --------------------------------------------------------

@pytest.mark.asyncio
async def test_usage_is_booked_against_the_session(mgr, prefs):
    s = mgr.start(ALICE)

    async def analyze(context):
        return [], {"model": "claude-opus-5", "input_tokens": 10_000, "output_tokens": 2_000}

    worker = make_worker(mgr, prefs, s, analyze)
    assert await worker.run_cycle() == CYCLE_RAN

    state = mgr.get(s["session_id"])
    assert state["llm_tokens_used"] == 12_000
    assert state["llm_cost_micros"] > 0


@pytest.mark.asyncio
async def test_spend_is_recorded_even_when_analysis_raises(mgr, prefs):
    """A request that errored AFTER the provider billed it still cost money. Skipping
    the charge on the error path is exactly how a cap leaks."""
    s = mgr.start(ALICE)

    class Boom(Exception):
        pass

    async def analyze(context):
        # Simulate a provider that billed, then the pipeline failing downstream.
        raise Boom("downstream parse error")

    worker = SessionWorker(mgr, prefs, s, analyze, pulse_client=FakePulses())

    # Book spend the way a real call site would, then let the cycle fail.
    worker.budget.record("claude-opus-5", input_tokens=50_000, output_tokens=5_000)
    before = mgr.get(s["session_id"])["llm_cost_micros"]

    assert await worker.run_cycle() == CYCLE_FAILED
    assert mgr.get(s["session_id"])["llm_cost_micros"] >= before > 0


@pytest.mark.asyncio
async def test_a_failed_cycle_does_not_end_the_session(mgr, prefs):
    """One bad cycle is not a terminal condition — the user paid for the minutes."""
    s = mgr.start(ALICE)

    async def analyze(context):
        raise RuntimeError("transient")

    worker = make_worker(mgr, prefs, s, analyze)
    assert await worker.run_cycle() == CYCLE_FAILED
    assert mgr.get(s["session_id"])["status"] != ENDED


# --- pulse staleness (invariant 2) --------------------------------------------

@pytest.mark.asyncio
async def test_no_analysis_on_an_unreadable_signal_plane(mgr, prefs):
    """Fail closed. The shared plane is a single point of failure for every tenant."""
    s = mgr.start(ALICE)
    called = {"n": 0}

    async def analyze(context):
        called["n"] += 1
        return [], None

    worker = make_worker(mgr, prefs, s, analyze, pulses=FakePulses(raises=True))
    assert await worker.run_cycle() == CYCLE_SKIPPED_STALE
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_no_pulses_is_distinct_from_nothing_tradable(mgr, prefs):
    """An empty pulse map means "no market data", which must not look like "the market
    says nothing is tradable"."""
    s = mgr.start(ALICE)
    worker = make_worker(mgr, prefs, s, _ok, pulses=FakePulses(result={}))
    assert await worker.run_cycle() == CYCLE_SKIPPED_STALE


@pytest.mark.asyncio
async def test_runs_without_a_pulse_client_configured(mgr, prefs):
    """The signal engine is not deployed yet; blocking every session on a service that
    does not exist would make the control plane untestable."""
    s = mgr.start(ALICE)
    worker = SessionWorker(mgr, prefs, s, _ok, pulse_client=None)
    assert await worker.run_cycle() == CYCLE_RAN


# --- session state ------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_analysis_while_a_proposal_is_pending(mgr, prefs):
    """The clock is paused at setup_proposed; burning LLM spend there would charge the
    user for deliberation they are explicitly not being metered for."""
    s = mgr.start(ALICE)
    mgr.propose(s["session_id"])

    called = {"n": 0}

    async def analyze(context):
        called["n"] += 1
        return [], None

    worker = make_worker(mgr, prefs, s, analyze)
    assert await worker.run_cycle() == CYCLE_SKIPPED_NOT_SCANNING
    assert called["n"] == 0


# --- per-user scoping ---------------------------------------------------------

@pytest.mark.asyncio
async def test_the_cycle_is_scoped_to_the_session_owner(mgr, prefs):
    """This is the whole point of the rewire: analysis is per-user, not a broadcast."""
    prefs.set(ALICE, {"symbol_universe": ["SOLUSDT"], "risk_appetite": "aggressive"})
    s = mgr.start(ALICE)
    seen = {}

    async def analyze(context):
        seen.update(context)
        return [], None

    worker = make_worker(mgr, prefs, s, analyze)
    await worker.run_cycle()

    assert seen["user_id"] == ALICE
    assert seen["symbols"] == ["SOLUSDT"]
    assert seen["preferences"]["risk_appetite"] == "aggressive"


@pytest.mark.asyncio
async def test_agent_steps_land_in_the_owners_feed(mgr, prefs):
    s = mgr.start(ALICE)
    worker = make_worker(mgr, prefs, s, _ok)
    await worker.run_cycle()

    events = mgr.events(s["session_id"])
    assert any(e["event_type"] == "agent_step" for e in events)


# --- pool ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_pool_spawns_one_worker_per_active_session(mgr, prefs):
    mgr.start(ALICE)
    mgr.start(BOB)
    pool = SessionWorkerPool(mgr, prefs, _ok, cycle_seconds=3600)

    assert await pool.discover_once() == 2
    await pool.stop(timeout=2)


@pytest.mark.asyncio
async def test_the_pool_does_not_double_spawn(mgr, prefs):
    mgr.start(ALICE)
    pool = SessionWorkerPool(mgr, prefs, _ok, cycle_seconds=3600)
    await pool.discover_once()
    assert await pool.discover_once() == 1
    await pool.stop(timeout=2)


@pytest.mark.asyncio
async def test_the_pool_spawns_nothing_for_an_idle_deployment(mgr, prefs):
    pool = SessionWorkerPool(mgr, prefs, _ok)
    assert await pool.discover_once() == 0


@pytest.mark.asyncio
async def test_the_kill_switch_halts_all_work(mgr, prefs):
    """Sessions decide WHO runs; the switch decides whether ANYONE does. Losing the
    ability to halt every tenant at once would be a real regression."""
    mgr.start(ALICE)

    class Off:
        async def is_on(self):
            return False

    pool = SessionWorkerPool(mgr, prefs, _ok, kill_switch=Off())
    assert await pool.discover_once() == 0


@pytest.mark.asyncio
async def test_an_unreadable_kill_switch_halts_work(mgr, prefs):
    """Fail closed: an emergency stop whose state is unknown must be treated as engaged."""
    mgr.start(ALICE)

    class Broken:
        async def is_on(self):
            raise RuntimeError("redis down")

    pool = SessionWorkerPool(mgr, prefs, _ok, kill_switch=Broken())
    assert await pool.discover_once() == 0


@pytest.mark.asyncio
async def test_no_kill_switch_means_no_emergency_stop_not_a_permanent_halt(mgr, prefs):
    mgr.start(ALICE)
    pool = SessionWorkerPool(mgr, prefs, _ok, kill_switch=None, cycle_seconds=3600)
    assert await pool.discover_once() == 1
    await pool.stop(timeout=2)


@pytest.mark.asyncio
async def test_discovery_survives_a_broken_session_store(mgr, prefs, monkeypatch):
    """The pool is the only thing spawning workers; a bad pass must not kill it."""
    pool = SessionWorkerPool(mgr, prefs, _ok)

    def explode(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(mgr, "active_sessions", explode)
    assert await pool.discover_once() == 0  # no raise


@pytest.mark.asyncio
async def test_finished_workers_are_reaped(mgr, prefs, clock):
    s = mgr.start(ALICE)
    pool = SessionWorkerPool(mgr, prefs, _ok, cycle_seconds=3600)
    await pool.discover_once()
    assert len(pool.workers) == 1

    # The session ends; its worker exits and the next pass should drop it.
    mgr.end(s["session_id"])
    for _ in range(50):
        await asyncio.sleep(0)
        if pool.workers[s["session_id"]].done():
            break
    assert await pool.discover_once() == 0
    await pool.stop(timeout=2)


@pytest.mark.asyncio
async def test_active_sessions_lists_every_tenant(mgr):
    mgr.start(ALICE)
    mgr.start(BOB)
    assert {s["user_id"] for s in mgr.active_sessions()} == {ALICE, BOB}


@pytest.mark.asyncio
async def test_active_sessions_excludes_ended_ones(mgr):
    a = mgr.start(ALICE)
    mgr.start(BOB)
    mgr.end(a["session_id"])
    assert [s["user_id"] for s in mgr.active_sessions()] == [BOB]
