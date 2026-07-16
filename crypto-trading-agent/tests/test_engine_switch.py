"""EngineSwitch: on/off + auto-off (TTL) + fail-off semantics.

Uses a tiny in-memory fake of the redis.asyncio surface the switch touches
(set/get/delete/exists/ttl) so the test needs no live Redis.
"""
import pytest

from src.core.engine_switch import EngineSwitch, ENGINE_KEY


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}
        self.fail = False

    async def set(self, key, value, ex=None):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = value
        self.ttls[key] = ex if ex else -1

    async def get(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)

    async def exists(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return 1 if key in self.store else 0

    async def ttl(self, key):
        return self.ttls.get(key, -2)


@pytest.mark.asyncio
async def test_default_is_off():
    sw = EngineSwitch(FakeRedis())
    assert await sw.is_on() is False
    st = await sw.status()
    assert st["enabled"] is False and st["expires_in_seconds"] is None


@pytest.mark.asyncio
async def test_turn_on_timed_sets_ttl():
    r = FakeRedis()
    sw = EngineSwitch(r)
    st = await sw.turn_on(duration_seconds=3600, enabled_by="owner")
    assert st["enabled"] is True
    assert st["expires_in_seconds"] == 3600
    assert st["enabled_by"] == "owner"
    assert r.ttls[ENGINE_KEY] == 3600
    assert await sw.is_on() is True


@pytest.mark.asyncio
async def test_turn_on_always_has_no_expiry():
    sw = EngineSwitch(FakeRedis())
    st = await sw.turn_on(duration_seconds=None)
    assert st["enabled"] is True
    assert st["expires_in_seconds"] is None  # -1 TTL reported as None


@pytest.mark.asyncio
async def test_turn_off():
    sw = EngineSwitch(FakeRedis())
    await sw.turn_on(duration_seconds=3600)
    st = await sw.turn_off()
    assert st["enabled"] is False
    assert await sw.is_on() is False


@pytest.mark.asyncio
async def test_fails_off_when_redis_unavailable():
    r = FakeRedis()
    r.fail = True
    sw = EngineSwitch(r)
    # A broken Redis must never leave the engine "on" (no unattended credit burn).
    assert await sw.is_on() is False
    assert (await sw.status())["enabled"] is False
