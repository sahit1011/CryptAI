"""Strategy profile scaffolding: resolution, the session-start API surface, and the
S1 stub strategy's no-raise guarantee.

Three properties pinned here:

1. **Default is untouchable.** No `strategy` field means S2 and byte-identical
   pre-S1 behavior — including writing NOTHING extra to Redis.
2. **Refusal is honest and typed.** S1 on a deployment without S1_ENABLED=true is
   a structured 403, never a silent downgrade; garbage is a 422. Neither creates
   a session row.
3. **The S1 stub never raises.** Short, missing, or malformed data always answers
   None — with or without the parallel-owned s1_signals contract module present
   (its import is lazy; a fake is injected via sys.modules to test composition).

Fully mocked: no Postgres, no Redis, no live services. Style follows
tests/test_session_api.py (real SessionManager over SQLite, overridden auth).
"""
import sys
import types
import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import src.api.server as server
from src.core.session_manager import SessionManager
from src.strategy.profiles import (
    DEFAULT_PROFILE,
    ProfileError,
    ProfileUnavailable,
    ProfileUnknown,
    StrategyProfile,
    resolve_profile,
    s1_enabled,
    session_strategy_key,
)
from src.strategy.s1_intraday import S1IntradayStrategy

ALICE = "user-alice"


# --- resolve_profile matrix ----------------------------------------------------


@pytest.fixture(autouse=True)
def _s1_flag_unset(monkeypatch):
    """Every test starts from the shipped default: S1_ENABLED absent (off)."""
    monkeypatch.delenv("S1_ENABLED", raising=False)


def test_absent_and_blank_resolve_to_the_default_s2():
    assert DEFAULT_PROFILE is StrategyProfile.S2_SWING
    assert resolve_profile(None) is StrategyProfile.S2_SWING
    assert resolve_profile("") is StrategyProfile.S2_SWING
    assert resolve_profile("   ") is StrategyProfile.S2_SWING


def test_s2_resolves_case_insensitively_with_or_without_the_flag():
    for token in ("s2", "S2", " s2 ", "s2_swing", "S2_SWING"):
        assert resolve_profile(token) is StrategyProfile.S2_SWING


def test_s1_disabled_raises_the_typed_unavailable_error(monkeypatch):
    with pytest.raises(ProfileUnavailable):
        resolve_profile("s1")
    # An explicit false and truthy-but-wrong spellings are equally OFF: the flag
    # has exactly one ON spelling so an unvalidated strategy can't be enabled by
    # accident.
    for off in ("false", "0", "yes", "on", "enabled"):
        monkeypatch.setenv("S1_ENABLED", off)
        assert not s1_enabled()
        with pytest.raises(ProfileUnavailable):
            resolve_profile("s1_intraday")


def test_s1_enabled_resolves_case_insensitively(monkeypatch):
    monkeypatch.setenv("S1_ENABLED", "true")
    for token in ("s1", "S1", " s1 ", "s1_intraday", "S1_Intraday"):
        assert resolve_profile(token) is StrategyProfile.S1_INTRADAY
    monkeypatch.setenv("S1_ENABLED", " TRUE ")
    assert resolve_profile("s1") is StrategyProfile.S1_INTRADAY


def test_garbage_is_rejected_as_unknown_not_unavailable(monkeypatch):
    # Unknown beats unavailable regardless of the flag: garbage must be reported
    # as garbage, not as a feature toggle problem.
    for flag in (None, "true"):
        if flag:
            monkeypatch.setenv("S1_ENABLED", flag)
        for bad in ("moon", "s3", "swing", "s 1", "s1;drop"):
            with pytest.raises(ProfileError) as excinfo:
                resolve_profile(bad)
            assert isinstance(excinfo.value, ProfileUnknown)
            assert not isinstance(excinfo.value, ProfileUnavailable)


# --- the session-start API surface ---------------------------------------------


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """App with a real SessionManager over SQLite and an authenticated principal.

    Capacity is made available (provider key present) so these tests exercise the
    strategy field, not the capacity gate — same trick as test_session_api.py.
    server.state_manager stays None (module default) so the Redis-marker write
    path must degrade gracefully; the marker itself is tested with a fake below.
    """
    mgr = SessionManager(f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800)
    monkeypatch.setattr(server, "session_manager", mgr)
    monkeypatch.setattr(server, "state_manager", None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    server.app.dependency_overrides[server.require_user] = lambda: ALICE
    client = TestClient(server.app)
    # The API's in-process rate limiter keys callers by Authorization-header hash,
    # else client IP — and every TestClient in the suite shares "ip:testclient".
    # The suite's POST tests collectively ride near the 60/min write budget, so a
    # unique token per test keeps this file from spending (or being starved by)
    # the shared key. Auth itself is bypassed via the dependency override above;
    # the header only individualizes the limiter key.
    client.headers["Authorization"] = f"Bearer test-{uuid.uuid4().hex}"
    yield client, mgr
    server.app.dependency_overrides.clear()


class _RecordingState:
    """Stands in for server.state_manager; records set() calls, nothing else."""

    def __init__(self):
        self.calls = []

    async def set(self, key, value, ttl=None):
        self.calls.append((key, value, ttl))


def test_start_without_strategy_is_default_s2_and_unchanged(wired, monkeypatch):
    client, mgr = wired
    state = _RecordingState()
    monkeypatch.setattr(server, "state_manager", state)

    r = client.post("/api/session/start")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "s2_swing"
    assert body["status"] == "scanning"
    # The default path writes NOTHING extra: pre-S1 behavior, byte for byte.
    assert state.calls == []


def test_start_with_explicit_s2_needs_no_flag(wired):
    client, _ = wired
    r = client.post("/api/session/start", json={"strategy": "S2"})
    assert r.status_code == 200
    assert r.json()["strategy"] == "s2_swing"


def test_start_with_s1_disabled_is_a_structured_403_and_creates_nothing(wired):
    client, mgr = wired
    r = client.post("/api/session/start", json={"strategy": "s1"})
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["code"] == "strategy_unavailable"
    assert "not enabled" in detail["message"]
    # Refused BEFORE mgr.start: no session row, no quota spent.
    assert mgr.get_active(ALICE) is None


def test_start_with_unknown_strategy_is_422_and_creates_nothing(wired, monkeypatch):
    client, mgr = wired
    monkeypatch.setenv("S1_ENABLED", "true")  # unknown is unknown even when S1 is on
    r = client.post("/api/session/start", json={"strategy": "moon"})
    assert r.status_code == 422
    assert mgr.get_active(ALICE) is None


def test_start_with_s1_enabled_succeeds_and_records_the_marker(wired, monkeypatch):
    client, _ = wired
    monkeypatch.setenv("S1_ENABLED", "true")
    state = _RecordingState()
    monkeypatch.setattr(server, "state_manager", state)

    r = client.post("/api/session/start", json={"strategy": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "s1_intraday"
    assert body["status"] == "scanning"

    # The profile is carried in the existing Redis/session-state mechanism under
    # the shared key builder, TTL-bounded (see the persistence-gap comment at the
    # write site in server.py).
    assert len(state.calls) == 1
    key, value, ttl = state.calls[0]
    assert key == session_strategy_key(body["session_id"])
    assert value == "s1_intraday"
    assert ttl is not None and ttl > 0


def test_start_with_s1_survives_a_missing_state_manager(wired, monkeypatch):
    """Hermetic/degraded boot: no Redis at all must not block a session start."""
    client, _ = wired  # fixture pins server.state_manager = None
    monkeypatch.setenv("S1_ENABLED", "true")
    r = client.post("/api/session/start", json={"strategy": "s1"})
    assert r.status_code == 200
    assert r.json()["strategy"] == "s1_intraday"


# --- S1IntradayStrategy: the no-raise guarantee ---------------------------------


def _candle(o, h, lo, c, v=100.0, tbv=50.0):
    return {
        "open": o, "high": h, "low": lo, "close": c,
        "volume": v, "taker_buy_volume": tbv,
    }


def _flat_candles(n, price=105.0):
    return [_candle(price, price + 1, price - 1, price) for _ in range(n)]


def test_evaluate_returns_none_on_empty_or_missing_series():
    s = S1IntradayStrategy()
    assert s.evaluate([], [], "long") is None
    assert s.evaluate(None, None, "long") is None
    assert s.evaluate(_flat_candles(50), [], "long") is None
    assert s.evaluate([], _flat_candles(50), "long") is None


def test_evaluate_returns_none_on_short_series():
    s = S1IntradayStrategy()
    # Too few 1h candles for any confirmed swing; too few 1m for any confirmation.
    assert s.evaluate(_flat_candles(50), _flat_candles(3), "long") is None
    assert s.evaluate(_flat_candles(2), _flat_candles(50), "short") is None


def test_evaluate_returns_none_on_missing_or_garbage_direction():
    s = S1IntradayStrategy()
    candles = _flat_candles(50)
    for bad in (None, "", "sideways", "LONGSHORT", 42):
        assert s.evaluate(candles, candles, bad) is None


def test_evaluate_never_raises_on_malformed_candles():
    s = S1IntradayStrategy()
    junk = [{"foo": "bar"}] * 50  # long enough to pass the length guards
    assert s.evaluate(junk, junk, "long") is None
    mixed = [_candle(105, 106, 104, 105)] * 20 + [None, 42, "candle"] * 10
    assert s.evaluate(mixed, mixed, "short") is None


# --- S1IntradayStrategy: composition against a fake contract --------------------
#
# The real s1_signals is owned by a parallel workstream; a fake injected into
# sys.modules pins THIS module's composition (swing → band → touch → participation
# → confirmation) hermetically and deterministically either way.


@dataclass(frozen=True)
class _FakeConfirmedEntry:
    entry_index: int
    entry_price: float
    stop_price: float
    absorption_index: int
    direction: str


def _fake_signals(participation=True, confirm=True):
    mod = types.ModuleType("src.strategy.s1_signals")

    @dataclass(frozen=True)
    class S1Params:
        min_taker_delta: float = 0.0

    mod.S1Params = S1Params
    mod.ConfirmedEntry = _FakeConfirmedEntry
    # A 100 -> 110 long impulse; discount band edges: enter at 103, dead below 101.
    mod.latest_swing = lambda candles, left=3, right=3: {
        "high": 110.0, "high_index": 6, "low": 100.0, "low_index": 2,
    }
    mod.discount_band = lambda lo, hi, direction: (103.0, 101.0)
    mod.participation_ok = lambda candles, index, params: participation
    mod.confirm_entry = (
        (lambda candles, touch_index, direction, params: _FakeConfirmedEntry(
            entry_index=touch_index + 2, entry_price=103.5, stop_price=100.9,
            absorption_index=touch_index + 1, direction=direction,
        ))
        if confirm
        else (lambda candles, touch_index, direction, params: None)
    )
    return mod


def _series_with_band_touch():
    """20 flat 1m candles around 105 with one dip into the band at index 12."""
    candles = _flat_candles(20)
    candles[12] = _candle(104.0, 104.5, 102.5, 103.8)  # low pierces the 103 edge
    return candles


def test_composition_confirms_on_touch_then_confirmation(monkeypatch):
    monkeypatch.setitem(sys.modules, "src.strategy.s1_signals", _fake_signals())
    s = S1IntradayStrategy()
    entry = s.evaluate(_series_with_band_touch(), _flat_candles(10), "long")
    assert entry is not None
    assert entry.direction == "long"
    assert entry.absorption_index == 13  # scan starts at the band touch (index 12)


def test_composition_returns_none_when_participation_fails(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "src.strategy.s1_signals", _fake_signals(participation=False)
    )
    entry = S1IntradayStrategy().evaluate(
        _series_with_band_touch(), _flat_candles(10), "long"
    )
    assert entry is None


def test_composition_returns_none_without_confirmation(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "src.strategy.s1_signals", _fake_signals(confirm=False)
    )
    entry = S1IntradayStrategy().evaluate(
        _series_with_band_touch(), _flat_candles(10), "long"
    )
    assert entry is None


def test_composition_returns_none_when_price_never_touches_the_band(monkeypatch):
    monkeypatch.setitem(sys.modules, "src.strategy.s1_signals", _fake_signals())
    entry = S1IntradayStrategy().evaluate(
        _flat_candles(20), _flat_candles(10), "long"  # lows stay at 104 > 103
    )
    assert entry is None


def test_composition_respects_invalidation_after_the_touch(monkeypatch):
    """A close beyond the far edge after the touch kills the setup (0.886 rule)."""
    monkeypatch.setitem(sys.modules, "src.strategy.s1_signals", _fake_signals())
    candles = _series_with_band_touch()
    candles[15] = _candle(102.0, 102.5, 100.2, 100.5)  # closes below 101 — dead
    entry = S1IntradayStrategy().evaluate(candles, _flat_candles(10), "long")
    assert entry is None
