"""GET /api/monitors — joins the caller's open positions with live monitor status.

User-scoped (never leaks another tenant's monitors); a symbol with no fresh status
reads monitored=false rather than implying protection that isn't running.
"""
import pytest
from fastapi.testclient import TestClient

import src.api.server as server
from src.core.monitor_worker import monitor_status_key

ALICE = "user-alice"


class _FakeState:
    def __init__(self):
        self.positions: dict = {}   # user_id -> [pos dicts]
        self.kv: dict = {}          # key -> value

    async def get_positions(self, user_id=None):
        return self.positions.get(user_id, [])

    async def get(self, key):
        return self.kv.get(key)


@pytest.fixture
def wired(monkeypatch):
    state = _FakeState()
    monkeypatch.setattr(server, "state_manager", state)
    server.app.dependency_overrides[server.require_user] = lambda: ALICE
    client = TestClient(server.app)
    yield client, state
    server.app.dependency_overrides.clear()


def test_no_positions_returns_an_empty_list(wired):
    client, state = wired
    r = client.get("/api/monitors")
    assert r.status_code == 200
    assert r.json() == {"monitors": []}


def test_a_watched_position_reports_its_status(wired):
    client, state = wired
    state.positions[ALICE] = [{"symbol": "BTCUSDT"}]
    state.kv[monitor_status_key(ALICE, "BTCUSDT")] = {
        "symbol": "BTCUSDT", "decision": "hold", "reason": None, "checks": 3,
        "favorable_pct": 0.4,
    }

    r = client.get("/api/monitors")
    body = r.json()["monitors"]
    assert len(body) == 1
    assert body[0]["symbol"] == "BTCUSDT"
    assert body[0]["monitored"] is True
    assert body[0]["status"]["decision"] == "hold"


def test_an_open_position_without_a_status_reads_unmonitored(wired):
    client, state = wired
    state.positions[ALICE] = [{"symbol": "ETHUSDT"}]  # no monitor status key set

    body = client.get("/api/monitors").json()["monitors"]
    assert body == [{"symbol": "ETHUSDT", "monitored": False, "status": None}]


def test_monitors_are_scoped_to_the_caller(wired):
    client, state = wired
    # Alice has one position; Bob's monitor status must never surface for Alice.
    state.positions[ALICE] = [{"symbol": "BTCUSDT"}]
    state.kv[monitor_status_key(ALICE, "BTCUSDT")] = {"symbol": "BTCUSDT", "decision": "hold"}
    state.kv[monitor_status_key("user-bob", "SOLUSDT")] = {"symbol": "SOLUSDT", "decision": "exit"}

    body = client.get("/api/monitors").json()["monitors"]
    assert [m["symbol"] for m in body] == ["BTCUSDT"]


def test_requires_a_state_manager(monkeypatch):
    monkeypatch.setattr(server, "state_manager", None)
    server.app.dependency_overrides[server.require_user] = lambda: ALICE
    try:
        client = TestClient(server.app)
        assert client.get("/api/monitors").status_code == 503
    finally:
        server.app.dependency_overrides.clear()
