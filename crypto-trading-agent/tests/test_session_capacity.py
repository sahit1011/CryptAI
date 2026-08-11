"""Analysis capacity: the overview signal and the start gate.

Capacity exists so the client never reconciles two independent switches against each
other. The overview field is UX; the 503 on start is the correctness gate, and it is the
one that protects the user's metered minutes.

Fully mocked — no Redis, no Postgres.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import src.api.server as server
from src.core.preferences import PreferencesStore
from src.core.session_manager import SessionManager

ALICE = "user-alice"
START = datetime(2026, 8, 2, 10, 0, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class Switch:
    """Stands in for EngineSwitch."""

    def __init__(self, enabled=True, raises=False):
        self.enabled = enabled
        self.raises = raises

    async def status(self):
        if self.raises:
            raise RuntimeError("redis down")
        return {"enabled": self.enabled, "expires_in_seconds": None, "enabled_by": None}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def wired(tmp_path, clock, monkeypatch):
    mgr = SessionManager(f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock)
    prefs = PreferencesStore(f"sqlite:///{tmp_path}/p.db")
    monkeypatch.setattr(server, "session_manager", mgr)
    monkeypatch.setattr(server, "preferences_store", prefs)
    # A key is configured unless a test says otherwise.
    monkeypatch.setattr(server, "_engine_switch", lambda: Switch(enabled=True))

    server.app.dependency_overrides[server.require_user] = lambda: ALICE
    client = TestClient(server.app)
    yield client, mgr, monkeypatch
    server.app.dependency_overrides.clear()


PROVIDER_VARS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
)


def _with_llm_key(monkeypatch):
    """Exactly one provider key configured."""
    for var in PROVIDER_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _without_llm_key(monkeypatch):
    for var in PROVIDER_VARS:
        monkeypatch.delenv(var, raising=False)


# --- the overview signal ------------------------------------------------------

def test_capacity_is_reported_on_the_session_poll(wired, monkeypatch):
    """Folded into the poll so the client never reconciles two switches — that
    reconciliation was the bug this replaces."""
    client, _, mp = wired
    _with_llm_key(mp)
    body = client.get("/api/session").json()
    assert "capacity" in body
    assert body["capacity"] == {"available": True, "reason": None, "eta_seconds": None}


def test_a_disabled_engine_reads_as_paused(wired, monkeypatch):
    client, _, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))
    cap = client.get("/api/session").json()["capacity"]
    assert cap["available"] is False
    assert cap["reason"] == server.CAPACITY_PAUSED


def test_an_unreadable_switch_reads_as_degraded(wired, monkeypatch):
    """The pool halts work when it cannot read the switch, so a session started here
    would meter time against a stopped engine."""
    client, _, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(raises=True))
    cap = client.get("/api/session").json()["capacity"]
    assert cap["available"] is False
    assert cap["reason"] == server.CAPACITY_DEGRADED


def test_a_missing_switch_reads_as_available(wired, monkeypatch):
    """No Redis means no emergency stop EXISTS, which is not the same as one that is
    engaged. SessionWorkerPool treats an unconfigured switch as permission to work, and
    the gate must agree — otherwise the gate blocks sessions the pool would happily
    serve, or admits ones it refuses."""
    client, _, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: None)
    assert client.get("/api/session").json()["capacity"]["available"] is True


def test_no_provider_key_reads_as_model_error(wired, monkeypatch):
    """Checked before the switch: with no key, flipping the switch on still produces
    nothing, so 'paused' would point the owner at the wrong lever."""
    client, _, mp = wired
    _without_llm_key(mp)

    cap = client.get("/api/session").json()["capacity"]
    assert cap["available"] is False
    assert cap["reason"] == server.CAPACITY_MODEL_ERROR


def test_model_error_outranks_paused(wired, monkeypatch):
    client, _, mp = wired
    _without_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))

    assert client.get("/api/session").json()["capacity"]["reason"] == server.CAPACITY_MODEL_ERROR


def test_no_eta_is_ever_invented(wired, monkeypatch):
    """A fabricated countdown that expires with nothing changed is worse than admitting
    we do not know when an owner will flip the switch back."""
    client, _, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))
    assert client.get("/api/session").json()["capacity"]["eta_seconds"] is None


# --- the start gate (the correctness gate) ------------------------------------

def test_start_is_refused_with_a_structured_503(wired, monkeypatch):
    client, _, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))

    resp = client.post("/api/session/start")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["code"] == "capacity_unavailable"
    assert detail["reason"] == server.CAPACITY_PAUSED
    assert isinstance(detail["message"], str) and detail["message"]


def test_a_refused_start_creates_no_session_and_spends_no_quota(wired, monkeypatch):
    """The check runs BEFORE mgr.start, so there is nothing to roll back. Starting first
    and compensating would leave a window with a live clock and no engine."""
    client, mgr, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))

    assert client.post("/api/session/start").status_code == 503

    assert mgr.get_active(ALICE) is None, "a session row survived a refused start"
    assert mgr.used_today(ALICE) == 0, "a refused start consumed quota"
    assert mgr.active_sessions() == []


def test_start_succeeds_when_capacity_is_available(wired, monkeypatch):
    client, mgr, mp = wired
    _with_llm_key(mp)
    resp = client.post("/api/session/start")
    assert resp.status_code == 200
    assert mgr.get_active(ALICE) is not None


def test_an_unreadable_switch_also_blocks_start(wired, monkeypatch):
    """Fails CLOSED: a blocked tap is recoverable, spent quota is not until UTC midnight."""
    client, mgr, mp = wired
    _with_llm_key(mp)
    mp.setattr(server, "_engine_switch", lambda: Switch(raises=True))

    assert client.post("/api/session/start").status_code == 503
    assert mgr.get_active(ALICE) is None


def test_the_quota_gate_still_applies_when_capacity_is_fine(wired, monkeypatch, clock):
    """Capacity is an additional gate, not a replacement for the 429."""
    client, mgr, mp = wired
    _with_llm_key(mp)
    s = mgr.start(ALICE)
    clock.advance(1800)
    mgr.end(s["session_id"])

    assert client.post("/api/session/start").status_code == 429


def test_capacity_outranks_the_quota_gate(wired, monkeypatch, clock):
    """With analysis down, 'you are out of time today' is the wrong answer — it hides
    the real cause and sends the user to wait for a reset that will not help."""
    client, mgr, mp = wired
    _with_llm_key(mp)
    s = mgr.start(ALICE)
    clock.advance(1800)
    mgr.end(s["session_id"])
    mp.setattr(server, "_engine_switch", lambda: Switch(enabled=False))

    resp = client.post("/api/session/start")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "capacity_unavailable"
