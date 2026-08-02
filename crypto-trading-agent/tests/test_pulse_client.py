"""PulseClient enforces the shared-plane boundary contract.

These test the invariants from docs/MULTI_TENANCY.md that the client is responsible for,
so no caller has to remember them. Fully mocked — no Redis needed.
"""
import json
from unittest.mock import AsyncMock

import pytest

from src.signals import (
    Pulse,
    PulseClient,
    PulseIncompatible,
    PulseMissing,
    PulseStale,
)
from src.signals.pulse_client import SCHEMA_VERSION

NOW = 1_754_092_800_000


def make_pulse(**overrides) -> dict:
    base = {
        "v": SCHEMA_VERSION,
        "symbol": "BTCUSDT",
        "ts": NOW,
        "feed_ts": NOW - 500,
        "regime": "trending_up",
        "tradability": 72,
        "vetoes": [],
        "factors": {"trend_alignment": 0.8, "efficiency_ratio": 0.6},
        "structure": {},
        "context": {"atr_pct": 1.3},
        "reference_price": 67_000.0,
    }
    base.update(overrides)
    return base


def client_returning(payload) -> PulseClient:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=json.dumps(payload) if isinstance(payload, dict) else payload
    )
    return PulseClient(redis, max_age_ms=15_000)


@pytest.mark.asyncio
async def test_reads_a_fresh_pulse():
    pulse = await client_returning(make_pulse()).get("BTCUSDT", now_ms=NOW)
    assert pulse.symbol == "BTCUSDT"
    assert pulse.tradability == 72
    assert pulse.is_tradable


@pytest.mark.asyncio
async def test_stale_data_raises_rather_than_returning():
    """Invariant 2: fail-closed staleness.

    The shared plane is a single point of failure for every tenant. A caller that
    receives stale facts cannot tell them from fresh ones, so the refusal has to happen
    here.
    """
    stale = make_pulse(feed_ts=NOW - 60_000)
    with pytest.raises(PulseStale, match="refusing to act on stale"):
        await client_returning(stale).get("BTCUSDT", now_ms=NOW)


@pytest.mark.asyncio
async def test_staleness_is_measured_from_feed_ts_not_computation_ts():
    """A pulse recomputed on schedule from a dead feed has a fresh `ts` and stale facts.
    Anchoring to `ts` would call that healthy."""
    fresh_ts_stale_feed = make_pulse(ts=NOW, feed_ts=NOW - 90_000)
    with pytest.raises(PulseStale):
        await client_returning(fresh_ts_stale_feed).get("BTCUSDT", now_ms=NOW)


@pytest.mark.asyncio
async def test_unknown_schema_version_is_rejected_not_parsed():
    future = make_pulse(v=SCHEMA_VERSION + 1)
    with pytest.raises(PulseIncompatible, match="schema"):
        await client_returning(future).get("BTCUSDT", now_ms=NOW)


@pytest.mark.asyncio
async def test_missing_and_malformed_are_distinguished():
    with pytest.raises(PulseMissing):
        await client_returning(None).get("BTCUSDT", now_ms=NOW)
    with pytest.raises(PulseIncompatible):
        await client_returning("{not json").get("BTCUSDT", now_ms=NOW)


@pytest.mark.asyncio
async def test_redis_outage_surfaces_as_unavailable_not_a_crash():
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=ConnectionError("Error 61"))
    with pytest.raises(PulseMissing, match="redis read failed"):
        await PulseClient(redis).get("BTCUSDT", now_ms=NOW)


@pytest.mark.asyncio
async def test_get_or_none_swallows_only_expected_failures():
    assert await client_returning(None).get_or_none("BTCUSDT", now_ms=NOW) is None
    stale = make_pulse(feed_ts=NOW - 60_000)
    assert await client_returning(stale).get_or_none("BTCUSDT", now_ms=NOW) is None


@pytest.mark.asyncio
async def test_one_dead_symbol_does_not_blind_the_others():
    """Partial results are correct: a session must still see the symbols that are fine."""
    redis = AsyncMock()

    async def get(key):
        if key.endswith("ETHUSDT"):
            return None
        return json.dumps(make_pulse(symbol=key.rsplit(":", 1)[-1]))

    redis.get = AsyncMock(side_effect=get)
    got = await PulseClient(redis).get_many(["BTCUSDT", "ETHUSDT", "SOLUSDT"], now_ms=NOW)
    assert set(got) == {"BTCUSDT", "SOLUSDT"}


def test_a_veto_means_not_tradable():
    pulse = Pulse.from_dict(make_pulse(vetoes=["spread_too_wide"], tradability=0))
    assert pulse.is_vetoed
    assert not pulse.is_tradable


def test_feed_age_never_negative_on_clock_skew():
    pulse = Pulse.from_dict(make_pulse(feed_ts=NOW + 5_000))
    assert pulse.feed_age_ms(NOW) == 0


def test_the_client_type_carries_no_trade_decision():
    """Mirror of the Rust contract test. If a direction/entry/stop field appears here,
    the shared plane has started emitting trades and every user gets the same one."""
    pulse = Pulse.from_dict(make_pulse())
    for forbidden in ("entry", "entry_price", "stop_loss", "take_profit", "direction", "side"):
        assert not hasattr(pulse, forbidden), (
            f"Pulse gained `{forbidden}` — the shared plane must not emit trade decisions"
        )


def test_key_layout_is_not_namespaced_by_user():
    """The shared plane's keys are deliberately un-namespaced; per-user keys are scoped
    by user_id. That asymmetry IS the tenancy boundary, made visible in the key layout."""
    key = PulseClient.key_for("btcusdt")
    assert key == "market:pulse:BTCUSDT"
    assert "user" not in key
