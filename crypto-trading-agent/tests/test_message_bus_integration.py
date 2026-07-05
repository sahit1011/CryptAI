"""MessageBus integration tests (require a local Redis on :6379).

Covers the resilience/correctness fixes:
- multiple callbacks per channel (no silent overwrite)
- selective unsubscribe (removing one waiter keeps the others)
- disconnect() nulls the handles (so the listen loop can reconnect)
"""
import asyncio
import os

import pytest

from src.core.message_bus import MessageBus

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def _redis_up() -> bool:
    bus = MessageBus(redis_url=REDIS_URL)
    try:
        await bus.connect()
        await bus.disconnect()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_multiple_callbacks_and_selective_unsubscribe():
    if not await _redis_up():
        pytest.skip("no local Redis")

    bus = MessageBus(redis_url=REDIS_URL)
    await bus.connect()

    got_a, got_b = [], []

    async def cb_a(msg):
        got_a.append(msg)

    async def cb_b(msg):
        got_b.append(msg)

    await bus.subscribe("test_chan", cb_a)
    await bus.subscribe("test_chan", cb_b)
    assert len(bus.subscribers["test_chan"]) == 2  # both retained, no overwrite

    await asyncio.sleep(0.2)  # let the listen loop attach
    await bus.publish("test_chan", {"type": "ping", "n": 1}, persist=False)
    await asyncio.sleep(0.3)
    assert len(got_a) == 1 and len(got_b) == 1

    # Remove only cb_a; cb_b must keep receiving.
    await bus.unsubscribe("test_chan", cb_a)
    assert bus.subscribers["test_chan"] == [cb_b]
    await bus.publish("test_chan", {"type": "ping", "n": 2}, persist=False)
    await asyncio.sleep(0.3)
    assert len(got_a) == 1  # unchanged
    assert len(got_b) == 2  # still receiving

    bus.running = False
    await bus.disconnect()


@pytest.mark.asyncio
async def test_disconnect_nulls_handles():
    if not await _redis_up():
        pytest.skip("no local Redis")
    bus = MessageBus(redis_url=REDIS_URL)
    await bus.connect()
    assert bus.redis_client is not None
    await bus.disconnect()
    assert bus.redis_client is None
    assert bus.pubsub is None
    # idempotent: a second disconnect must not raise
    await bus.disconnect()
