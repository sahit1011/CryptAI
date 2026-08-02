"""Session metering: the durable clock, the state machine, and both quota gates.

Runs against SQLite in-memory — no Postgres, no Redis. The clock is injected, so nothing
here sleeps: per CLAUDE.md, waiting out a timer is how the suite once spent 61 seconds in
a single test. Time is advanced by moving the fake clock forward.
"""
from datetime import datetime, timedelta

import pytest

from src.core.session_manager import (
    COST_CAP,
    ENDED,
    EXECUTING,
    QUOTA_EXHAUSTED,
    SCANNING,
    SETUP_PROPOSED,
    TRADE_OPENED,
    IllegalTransition,
    QuotaExhausted,
    SessionError,
    SessionManager,
)

START = datetime(2026, 8, 2, 10, 0, 0)
USER = "user-aaa"


class FakeClock:
    def __init__(self, start=START):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def mgr(clock, tmp_path):
    # A file-backed SQLite DB, so the manager's separate sessionmaker connections all
    # see the same data (an in-memory DB would give each connection its own).
    return SessionManager(
        f"sqlite:///{tmp_path}/sessions.db",
        daily_quota_seconds=1800,
        cost_cap_micros=500_000,
        now_fn=clock,
    )


# --- the durable clock -------------------------------------------------------

def test_clock_accrues_only_while_scanning(mgr, clock):
    s = mgr.start(USER)
    assert s["clock_running"] is True
    clock.advance(60)
    assert mgr.get(s["session_id"])["elapsed_seconds"] == 60


def test_proposing_pauses_the_clock(mgr, clock):
    """A user is not charged for deliberating on a proposal."""
    s = mgr.start(USER)
    clock.advance(60)
    mgr.propose(s["session_id"])

    clock.advance(600)  # ten minutes of thinking

    got = mgr.get(s["session_id"])
    assert got["clock_running"] is False
    assert got["elapsed_seconds"] == 60, "deliberation time was charged to the user"


def test_rejecting_resumes_the_clock(mgr, clock):
    s = mgr.start(USER)
    clock.advance(60)
    mgr.propose(s["session_id"])
    clock.advance(600)
    mgr.reject(s["session_id"])
    clock.advance(30)

    got = mgr.get(s["session_id"])
    assert got["clock_running"] is True
    assert got["elapsed_seconds"] == 90, "scanning before and after the pause should sum"


def test_executing_is_not_metered(mgr, clock):
    s = mgr.start(USER)
    clock.advance(60)
    mgr.propose(s["session_id"])
    mgr.approve(s["session_id"])
    clock.advance(300)

    got = mgr.get(s["session_id"])
    assert got["clock_running"] is False
    assert got["elapsed_seconds"] == 60


def test_elapsed_survives_a_restart_mid_session(mgr, clock, tmp_path):
    """The clock is derived from stored timestamps, not held in memory.

    A restart must lose at most the in-flight segment — and must never lose the whole
    session's accounting, which would silently grant the user unlimited time.
    """
    s = mgr.start(USER)
    clock.advance(120)
    mgr.propose(s["session_id"])  # settles 120s into accrued

    # A brand-new manager over the same database, as after a process restart.
    revived = SessionManager(
        f"sqlite:///{tmp_path}/sessions.db",
        daily_quota_seconds=1800,
        now_fn=clock,
    )
    assert revived.get(s["session_id"])["elapsed_seconds"] == 120


def test_a_backwards_clock_cannot_refund_time(mgr, clock):
    """NTP corrections and restores onto skewed machines both move clocks backwards."""
    s = mgr.start(USER)
    clock.advance(100)
    assert mgr.get(s["session_id"])["elapsed_seconds"] == 100

    clock.now -= timedelta(seconds=500)
    assert mgr.get(s["session_id"])["elapsed_seconds"] >= 0, "negative elapsed refunded time"


def test_no_countdown_is_ever_stored(mgr, clock):
    """Elapsed is derived. Storing a countdown makes a missed decrement free time."""
    s = mgr.start(USER)
    clock.advance(45)
    a = mgr.get(s["session_id"])["elapsed_seconds"]
    clock.advance(45)
    b = mgr.get(s["session_id"])["elapsed_seconds"]
    assert (a, b) == (45, 90), "elapsed did not track the wall clock"


# --- daily quota -------------------------------------------------------------

def test_quota_is_daily_across_sessions_not_per_session(mgr, clock):
    """Otherwise starting a new session resets the quota — unlimited time by restart."""
    s1 = mgr.start(USER)
    clock.advance(1000)
    mgr.end(s1["session_id"])

    assert mgr.used_today(USER) == 1000
    assert mgr.remaining_today(USER) == 800

    s2 = mgr.start(USER)
    clock.advance(100)
    assert mgr.used_today(USER) == 1100


def test_starting_with_no_time_left_is_refused(mgr, clock):
    s = mgr.start(USER)
    clock.advance(1800)
    mgr.end(s["session_id"])

    with pytest.raises(QuotaExhausted):
        mgr.start(USER)


def test_a_new_session_is_granted_only_the_time_that_remains(mgr, clock):
    s1 = mgr.start(USER)
    clock.advance(1500)
    mgr.end(s1["session_id"])

    s2 = mgr.start(USER)
    assert s2["quota_seconds_granted"] == 300


def test_explicit_quota_request_is_clamped_to_the_daily_cap(mgr, clock):
    """The quota-bypass regression: an explicit quota_seconds must never exceed what is
    left today. Before the fix, start(quota_seconds=86400) granted a 24h session against
    the 1800s daily quota."""
    s = mgr.start(USER, quota_seconds=86_400)
    assert s["quota_seconds_granted"] == 1800

    # And the tick meter then honours the clamp: the session ends at the daily cap.
    clock.advance(1800)
    assert mgr.tick(s["session_id"])["status"] == ENDED


def test_explicit_quota_request_is_clamped_to_remaining_after_prior_use(mgr, clock):
    s1 = mgr.start(USER)
    clock.advance(1500)
    mgr.end(s1["session_id"])  # 300s left today

    s2 = mgr.start(USER, quota_seconds=86_400)
    assert s2["quota_seconds_granted"] == 300


def test_explicit_quota_request_may_ask_for_less(mgr, clock):
    """Clamping is one-directional — a short 10-minute session is still honoured."""
    s = mgr.start(USER, quota_seconds=600)
    assert s["quota_seconds_granted"] == 600


# --- channel -----------------------------------------------------------------

def test_session_records_its_channel(mgr, clock):
    s = mgr.start(USER, channel="scalp")
    assert s["channel"] == "scalp"
    assert mgr.get_active(USER)["channel"] == "scalp"


def test_channel_defaults_to_none(mgr, clock):
    s = mgr.start(USER)
    assert s["channel"] is None


def test_an_unknown_channel_is_rejected(mgr, clock):
    with pytest.raises(SessionError):
        mgr.start(USER, channel="hodl")
    # And the rejected start left no session behind.
    assert mgr.get_active(USER) is None


def test_ensure_schema_adds_channel_to_a_preexisting_table(tmp_path, clock):
    """The deploy-critical self-heal: a `sessions` table created before `channel`
    existed (checkfirst never adds columns) must gain it on next SessionManager init,
    regardless of whether the alembic migration has run."""
    from sqlalchemy import create_engine, inspect, text

    db = f"sqlite:///{tmp_path}/legacy.db"
    # Simulate the legacy table: everything EXCEPT channel.
    legacy = create_engine(db)
    with legacy.begin() as conn:
        conn.execute(text(
            "CREATE TABLE sessions ("
            "id INTEGER PRIMARY KEY, session_id VARCHAR(50), user_id VARCHAR(64), "
            "status VARCHAR(24), quota_seconds_granted INTEGER, "
            "metered_seconds_accrued INTEGER, clock_started_at DATETIME, "
            "llm_tokens_used INTEGER, llm_cost_micros INTEGER, "
            "llm_cost_cap_micros INTEGER, trading_day DATETIME, "
            "cycles_completed INTEGER, started_at DATETIME, ended_at DATETIME, "
            "end_reason VARCHAR(40))"
        ))
    assert "channel" not in {c["name"] for c in inspect(legacy).get_columns("sessions")}
    legacy.dispose()

    # Booting a SessionManager on that DB must add the column and then work.
    mgr = SessionManager(db, daily_quota_seconds=1800, now_fn=clock)
    cols = {c["name"] for c in inspect(mgr.engine).get_columns("sessions")}
    assert "channel" in cols
    s = mgr.start(USER, channel="swing")
    assert s["channel"] == "swing"


def test_ensure_schema_is_idempotent_across_reconstruction(tmp_path, clock):
    """Two SessionManagers over the same DB: the second sees channel already present and
    skips the ALTER — no duplicate-column crash on the common re-boot case."""
    db = f"sqlite:///{tmp_path}/shared.db"
    first = SessionManager(db, daily_quota_seconds=1800, now_fn=clock)  # adds channel
    second = SessionManager(db, daily_quota_seconds=1800, now_fn=clock)  # sees it, skips
    assert second.start(USER, channel="scalp")["channel"] == "scalp"
    _ = first


def test_ensure_schema_swallows_a_concurrent_duplicate_add(tmp_path, clock, monkeypatch):
    """The real TOCTOU (backend + daemon boot together on Render): _ensure_schema's
    inspect reports channel ABSENT (stale), so it runs the ALTER — which the DB rejects
    because a concurrent boot already added it. The except must re-inspect and swallow,
    not propagate (propagating leaves session_manager=None and disables the session
    plane). Forced deterministically: `_ensure_schema` does `from sqlalchemy import
    inspect` at call time, so patching sqlalchemy.inspect controls what it sees."""
    import sqlalchemy

    db = f"sqlite:///{tmp_path}/race.db"
    mgr = SessionManager(db, daily_quota_seconds=1800, now_fn=clock)  # channel really exists

    class _FakeInspector:
        def __init__(self, has_channel):
            self._has = has_channel

        def get_table_names(self):
            return ["sessions"]

        def get_columns(self, _table):
            cols = [{"name": "id"}, {"name": "session_id"}]
            return cols + ([{"name": "channel"}] if self._has else [])

    calls = {"n": 0}

    def fake_inspect(_engine):
        calls["n"] += 1
        # 1st call: the `existing` check — lie that channel is absent, forcing the ALTER.
        # 2nd call: the post-failure re-check — tell the truth (it exists), so it swallows.
        return _FakeInspector(has_channel=calls["n"] >= 2)

    monkeypatch.setattr(sqlalchemy, "inspect", fake_inspect)
    mgr._ensure_schema()  # ALTER duplicate -> caught -> re-inspect -> swallow. No raise.
    assert calls["n"] == 2  # it did try the ALTER and did re-check


def test_quota_resets_at_utc_midnight(mgr, clock):
    s = mgr.start(USER)
    clock.advance(1800)
    mgr.end(s["session_id"])
    assert mgr.remaining_today(USER) == 0

    clock.now = datetime(2026, 8, 3, 0, 0, 1)
    assert mgr.remaining_today(USER) == 1800
    mgr.start(USER)  # must not raise


def test_quotas_are_isolated_between_users(mgr, clock):
    s = mgr.start(USER)
    clock.advance(1800)
    mgr.end(s["session_id"])

    assert mgr.remaining_today(USER) == 0
    assert mgr.remaining_today("user-bbb") == 1800
    mgr.start("user-bbb")


def test_tick_ends_the_session_when_time_runs_out(mgr, clock):
    s = mgr.start(USER)
    clock.advance(1801)
    got = mgr.tick(s["session_id"])
    assert got["status"] == ENDED
    assert got["end_reason"] == QUOTA_EXHAUSTED


def test_only_one_live_session_per_user(mgr, clock):
    """Two concurrent sessions would double-spend the same daily quota."""
    mgr.start(USER)
    with pytest.raises(SessionError):
        mgr.start(USER)


# --- cost cap ----------------------------------------------------------------

def test_cost_cap_ends_the_session(mgr, clock):
    """Minutes are the product; spend is the safety net. 30 minutes of aggressive
    multi-agent analysis is bounded in time but not in cost."""
    s = mgr.start(USER)
    got = mgr.record_llm_usage(s["session_id"], tokens=100_000, cost_micros=600_000)
    assert got["status"] == ENDED
    assert got["end_reason"] == COST_CAP


def test_cost_below_the_cap_keeps_the_session_alive(mgr, clock):
    s = mgr.start(USER)
    got = mgr.record_llm_usage(s["session_id"], tokens=1_000, cost_micros=1_000)
    assert got["status"] == SCANNING
    assert got["llm_cost_micros"] == 1_000


def test_cost_accumulates_across_calls(mgr, clock):
    """Small charges must sum toward the cap; the boundary is checked from both sides."""
    s = mgr.start(USER)

    # 4 x 120_000 = 480_000, still under the 500_000 cap.
    for _ in range(4):
        got = mgr.record_llm_usage(s["session_id"], tokens=1_000, cost_micros=120_000)
    assert got["status"] == SCANNING, "ended early, below the cap"
    assert got["llm_cost_micros"] == 480_000

    # The fifth call crosses it.
    got = mgr.record_llm_usage(s["session_id"], tokens=1_000, cost_micros=120_000)
    assert got["status"] == ENDED
    assert got["end_reason"] == COST_CAP


def test_spend_after_the_cap_is_still_recorded_but_does_not_revive_the_session(mgr, clock):
    """Late-arriving cost must be counted, not rejected.

    Spend is recorded AFTER the call returns, so a request in flight when the cap trips
    will report afterwards. Refusing it would make the accounting understate real money
    spent. The session stays ended; enforcement lives at the call site, which checks
    status via tick() before making the next request — the manager cannot stop a caller
    that never asks.
    """
    s = mgr.start(USER)
    sid = s["session_id"]

    ended = mgr.record_llm_usage(sid, tokens=1, cost_micros=600_000)
    assert ended["status"] == ENDED
    assert ended["end_reason"] == COST_CAP

    after = mgr.record_llm_usage(sid, tokens=500, cost_micros=25_000)
    assert after["status"] == ENDED, "an ended session was revived by late spend"
    assert after["end_reason"] == COST_CAP, "the original end reason was overwritten"
    assert after["llm_cost_micros"] == 625_000, "late spend was dropped from accounting"
    assert after["llm_tokens_used"] == 501


def test_cost_cap_is_reported_over_time_when_both_are_breached(mgr, clock):
    """Support needs the binding constraint, and cost is the one that matters."""
    s = mgr.start(USER)
    clock.advance(1801)
    got = mgr.record_llm_usage(s["session_id"], tokens=1, cost_micros=600_000)
    assert got["end_reason"] == COST_CAP


# --- state machine -----------------------------------------------------------

def test_illegal_transitions_raise(mgr, clock):
    """A permissive state machine turns a race into a billing bug."""
    s = mgr.start(USER)
    sid = s["session_id"]

    with pytest.raises(IllegalTransition):
        mgr.approve(sid)  # scanning -> executing skips the proposal

    mgr.propose(sid)
    with pytest.raises(IllegalTransition):
        mgr.propose(sid)  # already proposed

    mgr.approve(sid)
    with pytest.raises(IllegalTransition):
        mgr.reject(sid)  # executing -> scanning


def test_an_ended_session_is_terminal(mgr, clock):
    s = mgr.start(USER)
    mgr.end(s["session_id"])
    for op in (mgr.propose, mgr.reject, mgr.approve):
        with pytest.raises(IllegalTransition):
            op(s["session_id"])


def test_the_full_happy_path(mgr, clock):
    s = mgr.start(USER)
    sid = s["session_id"]
    clock.advance(120)

    assert mgr.propose(sid)["status"] == SETUP_PROPOSED
    clock.advance(45)  # unmetered deliberation
    assert mgr.approve(sid)["status"] == EXECUTING

    # The trade is open: the session ends and the monitor takes over, unmetered.
    final = mgr.end(sid, TRADE_OPENED)
    assert final["status"] == ENDED
    assert final["end_reason"] == TRADE_OPENED
    assert final["elapsed_seconds"] == 120
    assert mgr.remaining_today(USER) == 1680


def test_ending_a_session_does_not_consume_the_rest_of_the_quota(mgr, clock):
    """A trade opening ends the session. The unused minutes stay available, because
    monitoring is unmetered and the user may want to scan again after the trade closes.
    """
    s = mgr.start(USER)
    clock.advance(60)
    mgr.end(s["session_id"], TRADE_OPENED)
    assert mgr.remaining_today(USER) == 1740
    mgr.start(USER)  # must not raise


# --- audit trail -------------------------------------------------------------

def test_every_transition_is_recorded(mgr, clock):
    s = mgr.start(USER)
    sid = s["session_id"]
    mgr.propose(sid)
    mgr.reject(sid)
    mgr.end(sid)

    events = mgr.events(sid)
    transitions = [(e["from_status"], e["to_status"]) for e in events if e["event_type"] == "state_change"]
    assert (None, SCANNING) in transitions
    assert (SCANNING, SETUP_PROPOSED) in transitions
    assert (SETUP_PROPOSED, SCANNING) in transitions
    assert (SCANNING, ENDED) in transitions


def test_agent_steps_are_recorded_for_the_user_facing_feed(mgr, clock):
    s = mgr.start(USER)
    mgr.log_agent_step(s["session_id"], "structure_analyst", "scanning BTCUSDT", {"symbol": "BTCUSDT"})
    steps = [e for e in mgr.events(s["session_id"]) if e["event_type"] == "agent_step"]
    assert len(steps) == 1
    assert steps[0]["agent"] == "structure_analyst"
    assert steps[0]["payload"] == {"symbol": "BTCUSDT"}


def test_events_are_scoped_to_their_session(mgr, clock):
    a = mgr.start(USER)
    mgr.end(a["session_id"])
    b = mgr.start(USER)

    mgr.log_agent_step(b["session_id"], "x", "only in b")
    messages = [e["message"] for e in mgr.events(a["session_id"])]
    assert "only in b" not in messages
