"""R2.6 — the activity badge tells the truth in all four states.

The founder asked for a "hottest hour" indicator; the honesty law forbids forward
claims. These tests pin the resulting contract: `now` is a live measurement that
degrades to an explicit UNKNOWN (never to "calm"), `hour` is a past-tense measured
rank carrying its own sample, and nothing anywhere returns a forecast.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.signals import hour_profile
from src.signals.pulse_client import GlobalPulse, read_global


def _global_payload(ts_ms, **over):
    payload = {"v": 1, "ts": ts_ms, "symbols_scored": 3, "symbols_vetoed": 1,
               "tradability_max": 71, "tradability_median": 42}
    payload.update(over)
    return json.dumps(payload)


def _redis_returning(value):
    r = AsyncMock()
    r.get.return_value = value
    return r


# --------------------------------------------------------------------------- #
# the global pulse reader
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_reads_a_fresh_global_pulse():
    now = 1_800_000_000_000
    pulse = await read_global(_redis_returning(_global_payload(now - 3_000)))
    assert isinstance(pulse, GlobalPulse)
    assert (pulse.tradability_max, pulse.tradability_median) == (71, 42)
    assert pulse.symbols_vetoed == 1
    assert not pulse.is_stale(now_ms=now)


@pytest.mark.asyncio
async def test_staleness_is_detected_not_smoothed_over():
    now = 1_800_000_000_000
    pulse = await read_global(_redis_returning(_global_payload(now - 120_000)))
    assert pulse.is_stale(now_ms=now)
    assert pulse.age_ms(now_ms=now) == 120_000


@pytest.mark.asyncio
async def test_missing_unparseable_and_wrong_schema_all_return_none():
    assert await read_global(_redis_returning(None)) is None
    assert await read_global(_redis_returning("{not json")) is None
    assert await read_global(_redis_returning(_global_payload(1, v=999))) is None
    broken = AsyncMock()
    broken.get.side_effect = ConnectionError("redis gone")
    assert await read_global(broken) is None  # never raises into a status endpoint


# --------------------------------------------------------------------------- #
# the measured hour profile
# --------------------------------------------------------------------------- #

def test_hour_profile_artifact_is_shipped_and_sane():
    profile = hour_profile.load_profile()
    assert profile is not None, "hour_profile.json must ship with the package"
    assert len(profile["hours_utc"]) == 24
    ranks = sorted(int(v["rank"]) for v in profile["hours_utc"].values())
    assert ranks == list(range(1, 25))          # a real permutation, no ties/gaps
    assert len(profile["top6_hours_utc"]) == 6
    assert profile["total_1m_bars"] > 1_000_000  # enough sample to make a claim
    assert "not a forecast" in profile["caveat"]


def test_describe_hour_is_past_tense_with_provenance():
    at_peak = datetime(2026, 8, 25, 14, 30, tzinfo=timezone.utc)
    out = hour_profile.describe_hour(at_peak)
    assert out["hour_utc"] == 14
    assert out["of"] == 24 and 1 <= out["rank"] <= 24
    assert out["in_top_window"] is True          # 14:00 UTC measured most active
    assert out["sample"]["bars"] > 1_000_000
    assert out["sample"]["symbols"] and out["sample"]["from_ms"] < out["sample"]["to_ms"]
    # No forward-looking field may exist — that is the whole constraint.
    assert not any(k in out for k in ("forecast", "next_hour", "prediction", "expected"))


def test_a_quiet_hour_is_reported_as_quiet():
    at_trough = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
    out = hour_profile.describe_hour(at_trough)
    assert out["in_top_window"] is False
    assert out["rank"] > 12


def test_missing_profile_yields_none_not_a_guess(monkeypatch):
    monkeypatch.setattr(hour_profile, "_cache", None)
    monkeypatch.setattr(hour_profile, "_load_failed", False)
    monkeypatch.setattr(hour_profile, "PROFILE_PATH", "/nonexistent/hour_profile.json")
    assert hour_profile.load_profile() is None
    assert hour_profile.describe_hour() is None


# --------------------------------------------------------------------------- #
# the endpoint
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_endpoint_reports_live_conditions(monkeypatch):
    from src.api import server as srv
    import time

    sm = MagicMock()
    sm.redis = _redis_returning(_global_payload(int(time.time() * 1000) - 2_000))
    monkeypatch.setattr(srv, "state_manager", sm)

    body = await srv.get_pulse()
    assert body["now"]["available"] is True
    assert body["now"]["tradability_max"] == 71
    assert body["hour"]["of"] == 24


@pytest.mark.asyncio
async def test_endpoint_says_unknown_not_calm_when_the_plane_is_down(monkeypatch):
    """The failure that must never look like good news: a dead engine reading as a
    quiet market. Each cause reports a DIFFERENT reason — operators need to tell a
    stale plane from an absent one."""
    from src.api import server as srv
    import time

    monkeypatch.setattr(srv, "state_manager", None)
    assert (await srv.get_pulse())["now"] == {
        "available": False, "reason": "signal_plane_unavailable"}

    sm = MagicMock()
    sm.redis = _redis_returning(None)
    monkeypatch.setattr(srv, "state_manager", sm)
    assert (await srv.get_pulse())["now"]["reason"] == "no_pulse_published"

    sm.redis = _redis_returning(_global_payload(int(time.time() * 1000) - 300_000))
    body = await srv.get_pulse()
    assert body["now"]["available"] is False
    assert body["now"]["reason"] == "pulse_stale"
    assert body["now"]["age_ms"] > 60_000
    # ...and the measured hour profile still works: it needs no live plane at all.
    assert body["hour"]["of"] == 24
