"""Session and preferences endpoints: auth, tenancy scoping, and quota semantics.

The tenancy property here is structural rather than checked: no handler accepts a
session_id from the client. Every one resolves the session THROUGH the authenticated
user_id, so there is no id to guess. These tests pin that, because the obvious
"convenience" refactor — taking session_id in the body — would silently reintroduce an
IDOR against a backend that bypasses RLS.

Fully mocked: no Postgres, no Redis.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import src.api.server as server
from src.core.preferences import PreferencesStore
from src.core.session_manager import SessionManager

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


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def wired(tmp_path, clock, monkeypatch):
    """App with real stores over SQLite and a controllable authenticated principal."""
    mgr = SessionManager(
        f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock
    )
    prefs = PreferencesStore(f"sqlite:///{tmp_path}/p.db")
    monkeypatch.setattr(server, "session_manager", mgr)
    monkeypatch.setattr(server, "preferences_store", prefs)

    current = {"user": ALICE}
    server.app.dependency_overrides[server.require_user] = lambda: current["user"]
    client = TestClient(server.app)
    yield client, current, mgr, clock
    server.app.dependency_overrides.clear()


# --- auth --------------------------------------------------------------------

def test_every_session_endpoint_requires_auth(tmp_path, monkeypatch):
    """No override installed, so the real dependency runs and must reject."""
    monkeypatch.setattr(server, "session_manager", None)
    client = TestClient(server.app)
    for method, path in [
        ("get", "/api/session"),
        ("post", "/api/session/start"),
        ("post", "/api/session/end"),
        ("post", "/api/session/approve"),
        ("post", "/api/session/reject"),
        ("get", "/api/session/events"),
        ("get", "/api/preferences"),
        ("post", "/api/preferences"),
    ]:
        resp = (
            client.post(path, json={}) if method == "post" else client.get(path)
        )
        assert resp.status_code in (401, 403), f"{path} returned {resp.status_code}"


# --- tenancy -----------------------------------------------------------------

def test_no_endpoint_accepts_a_session_id_from_the_client(wired):
    """The structural guard. Passing another user's id must change nothing."""
    client, current, mgr, _ = wired

    alice = client.post("/api/session/start").json()
    current["user"] = BOB
    bob = client.post("/api/session/start").json()
    assert bob["session_id"] != alice["session_id"]

    # Bob tries to end Alice's session by supplying her id. The body is ignored.
    resp = client.post("/api/session/end", json={"session_id": alice["session_id"]})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == bob["session_id"], "ended another user's session"

    current["user"] = ALICE
    assert client.get("/api/session").json()["session"]["status"] == "scanning"


def test_each_user_sees_only_their_own_session(wired):
    client, current, _, _ = wired
    client.post("/api/session/start")

    current["user"] = BOB
    assert client.get("/api/session").json()["session"] is None

    current["user"] = ALICE
    assert client.get("/api/session").json()["session"] is not None


def test_quotas_are_per_user(wired):
    client, current, _, clock = wired
    client.post("/api/session/start")
    clock.advance(1800)
    client.post("/api/session/end")
    assert client.post("/api/session/start").status_code == 429

    current["user"] = BOB
    assert client.post("/api/session/start").status_code == 200


# --- lifecycle ---------------------------------------------------------------

def test_idle_is_a_normal_state_not_an_error(wired):
    """The dashboard renders "no session" constantly; it must not be a 404."""
    client, _, _, _ = wired
    body = client.get("/api/session").json()
    assert body["session"] is None
    assert body["remaining_today_seconds"] == 1800


def test_start_then_report_elapsed(wired):
    client, _, _, clock = wired
    client.post("/api/session/start")
    clock.advance(120)
    body = client.get("/api/session").json()
    assert body["session"]["elapsed_seconds"] == 120
    assert body["remaining_today_seconds"] == 1680


def test_exhausted_quota_is_429_not_403(wired):
    """A rate limit that resets, not a permission problem the user can act on."""
    client, _, _, clock = wired
    client.post("/api/session/start")
    clock.advance(1800)
    client.post("/api/session/end")

    resp = client.post("/api/session/start")
    assert resp.status_code == 429
    assert "today" in resp.json()["detail"]


def test_a_second_concurrent_session_is_409(wired):
    client, _, _, _ = wired
    client.post("/api/session/start")
    assert client.post("/api/session/start").status_code == 409


def test_approve_and_reject_require_a_pending_proposal(wired):
    """Approve is refused without a live Proposal row — the old contract (blindly flip
    to EXECUTING) meant a UI could show "executing" while nothing executed. The full
    proposal-backed approve path is pinned in tests/test_session_approve_flow.py.
    """
    client, _, mgr, _ = wired
    started = client.post("/api/session/start").json()

    # scanning -> executing is not a legal transition.
    assert client.post("/api/session/approve").status_code == 409

    mgr.propose(started["session_id"])
    assert client.post("/api/session/reject").json()["status"] == "scanning"

    # Paused session, but proposal_service is unwired in this fixture (init failure):
    # approve answers 503 and leaves the clock paused — it must not misdiagnose the
    # outage as "your proposal expired". The proposal-backed paths (including expiry →
    # 409 + resume) are pinned in tests/test_session_approve_flow.py.
    mgr.propose(started["session_id"])
    assert client.post("/api/session/approve").status_code == 503
    assert mgr.get_active(ALICE)["status"] == "setup_proposed"


def test_start_accepts_and_records_a_channel(wired):
    client, _, mgr, _ = wired
    r = client.post("/api/session/start", json={"channel": "scalp"})
    assert r.status_code == 200
    assert r.json()["channel"] == "scalp"


def test_start_rejects_an_unknown_channel(wired):
    client, _, mgr, _ = wired
    r = client.post("/api/session/start", json={"channel": "moon"})
    assert r.status_code == 409
    assert mgr.get_active(ALICE) is None


def test_rejecting_resumes_the_meter_via_the_api(wired):
    client, _, mgr, clock = wired
    started = client.post("/api/session/start").json()
    clock.advance(60)
    mgr.propose(started["session_id"])

    clock.advance(600)  # deliberation, unmetered
    assert client.get("/api/session").json()["session"]["elapsed_seconds"] == 60

    client.post("/api/session/reject")
    clock.advance(30)
    assert client.get("/api/session").json()["session"]["elapsed_seconds"] == 90


def test_operations_without_a_session_are_404(wired):
    client, _, _, _ = wired
    for path in ("/api/session/end", "/api/session/approve", "/api/session/reject"):
        assert client.post(path).status_code == 404
    assert client.get("/api/session/events").status_code == 404


def test_events_feed_returns_the_agent_trail(wired):
    client, _, mgr, _ = wired
    started = client.post("/api/session/start").json()
    mgr.log_agent_step(started["session_id"], "structure_analyst", "scanning BTCUSDT")

    body = client.get("/api/session/events").json()
    assert body["session_id"] == started["session_id"]
    assert any(e["agent"] == "structure_analyst" for e in body["events"])


# --- degraded ----------------------------------------------------------------

def test_endpoints_503_when_the_store_is_unconfigured(wired, monkeypatch):
    """Explicit 503 beats a 500 traceback when a store failed to initialise."""
    client, _, _, _ = wired
    monkeypatch.setattr(server, "session_manager", None)
    assert client.get("/api/session").status_code == 503
    monkeypatch.setattr(server, "preferences_store", None)
    assert client.get("/api/preferences").status_code == 503


# --- preferences -------------------------------------------------------------

def test_defaults_are_returned_for_a_new_user(wired):
    client, _, _, _ = wired
    prefs = client.get("/api/preferences").json()
    assert prefs["max_concurrent_positions"] == 1
    assert prefs["max_risk_per_trade_pct"] == 1.0


def test_partial_update_leaves_other_fields_alone(wired):
    client, _, _, _ = wired
    client.post("/api/preferences", json={"risk_appetite": "aggressive"})
    client.post("/api/preferences", json={"trading_capital": 25000})
    prefs = client.get("/api/preferences").json()
    assert prefs["risk_appetite"] == "aggressive"
    assert prefs["trading_capital"] == 25000


def test_unknown_fields_are_rejected_by_the_schema(wired):
    """extra=forbid, so a typo is a 422 rather than a silently ignored setting."""
    client, _, _, _ = wired
    resp = client.post("/api/preferences", json={"max_rissk_per_trade_pct": 2.0})
    assert resp.status_code == 422


def test_invalid_enum_is_a_400(wired):
    client, _, _, _ = wired
    assert client.post("/api/preferences", json={"risk_appetite": "yolo"}).status_code == 400


def test_risk_reward_below_one_is_rejected_at_the_schema(wired):
    client, _, _, _ = wired
    assert client.post("/api/preferences", json={"min_risk_reward": 0.4}).status_code == 422


def test_plan_caps_clamp_a_greedy_request(wired):
    """The free tier allows 1% risk and 1 concurrent position; asking for more clamps."""
    client, _, _, _ = wired
    got = client.post(
        "/api/preferences",
        json={"max_risk_per_trade_pct": 25.0, "max_concurrent_positions": 15},
    ).json()
    assert got["max_risk_per_trade_pct"] <= 1.0
    assert got["max_concurrent_positions"] <= 1


def test_an_empty_body_is_a_no_op_not_an_error(wired):
    client, _, _, _ = wired
    before = client.get("/api/preferences").json()
    assert client.post("/api/preferences", json={}).json() == before
