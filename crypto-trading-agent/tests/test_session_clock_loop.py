"""The server-authoritative session clock loop.

This loop is the only thing that ends an abandoned session. Both meters are enforced in
`tick()`, which otherwise runs only when a request arrives — so a user who starts a
session and shuts their laptop would meter forever and silently drain their whole daily
quota. These tests exercise one iteration of the loop directly rather than waiting on its
sleep, so nothing here takes real time.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

import src.api.server as server
from src.core.session_manager import COST_CAP, ENDED, QUOTA_EXHAUSTED, SessionManager

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


class FakeSocket:
    """Stands in for a WebSocket in manager.connections."""


class RecordingManager:
    """Captures broadcasts instead of writing to sockets."""

    def __init__(self, connections):
        self.connections = connections
        self.sent = []

    async def broadcast(self, message, channel=None):
        self.sent.append(message)


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


async def _one_iteration(monkeypatch, mgr, conns):
    """Run exactly one pass of the loop body.

    Calls `_session_tick_once` directly rather than starting the loop and cancelling it.
    Racing a task cancellation against `asyncio.to_thread` is flaky, and it tests the
    timer instead of the behaviour.
    """
    recorder = RecordingManager(conns)
    monkeypatch.setattr(server, "manager", recorder)
    monkeypatch.setattr(server, "session_manager", mgr)
    await server._session_tick_once()
    return recorder.sent


@pytest.mark.asyncio
async def test_an_abandoned_session_is_ended_by_the_loop(monkeypatch, mgr, clock):
    """The property the loop exists for: nothing else would ever end this session."""
    s = mgr.start(ALICE)
    clock.advance(1801)  # past the quota, no requests made

    conns = {FakeSocket(): ALICE}
    await _one_iteration(monkeypatch, mgr, conns)

    got = mgr.get(s["session_id"])
    assert got["status"] == ENDED
    assert got["end_reason"] == QUOTA_EXHAUSTED


@pytest.mark.asyncio
async def test_the_cost_cap_is_enforced_by_the_loop_too(monkeypatch, mgr, clock):
    s = mgr.start(ALICE)
    mgr.record_llm_usage(s["session_id"], tokens=10, cost_micros=100)
    # Force the recorded spend past the cap without going through record_llm_usage,
    # simulating cost booked by another process.
    db = mgr.Session()
    try:
        from src.data.data_models import Session as SessionRow
        row = db.query(SessionRow).filter_by(session_id=s["session_id"]).first()
        row.llm_cost_micros = 900_000
        db.commit()
    finally:
        db.close()

    await _one_iteration(monkeypatch, mgr, {FakeSocket(): ALICE})
    assert mgr.get(s["session_id"])["end_reason"] == COST_CAP


@pytest.mark.asyncio
async def test_the_tick_is_addressed_to_its_owner(monkeypatch, mgr, clock):
    """Tenanted broadcast: the payload must carry the user_id the router keys off."""
    mgr.start(ALICE)
    clock.advance(30)

    sent = await _one_iteration(monkeypatch, mgr, {FakeSocket(): ALICE})
    ticks = [m for m in sent if m.get("type") == "session_tick"]
    assert len(ticks) == 1
    assert ticks[0]["user_id"] == ALICE
    assert ticks[0]["data"]["user_id"] == ALICE
    assert ticks[0]["data"]["elapsed_seconds"] == 30
    assert ticks[0]["data"]["remaining_today_seconds"] == 1770


@pytest.mark.asyncio
async def test_users_without_a_session_are_not_ticked(monkeypatch, mgr, clock):
    mgr.start(ALICE)
    sent = await _one_iteration(monkeypatch, mgr, {FakeSocket(): ALICE, FakeSocket(): BOB})
    recipients = {m["user_id"] for m in sent if m.get("type") == "session_tick"}
    assert recipients == {ALICE}


@pytest.mark.asyncio
async def test_one_tenants_failure_does_not_stop_the_others(monkeypatch, mgr, clock):
    """A per-user exception must not take the quota enforcer down for everyone."""
    mgr.start(ALICE)
    mgr.start(BOB)

    real_get_active = mgr.get_active

    def exploding(user_id):
        if user_id == ALICE:
            raise RuntimeError("boom")
        return real_get_active(user_id)

    monkeypatch.setattr(mgr, "get_active", exploding)
    sent = await _one_iteration(monkeypatch, mgr, {FakeSocket(): ALICE, FakeSocket(): BOB})

    recipients = {m["user_id"] for m in sent if m.get("type") == "session_tick"}
    assert recipients == {BOB}, "a failing tenant suppressed a healthy one"


@pytest.mark.asyncio
async def test_the_pass_is_a_noop_without_a_session_manager(monkeypatch, mgr):
    """The loop starts even if SessionManager failed to initialise, so it must no-op."""
    recorder = RecordingManager({FakeSocket(): ALICE})
    monkeypatch.setattr(server, "manager", recorder)
    monkeypatch.setattr(server, "session_manager", None)

    await server._session_tick_once()  # must not raise
    assert recorder.sent == []


@pytest.mark.asyncio
async def test_the_loop_keeps_running_after_a_pass_raises(monkeypatch, mgr):
    """The loop is the only thing enforcing the quota; a bad pass must not kill it."""
    calls = {"n": 0}

    async def sometimes_explodes():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "_session_tick_once", sometimes_explodes)
    monkeypatch.setattr(server, "SESSION_TICK_SECONDS", 0)

    task = asyncio.get_running_loop().create_task(server._session_tick_loop())
    for _ in range(20):
        await asyncio.sleep(0)
        if calls["n"] >= 2:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert calls["n"] >= 2, "loop died after the first exception"


@pytest.mark.asyncio
async def test_a_paused_clock_does_not_advance_over_ticks(monkeypatch, mgr, clock):
    """Deliberation stays unmetered even while the loop is pushing updates."""
    s = mgr.start(ALICE)
    clock.advance(60)
    mgr.propose(s["session_id"])

    clock.advance(300)
    sent = await _one_iteration(monkeypatch, mgr, {FakeSocket(): ALICE})

    tick = next(m for m in sent if m.get("type") == "session_tick")
    assert tick["data"]["elapsed_seconds"] == 60
    assert tick["data"]["clock_running"] is False
    assert mgr.get(s["session_id"])["status"] == "setup_proposed", "tick ended a paused session"
