"""Approve/reject flow: the API drives the state machine, the daemon owns the money.

Pins the M2 contract:
- approve dispatches to the daemon WHILE the session is still SETUP_PROPOSED (EXECUTING
  has no legal path back to SCANNING, so a refused fill must not strand the session);
- success ends the session with reason `trade_opened`;
- a refused re-validation resumes scanning; a daemon timeout changes nothing;
- reject marks the proposal REJECTED and resumes the meter.

Real stores over SQLite; the daemon is a recorded fake behind _dispatch_user_command.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import src.api.server as server
from src.core.preferences import PreferencesStore
from src.core.proposals import REJECTED, ProposalService
from src.core.session_manager import (
    SCANNING,
    SETUP_PROPOSED,
    TRADE_OPENED,
    SessionManager,
)

ALICE = "user-alice"
START = datetime(2026, 8, 2, 10, 0, 0)

SETUP = {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 64000.0,
    "stop_loss": 62000.0,
    "take_profit_levels": [68000.0],
    "confidence_score": 0.8,
}


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    clock = FakeClock()
    mgr = SessionManager(f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock)
    prefs = PreferencesStore(f"sqlite:///{tmp_path}/p.db")
    proposals = ProposalService(f"sqlite:///{tmp_path}/pr.db", now_fn=clock)
    monkeypatch.setattr(server, "session_manager", mgr)
    monkeypatch.setattr(server, "preferences_store", prefs)
    monkeypatch.setattr(server, "proposal_service", proposals)

    dispatched = []
    reply = {"value": {"approved": True, "execution_id": "EX1", "status": "completed"}}

    async def fake_dispatch(command, *, wait=True):
        dispatched.append(command)
        return reply["value"]

    monkeypatch.setattr(server, "_dispatch_user_command", fake_dispatch)
    server.app.dependency_overrides[server.require_user] = lambda: ALICE
    client = TestClient(server.app)
    yield client, mgr, prefs, proposals, clock, dispatched, reply
    server.app.dependency_overrides.clear()


def _proposed_session(mgr, prefs, proposals):
    """A session paused on a real pending proposal, the state approve expects."""
    session = mgr.start(ALICE)
    proposal = proposals.create(
        user_id=ALICE, session_id=session["session_id"],
        setup=SETUP, prefs=prefs.get(ALICE),
    )
    assert proposal is not None
    mgr.propose(session["session_id"])
    return session, proposal


def test_approve_executes_and_ends_the_session_with_trade_opened(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    session, proposal = _proposed_session(mgr, prefs, proposals)

    r = client.post("/api/session/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["status"] == "ended"
    assert body["session"]["end_reason"] == TRADE_OPENED
    assert body["execution"]["execution_id"] == "EX1"

    # The daemon got the exact proposal, tenant-stamped.
    assert dispatched[-1]["type"] == "approve_proposal"
    assert dispatched[-1]["user_id"] == ALICE
    assert dispatched[-1]["proposal_id"] == proposal["proposal_id"]


def test_refused_revalidation_resumes_scanning(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _proposed_session(mgr, prefs, proposals)
    reply["value"] = {"approved": False, "reason": "price_moved"}

    r = client.post("/api/session/approve")
    assert r.status_code == 409
    assert "price_moved" in r.json()["detail"]
    # The session is scanning again — the meter restarted, nothing stranded.
    assert mgr.get_active(ALICE)["status"] == SCANNING


def test_retryable_refusal_keeps_the_proposal_approvable(wired):
    """The price_moved dead-zone regression: the daemon leaves a drifted proposal
    PROPOSED (price may come back), so the API must keep the session paused — resuming
    scanning stranded a live proposal where neither approve nor a new cycle could
    reach it, while the meter burned."""
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _, proposal = _proposed_session(mgr, prefs, proposals)
    reply["value"] = {
        "approved": False, "reason": "price_moved_beyond_tolerance", "retryable": True,
    }

    r = client.post("/api/session/approve")
    assert r.status_code == 409
    assert "retry" in r.json()["detail"]
    # Clock still paused, proposal still on the table.
    assert mgr.get_active(ALICE)["status"] == SETUP_PROPOSED
    assert proposals.get_pending(ALICE)["proposal_id"] == proposal["proposal_id"]

    # Price came back: the retry executes.
    reply["value"] = {"approved": True, "execution_id": "EX2"}
    r = client.post("/api/session/approve")
    assert r.status_code == 200
    assert r.json()["session"]["end_reason"] == TRADE_OPENED


def test_lost_reply_recovery_never_books_twice(wired):
    """If the daemon booked but the reply outran the timeout, the proposal is EXECUTED
    while the session still looks paused. A retry must close the session as
    trade_opened and report the open position — resuming scanning here allowed a
    second trade in the same session."""
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    session, proposal = _proposed_session(mgr, prefs, proposals)
    # Simulate the daemon having completed the booking out of band.
    from src.core.proposals import EXECUTED
    proposals.mark(proposal["proposal_id"], EXECUTED, "TRADE-9")

    r = client.post("/api/session/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["execution"]["recovered"] is True
    assert body["execution"]["execution_id"] == "TRADE-9"
    assert body["session"]["status"] == "ended"
    assert body["session"]["end_reason"] == TRADE_OPENED
    assert dispatched == []  # nothing re-sent to the daemon; no double-book


def test_ending_a_session_decides_its_pending_proposal(wired):
    """An orphaned PROPOSED row from an ended session held the one-pending slot and
    haunted the next session's UI for the length of its TTL."""
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _, proposal = _proposed_session(mgr, prefs, proposals)

    r = client.post("/api/session/end")
    assert r.status_code == 200
    assert proposals.get(proposal["proposal_id"], ALICE)["status"] == REJECTED
    assert proposals.get_pending(ALICE) is None


def test_daemon_timeout_leaves_everything_retryable(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _, proposal = _proposed_session(mgr, prefs, proposals)
    reply["value"] = None  # dispatch timeout

    r = client.post("/api/session/approve")
    assert r.status_code == 504
    # Clock still paused, proposal still pending: the user can simply retry.
    assert mgr.get_active(ALICE)["status"] == SETUP_PROPOSED
    assert proposals.get_pending(ALICE)["proposal_id"] == proposal["proposal_id"]


def test_approve_with_expired_proposal_resumes_scanning(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _proposed_session(mgr, prefs, proposals)
    clock.advance(10 * 60)  # past the proposal TTL; get_pending expires it on read

    r = client.post("/api/session/approve")
    assert r.status_code == 409
    assert "expired" in r.json()["detail"].lower()
    assert mgr.get_active(ALICE)["status"] == SCANNING
    assert dispatched == []  # nothing was sent to the daemon


def test_approve_without_a_paused_session_is_409(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    mgr.start(ALICE)  # scanning, nothing proposed

    r = client.post("/api/session/approve")
    assert r.status_code == 409
    assert dispatched == []


def test_reject_marks_the_proposal_and_resumes_the_meter(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired
    _, proposal = _proposed_session(mgr, prefs, proposals)

    r = client.post("/api/session/reject")
    assert r.status_code == 200
    assert r.json()["status"] == SCANNING
    assert proposals.get(proposal["proposal_id"], ALICE)["status"] == REJECTED
    assert proposals.get_pending(ALICE) is None


def test_pending_proposal_endpoint_is_user_scoped(wired):
    client, mgr, prefs, proposals, clock, dispatched, reply = wired

    r = client.get("/api/proposals/pending")
    assert r.status_code == 200
    assert r.json()["proposal"] is None

    _, proposal = _proposed_session(mgr, prefs, proposals)
    r = client.get("/api/proposals/pending")
    assert r.json()["proposal"]["proposal_id"] == proposal["proposal_id"]

    # Another tenant's proposal must not surface for Alice: create one for Bob and
    # confirm Alice's view is unchanged.
    bob_session = mgr.start("user-bob")
    proposals.create(
        user_id="user-bob", session_id=bob_session["session_id"],
        setup={**SETUP, "symbol": "ETHUSDT", "entry_price": 2500.0,
               "stop_loss": 2400.0, "take_profit_levels": [2800.0]},
        prefs=prefs.get("user-bob"),
    )
    r = client.get("/api/proposals/pending")
    assert r.json()["proposal"]["proposal_id"] == proposal["proposal_id"]
