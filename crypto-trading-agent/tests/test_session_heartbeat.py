"""The session heartbeat: `last_cycle_at` and `expected_cycle_seconds`.

Together these let the UI stop claiming the agents are working when they are not. The
client compares the two, so a drift between the interval the server paces on and the
interval it publishes would make it accuse a healthy engine of being dead — or, worse,
stay quiet about a dead one.
"""
from datetime import datetime, timedelta

import pytest

from src.core.session_manager import (
    DEFAULT_CYCLE_SECONDS,
    SessionManager,
    configured_cycle_seconds,
)
from src.core import session_worker

ALICE = "user-alice"
START = datetime(2026, 8, 2, 10, 0, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def mgr(tmp_path, clock):
    return SessionManager(f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock)


# --- last_cycle_at ------------------------------------------------------------

def test_a_fresh_session_has_reported_nothing(mgr):
    """null is not "a while ago". A session that merely exists is not evidence the
    agents are working, and the client leans on that distinction to judge a new session
    leniently instead of accusing it before its first sweep lands."""
    s = mgr.start(ALICE)
    assert s["last_cycle_at"] is None


def test_recording_a_cycle_stamps_the_heartbeat(mgr, clock):
    s = mgr.start(ALICE)
    clock.advance(120)
    mgr.record_cycle(s["session_id"])

    got = mgr.get(s["session_id"])
    assert got["last_cycle_at"] == (START + timedelta(seconds=120)).isoformat()
    assert got["cycles_completed"] == 1


def test_the_heartbeat_advances_with_each_cycle(mgr, clock):
    s = mgr.start(ALICE)
    mgr.record_cycle(s["session_id"])
    first = mgr.get(s["session_id"])["last_cycle_at"]

    clock.advance(180)
    mgr.record_cycle(s["session_id"])
    second = mgr.get(s["session_id"])["last_cycle_at"]

    assert second > first
    assert mgr.get(s["session_id"])["cycles_completed"] == 2


def test_the_heartbeat_is_stamped_on_completion_not_dispatch(mgr, clock):
    """Stamping when a cycle STARTS would keep the heartbeat fresh while every cycle
    failed — exactly the state the staleness check exists to expose. record_cycle is
    only reached after a cycle returns successfully."""
    s = mgr.start(ALICE)
    clock.advance(600)
    # No record_cycle call: cycles were attempted and failed.
    assert mgr.get(s["session_id"])["last_cycle_at"] is None


# --- expected_cycle_seconds ---------------------------------------------------

def test_the_payload_publishes_the_pacing_interval(mgr, monkeypatch):
    monkeypatch.delenv("SESSION_CYCLE_SECONDS", raising=False)
    s = mgr.start(ALICE)
    assert s["expected_cycle_seconds"] == DEFAULT_CYCLE_SECONDS


def test_the_published_interval_follows_the_env_override(mgr, monkeypatch):
    monkeypatch.setenv("SESSION_CYCLE_SECONDS", "45")
    s = mgr.start(ALICE)
    assert s["expected_cycle_seconds"] == 45


def test_a_garbage_interval_falls_back_rather_than_raising(monkeypatch):
    """A typo'd env var must not take the daemon down."""
    monkeypatch.setenv("SESSION_CYCLE_SECONDS", "not-a-number")
    assert configured_cycle_seconds() == DEFAULT_CYCLE_SECONDS


def test_a_non_positive_interval_falls_back(monkeypatch):
    """Zero would spin the worker loop at full speed against the LLM."""
    for bad in ("0", "-30"):
        monkeypatch.setenv("SESSION_CYCLE_SECONDS", bad)
        assert configured_cycle_seconds() == DEFAULT_CYCLE_SECONDS


# --- the drift guard ----------------------------------------------------------

def test_the_worker_paces_on_the_interval_the_api_publishes(monkeypatch, tmp_path, clock):
    """THE property these two fields exist for. If the worker's cadence and the published
    `expected_cycle_seconds` diverge, the client's staleness maths is measured against a
    number the server never used."""
    monkeypatch.setenv("SESSION_CYCLE_SECONDS", "42")
    mgr = SessionManager(f"sqlite:///{tmp_path}/s.db", now_fn=clock)
    session = mgr.start(ALICE)

    async def _noop(_ctx):
        return [], None

    worker = session_worker.SessionWorker(mgr, object(), session, _noop)
    assert worker.cycle_seconds == session["expected_cycle_seconds"] == 42


def test_the_constant_is_not_duplicated():
    """session_worker re-exports rather than redefining. Two copies would drift the
    moment either was tuned."""
    assert session_worker.DEFAULT_CYCLE_SECONDS is DEFAULT_CYCLE_SECONDS


# --- refunds are not implemented yet ------------------------------------------

def test_seconds_refunded_is_an_honest_zero(mgr):
    """Mid-scan capacity refunds do not exist yet. Publishing 0 rather than omitting the
    field keeps the receipt honest and stops the client guessing at an absent value."""
    s = mgr.start(ALICE)
    assert s["seconds_refunded"] == 0
