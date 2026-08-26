"""Redis eviction hardening (R1.7): a 25MB allkeys-lru store may drop ANY key.

Three defenses under test:
1. Bus queues are bounded — candle payloads must not fill the LRU and make
   eviction of critical keys (engine:on, cmd_reply:*) the expected state.
2. The switch guard heals an EVICTED always-on engine switch — while never
   resurrecting a deliberate owner-OFF (tombstone), never re-asserting a timed
   switch (expiry is the feature), and never acting on a fresh process's empty
   memory (restart still fails OFF, the switch module's designed money-safety).
3. turn_off leaves the tombstone that makes owner-OFF distinguishable from
   eviction at all.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.engine_switch import ENGINE_KEY, OWNER_OFF_KEY, EngineSwitch
from src.core.message_bus import MessageBus
from src.multi_user_daemon import MultiUserTradingDaemon


# --------------------------------------------------------------------------- #
# 1. bounded bus queues
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_persisted_bus_messages_keep_the_queue_bounded():
    bus = MessageBus.__new__(MessageBus)
    bus.redis_client = AsyncMock()

    await bus.publish("analysis_agent_inbox", {"type": "market_data_update", "payload": {}})

    bus.redis_client.lpush.assert_awaited_once()
    bus.redis_client.ltrim.assert_awaited_once_with("queue:analysis_agent_inbox", 0, 49)
    bus.redis_client.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_realtime_only_messages_touch_no_queue():
    bus = MessageBus.__new__(MessageBus)
    bus.redis_client = AsyncMock()

    await bus.publish("agent_activity", {"type": "heartbeat"}, persist=False)

    bus.redis_client.lpush.assert_not_awaited()
    bus.redis_client.ltrim.assert_not_awaited()


# --------------------------------------------------------------------------- #
# 2. the switch guard
# --------------------------------------------------------------------------- #

def guard_daemon(switch):
    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d.engine_switch = switch
    d._switch_always_on = False
    d._switch_seen_at = 0.0
    return d


class FakeSwitch:
    def __init__(self):
        self.state = {"enabled": False, "expires_in_seconds": None}
        self.owner_off = False
        self.turned_on = []

    async def status(self):
        return dict(self.state)

    async def owner_turned_off_recently(self):
        return self.owner_off

    async def turn_on(self, *, duration_seconds, enabled_by):
        self.turned_on.append(enabled_by)
        self.state = {"enabled": True, "expires_in_seconds": None}


@pytest.mark.asyncio
async def test_evicted_always_on_switch_is_reasserted():
    """The one case the guard exists for: seen ON-with-no-timer, then the key
    vanishes with no owner tombstone — that is an eviction, heal it."""
    sw = FakeSwitch()
    d = guard_daemon(sw)

    sw.state = {"enabled": True, "expires_in_seconds": None}
    assert await d._switch_guard_once(now=1000.0) is False  # observe ON

    sw.state = {"enabled": False, "expires_in_seconds": None}  # evicted
    assert await d._switch_guard_once(now=1030.0) is True
    assert sw.turned_on == ["switch-guard(re-assert)"]


@pytest.mark.asyncio
async def test_owner_off_is_never_resurrected():
    sw = FakeSwitch()
    d = guard_daemon(sw)
    sw.state = {"enabled": True, "expires_in_seconds": None}
    await d._switch_guard_once(now=1000.0)

    sw.state = {"enabled": False, "expires_in_seconds": None}
    sw.owner_off = True  # turn_off tombstone present
    assert await d._switch_guard_once(now=1030.0) is False
    assert sw.turned_on == []
    # and the memory is dropped, so a later tombstone expiry can't resurrect either
    sw.owner_off = False
    assert await d._switch_guard_once(now=1060.0) is False


@pytest.mark.asyncio
async def test_timed_switch_expiry_is_the_feature_not_a_failure():
    sw = FakeSwitch()
    d = guard_daemon(sw)
    sw.state = {"enabled": True, "expires_in_seconds": 1800}  # auto-off timer set
    await d._switch_guard_once(now=1000.0)

    sw.state = {"enabled": False, "expires_in_seconds": None}  # expired
    assert await d._switch_guard_once(now=1030.0) is False
    assert sw.turned_on == []


@pytest.mark.asyncio
async def test_fresh_process_memory_never_reasserts():
    """A restart loses the guard's memory BY DESIGN — matching the switch module's
    own rule that lost state fails OFF, never into credit burn."""
    sw = FakeSwitch()
    d = guard_daemon(sw)
    sw.state = {"enabled": False, "expires_in_seconds": None}
    assert await d._switch_guard_once(now=1000.0) is False
    assert sw.turned_on == []


@pytest.mark.asyncio
async def test_stale_memory_lapses():
    """Timestamps are rewound, never slept: an observation older than the memory
    window is no longer actionable."""
    sw = FakeSwitch()
    d = guard_daemon(sw)
    sw.state = {"enabled": True, "expires_in_seconds": None}
    await d._switch_guard_once(now=1000.0)

    sw.state = {"enabled": False, "expires_in_seconds": None}
    late = 1000.0 + MultiUserTradingDaemon.SWITCH_GUARD_MEMORY_S + 1
    assert await d._switch_guard_once(now=late) is False
    assert sw.turned_on == []


# --------------------------------------------------------------------------- #
# 3. the tombstone itself
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_turn_off_writes_the_tombstone_and_turn_on_clears_it():
    redis = AsyncMock()
    redis.get.return_value = None
    redis.exists.return_value = 0
    redis.ttl.return_value = -2
    sw = EngineSwitch(redis)

    await sw.turn_off(disabled_by="owner")
    redis.delete.assert_any_await(ENGINE_KEY)
    args, kwargs = redis.set.await_args
    assert args[0] == OWNER_OFF_KEY and kwargs.get("ex") == 600

    redis.reset_mock()
    redis.get.return_value = None
    redis.ttl.return_value = -2
    await sw.turn_on(duration_seconds=None)
    redis.delete.assert_any_await(OWNER_OFF_KEY)


@pytest.mark.asyncio
async def test_tombstone_read_error_fails_toward_off():
    """When unsure whether the owner turned it off, the guard must NOT resurrect —
    staying off is the safe direction for money and credits alike."""
    redis = AsyncMock()
    redis.exists.side_effect = ConnectionError("redis gone")
    sw = EngineSwitch(redis)
    assert await sw.owner_turned_off_recently() is True
