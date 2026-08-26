"""The base market feed is held only while somebody is watching.

`btcusdt@depth5@100ms` is ten messages a second. Subscribed at startup — which is what
this used to do — it streams whether or not a browser is open, and the keepalive cron
guarantees the process never sleeps to stop it. That burned a 5GB free-tier bandwidth
allowance in ten days and suspended the Render workspace on 2026-08-10.

These tests pin the demand-driven lifecycle, not the resolution: 100ms is still 100ms
for anyone actually looking at a terminal.
"""
import asyncio

import pytest

from src.data.binance_client import BinanceWebSocketClient


# --- the client half: unsubscribe must survive a reconnect --------------------

@pytest.mark.asyncio
async def test_unsubscribe_drops_the_stream_from_the_resubscribe_set():
    """THE property. A reconnect replays `subscriptions`, so a stream left in that list
    comes straight back after the next socket drop — the feed would silently resurrect
    itself and the bandwidth with it."""
    c = BinanceWebSocketClient()
    c.subscriptions = ["btcusdt@ticker", "btcusdt@depth5@100ms", "btcusdt@kline_1m"]

    await c.unsubscribe(["btcusdt@depth5@100ms"])

    assert "btcusdt@depth5@100ms" not in c.subscriptions
    assert c.subscriptions == ["btcusdt@ticker", "btcusdt@kline_1m"]


@pytest.mark.asyncio
async def test_unsubscribe_keeps_the_callbacks():
    """Callbacks are keyed by stream name, not by subscription epoch. Dropping them
    would make a re-subscribed stream deliver to nobody — a dashboard that reconnects
    after the grace period would render a dead chart with no error."""
    c = BinanceWebSocketClient()
    c.subscriptions = ["btcusdt@ticker"]
    c.callbacks = {"btcusdt@ticker": [lambda _: None]}

    await c.unsubscribe(["btcusdt@ticker"])

    assert c.callbacks["btcusdt@ticker"], "callback was dropped with the subscription"


@pytest.mark.asyncio
async def test_unsubscribing_something_not_subscribed_is_a_no_op():
    c = BinanceWebSocketClient()
    c.subscriptions = ["btcusdt@ticker"]
    await c.unsubscribe(["ethusdt@ticker"])
    assert c.subscriptions == ["btcusdt@ticker"]


@pytest.mark.asyncio
async def test_duplicate_entries_are_all_removed():
    """subscribe_depth appends without a dedup check, unlike subscribe_kline. A single
    list.remove() would leave a copy behind, and one copy is enough to resurrect the
    stream on the next reconnect."""
    c = BinanceWebSocketClient()
    c.subscriptions = ["btcusdt@depth5@100ms", "btcusdt@ticker", "btcusdt@depth5@100ms"]
    await c.unsubscribe(["btcusdt@depth5@100ms"])
    assert c.subscriptions == ["btcusdt@ticker"]


# --- the server half: acquire on first viewer, release after the last ---------

@pytest.fixture
def feed(monkeypatch):
    """The server module with a fake exchange client and no linger delay."""
    from src.api import server as srv

    calls = {"subscribed": [], "unsubscribed": []}

    class FakeClient:
        async def subscribe_ticker(self, symbol, callback):
            calls["subscribed"].append(f"{symbol}@ticker")

        async def subscribe_depth(self, symbol, levels, update_speed, callback):
            calls["subscribed"].append(f"{symbol}@depth{levels}@{update_speed}")

        async def subscribe_kline(self, symbol, intervals, callback):
            calls["subscribed"].extend(f"{symbol}@kline_{i}" for i in intervals)

        async def unsubscribe(self, streams):
            calls["unsubscribed"].extend(streams)

    monkeypatch.setattr(srv, "binance_client", FakeClient())
    monkeypatch.setattr(srv, "MARKET_FEED_LINGER_S", 0)
    monkeypatch.setattr(srv, "_market_feed_on", False)
    monkeypatch.setattr(srv, "_market_feed_release_task", None)
    return srv, calls


@pytest.mark.asyncio
async def test_the_first_viewer_brings_the_feed_up(feed, monkeypatch):
    srv, calls = feed
    await srv.acquire_market_feed()
    assert set(calls["subscribed"]) == set(srv.BASE_MARKET_STREAMS)


@pytest.mark.asyncio
async def test_a_second_viewer_does_not_subscribe_twice(feed):
    """subscribe_depth appends unconditionally, so a duplicate subscribe would leave a
    second copy in the resubscribe set and double the fan-out after a reconnect."""
    srv, calls = feed
    await srv.acquire_market_feed()
    await srv.acquire_market_feed()
    assert len(calls["subscribed"]) == len(srv.BASE_MARKET_STREAMS)


@pytest.mark.asyncio
async def test_the_feed_drops_once_the_last_viewer_leaves(feed, monkeypatch):
    srv, calls = feed
    monkeypatch.setattr(type(srv.manager), "active_connections", property(lambda self: []))

    await srv.acquire_market_feed()
    srv.release_market_feed_when_idle()
    await asyncio.sleep(0.05)          # let the (zero-linger) teardown run

    assert set(calls["unsubscribed"]) == set(srv.BASE_MARKET_STREAMS)


@pytest.mark.asyncio
async def test_the_feed_stays_up_while_a_viewer_remains(feed, monkeypatch):
    """Releasing on ANY disconnect rather than the LAST one would cut the feed out from
    under everyone else the moment one of several dashboards closed."""
    srv, calls = feed
    monkeypatch.setattr(
        type(srv.manager), "active_connections", property(lambda self: ["still-here"])
    )

    await srv.acquire_market_feed()
    srv.release_market_feed_when_idle()
    await asyncio.sleep(0.05)

    assert calls["unsubscribed"] == []


@pytest.mark.asyncio
async def test_a_viewer_arriving_during_the_grace_period_cancels_the_teardown(monkeypatch):
    """The race the linger exists to lose safely: a reload disconnects and reconnects
    within a second. If the pending teardown still fired, the returning dashboard would
    hold a socket to a feed that had just been switched off — no error, just a chart
    that never ticks."""
    from src.api import server as srv

    calls = {"unsubscribed": []}

    class FakeClient:
        async def subscribe_ticker(self, symbol, callback):
            pass

        async def subscribe_depth(self, symbol, levels, update_speed, callback):
            pass

        async def subscribe_kline(self, symbol, intervals, callback):
            pass

        async def unsubscribe(self, streams):
            calls["unsubscribed"].extend(streams)

    monkeypatch.setattr(srv, "binance_client", FakeClient())
    monkeypatch.setattr(srv, "MARKET_FEED_LINGER_S", 5)   # long enough to interrupt
    monkeypatch.setattr(srv, "_market_feed_on", False)
    monkeypatch.setattr(srv, "_market_feed_release_task", None)
    monkeypatch.setattr(type(srv.manager), "active_connections", property(lambda self: []))

    await srv.acquire_market_feed()
    srv.release_market_feed_when_idle()      # last viewer left; teardown pending
    await asyncio.sleep(0.05)
    await srv.acquire_market_feed()          # they came back

    await asyncio.sleep(0.05)
    assert calls["unsubscribed"] == [], "teardown fired despite a viewer returning"


# --- client-requested extra channels: refcounted, no longer add-only ------------

@pytest.fixture
def upstream(monkeypatch):
    """Server module with a fake client, no linger, and clean channel state.

    _ensure_upstream used to be add-only for process lifetime: one depth.<SYM>
    request re-created a permanent ~10 msg/s stream that only a restart could
    stop. These tests pin the refcounted lifecycle.
    """
    from src.api import server as srv

    calls = {"unsubscribed": []}

    class FakeClient:
        async def unsubscribe(self, streams):
            calls["unsubscribed"].extend(streams)

    monkeypatch.setattr(srv, "binance_client", FakeClient())
    monkeypatch.setattr(srv, "MARKET_FEED_LINGER_S", 0)
    monkeypatch.setattr(srv, "_upstream_channels", set())
    monkeypatch.setattr(srv, "_upstream_release_pending", set())
    monkeypatch.setattr(srv, "_upstream_release_task", None)
    monkeypatch.setattr(srv.manager, "channel_subs", {})
    return srv, calls


@pytest.mark.asyncio
async def test_unwatched_extra_channel_is_released_upstream(upstream):
    """The last watcher leaves -> the upstream stream must actually stop, or the
    bandwidth of a single curious click runs until the next deploy."""
    srv, calls = upstream
    srv._upstream_channels.add("depth.ETHUSDT")

    srv._schedule_upstream_release({"depth.ETHUSDT"})
    await asyncio.sleep(0.01)  # linger is 0; let the release task run

    assert calls["unsubscribed"] == ["ethusdt@depth5@100ms"]
    assert "depth.ETHUSDT" not in srv._upstream_channels


@pytest.mark.asyncio
async def test_channel_stays_while_another_socket_still_watches(upstream):
    srv, calls = upstream
    srv._upstream_channels.add("kline.5m.ETHUSDT")
    srv.manager.channel_subs["other-socket"] = {"kline.5m.ETHUSDT"}

    srv._schedule_upstream_release({"kline.5m.ETHUSDT"})
    await asyncio.sleep(0.01)

    assert calls["unsubscribed"] == []
    assert "kline.5m.ETHUSDT" in srv._upstream_channels


@pytest.mark.asyncio
async def test_base_channels_are_never_released_by_the_refcount(upstream):
    """The base BTCUSDT feed has its own viewer-gated lifecycle — the channel
    refcount must not fight it."""
    srv, calls = upstream
    srv._upstream_channels.add("ticker.BTCUSDT")

    srv._schedule_upstream_release({"ticker.BTCUSDT"})
    await asyncio.sleep(0.01)

    assert calls["unsubscribed"] == []


def test_channel_to_stream_mapping():
    from src.api import server as srv
    assert srv._channel_stream("ticker.ETHUSDT") == "ethusdt@ticker"
    assert srv._channel_stream("depth.ETHUSDT") == "ethusdt@depth5@100ms"
    assert srv._channel_stream("kline.5m.ETHUSDT") == "ethusdt@kline_5m"
    assert srv._channel_stream("garbage") is None
