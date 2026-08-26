"""Market-data streams are demand-gated (R0.2) — nothing runs for nobody.

The Aug-10 Render suspension was the daemon's DataAgent subscribing
depth20@100ms + markprice@1s + ticker + five kline streams PER SYMBOL at
startup, 24/7, kept alive by our own keepalive cron (~2.2GB/day flowing to
nobody against a 167MB/day budget). Only the LLM analysis was demand-gated —
the streams never were. These tests pin the new lifecycle:

  scan demand  -> full analysis feed (klines all TFs + markprice; NO depth
                  stream, NO ticker)
  positions    -> kline_1m per exposed symbol (paper fills + monitors need
                  prices; nothing else does)
  idle         -> zero streams, and the idle socket must not staleness-churn
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from src.data.binance_client import BinanceWebSocketClient
from src.agents.data_agent import DataCollectionAgent
from src.multi_user_daemon import MultiUserTradingDaemon


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class FakeStateManager:
    """Just enough async surface for the data agent."""

    def __init__(self):
        self.prices = {}
        self.kv = {}

    async def update_price(self, symbol, price):
        self.prices[symbol] = price

    async def set(self, key, value, ttl=None):
        self.kv[key] = value

    async def get(self, key):
        return self.kv.get(key)


def make_agent():
    """A DataCollectionAgent with a real (offline) ws client and a stubbed fetcher.

    The ws client never connects (ws is None), so subscribe/unsubscribe mutate
    local state without touching the network — which is exactly the surface the
    gate logic drives.
    """
    agent = DataCollectionAgent(message_bus=MagicMock(), state_manager=FakeStateManager())
    agent.historical_fetcher = MagicMock()
    backfills = []

    async def record_backfill():
        backfills.append(1)

    agent._fetch_initial_data = record_backfill
    return agent, backfills


# --------------------------------------------------------------------------- #
# the client half
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_resubscribing_the_same_handler_does_not_duplicate_it():
    """Every feed-gate cycle re-calls subscribe_* with the same bound handler.
    An unconditional append accumulated one duplicate per cycle, and every
    duplicate re-delivered every frame — N dashboard reopen cycles meant N
    copies of each message hitting the handlers."""
    c = BinanceWebSocketClient()

    async def handler(_):
        pass

    for _ in range(3):
        await c.subscribe_kline("btcusdt", ["1m"], handler)

    assert c.subscriptions.count("btcusdt@kline_1m") == 1
    assert len(c.callbacks["btcusdt@kline_1m"]) == 1


@pytest.mark.asyncio
async def test_depth_ticker_funding_subscriptions_do_not_duplicate():
    """subscribe_kline deduped its stream list; depth/ticker/funding appended
    blindly, so one gate cycle per stream kind left a duplicate behind — and one
    leftover copy is enough to resurrect the stream on the next reconnect."""
    c = BinanceWebSocketClient()

    async def handler(_):
        pass

    for _ in range(2):
        await c.subscribe_depth("btcusdt", levels=5, update_speed="100ms", callback=handler)
        await c.subscribe_ticker("btcusdt", handler)
        await c.subscribe_funding_rate("btcusdt", handler)

    assert c.subscriptions.count("btcusdt@depth5@100ms") == 1
    assert c.subscriptions.count("btcusdt@ticker") == 1
    assert c.subscriptions.count("btcusdt@markprice@1s") == 1


def test_idle_socket_is_never_reconnected_for_staleness():
    """With zero subscriptions no data frames ever arrive, so a plain staleness
    check declared the healthy idle socket dead every 90s and reconnected it
    forever — ~960 pointless TLS handshakes a day. A socket with no streams has
    nothing to be stale about."""
    c = BinanceWebSocketClient()
    c._last_message_at = 1.0  # ancient — _is_stale() itself is True

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        assert c._is_stale() or True  # not the property under test
        c.subscriptions = []
        assert c._should_reconnect_stale() is False

        c.subscriptions = ["btcusdt@kline_1m"]
        assert c._should_reconnect_stale() is c._is_stale()
    finally:
        asyncio.set_event_loop(None)
        loop.close()


# --------------------------------------------------------------------------- #
# the data-agent half: stream profiles
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_scan_profile_is_klines_plus_markprice_and_never_depth_or_ticker():
    """The analysis feed needs candles and funding. The book is read once per
    cycle (REST snapshot at request time) and price rides on every kline push —
    the depth and ticker streams were pure bandwidth."""
    agent, _ = make_agent()

    await agent.set_stream_profile("scan")

    subs = set(agent.ws_client.subscriptions)
    for symbol in agent.config.trading.symbols:
        b = symbol.replace("/", "").lower()
        for tf in agent.normalized_timeframes:
            assert f"{b}@kline_{tf}" in subs
        assert f"{b}@markprice@1s" in subs
    assert not any("depth" in s for s in subs), "depth must be a REST snapshot, not a stream"
    assert not any(s.endswith("@ticker") for s in subs), "klines already carry the price"


@pytest.mark.asyncio
async def test_reapplying_scan_profile_is_idempotent():
    agent, _ = make_agent()

    await agent.set_stream_profile("scan")
    first = sorted(agent.ws_client.subscriptions)
    await agent.set_stream_profile("scan")

    assert sorted(agent.ws_client.subscriptions) == first
    for handlers in agent.ws_client.callbacks.values():
        assert len(handlers) == 1


@pytest.mark.asyncio
async def test_prices_profile_streams_one_light_kline_per_exposed_symbol():
    """Positions still need prices after the session ends — paper SL/TP fills and
    monitors read state prices, which only flow while a stream is up. One 1m
    kline per held symbol is the whole bill."""
    agent, _ = make_agent()
    a_symbol = agent.config.trading.symbols[0]

    await agent.set_stream_profile("prices", price_symbols=[a_symbol, "NOTATRACKEDSYM"])

    b = a_symbol.replace("/", "").lower()
    assert agent.ws_client.subscriptions == [f"{b}@kline_1m"]


@pytest.mark.asyncio
async def test_idle_profile_unsubscribes_everything():
    agent, _ = make_agent()
    await agent.set_stream_profile("scan")
    assert agent.ws_client.subscriptions

    await agent.set_stream_profile(None)

    assert agent.ws_client.subscriptions == []


@pytest.mark.asyncio
async def test_scan_to_prices_drops_the_analysis_feed_but_keeps_the_price_stream():
    agent, _ = make_agent()
    a_symbol = agent.config.trading.symbols[0]
    await agent.set_stream_profile("scan")

    await agent.set_stream_profile("prices", price_symbols=[a_symbol])

    b = a_symbol.replace("/", "").lower()
    assert agent.ws_client.subscriptions == [f"{b}@kline_1m"]


@pytest.mark.asyncio
async def test_entering_scan_after_a_long_gap_backfills_the_buffers():
    """Buffers stop updating the moment klines unsubscribe. Analysis on a buffer
    with a silent hole is worse than a few cached REST calls, so entering scan
    mode after a quiet spell refills first. Timestamps are rewound, never slept."""
    agent, backfills = make_agent()
    # Rewind past the refill window RELATIVE to the loop clock — an absolute 0.0
    # sentinel only means "ages ago" on machines with large uptime (CI containers
    # boot with a seconds-old monotonic clock, which is how this bug was caught).
    loop_now = asyncio.get_event_loop().time()
    agent._scan_streams_until = loop_now - (agent.SCAN_GAP_REFILL_S + 1)

    await agent.set_stream_profile("scan")
    assert len(backfills) == 1

    # Leaving and re-entering within the refill window must NOT refetch:
    await agent.set_stream_profile(None)
    agent._scan_streams_until = asyncio.get_event_loop().time()  # rewind: "just left"
    await agent.set_stream_profile("scan")
    assert len(backfills) == 1


@pytest.mark.asyncio
async def test_price_kline_updates_price_and_never_touches_buffers():
    """1m is deliberately not an analysis timeframe — buffers/locks are keyed by
    the configured timeframes, so a buffer write for 1m would KeyError. The
    light handler's one job is state prices."""
    agent, _ = make_agent()
    symbol = agent.config.trading.symbols[0]
    b = symbol.replace("/", "").upper()

    await agent._on_price_kline({
        "e": "kline", "s": b,
        "k": {"i": "1m", "t": 1700000000000, "o": "100", "h": "101",
              "l": "99", "c": "100.5", "v": "12", "x": False, "s": b},
    })

    assert agent.state_manager.prices.get(symbol) == pytest.approx(100.5)
    assert "1m" not in agent.candle_buffers.get(symbol, {})


@pytest.mark.asyncio
async def test_depth_snapshot_stores_stream_shape_and_respects_ttl():
    """The REST snapshot must be a drop-in for what the depth stream stored, and
    back-to-back analysis requests must not hammer the endpoint."""
    agent, _ = make_agent()
    symbol = agent.config.trading.symbols[0]
    calls = []

    async def fake_book(sym, limit=20):
        calls.append(sym)
        return {"bids": [[100.0, 1.0], [99.9, 2.0]], "asks": [[100.1, 1.5]], "timestamp": 1700000000000}

    agent.historical_fetcher.fetch_order_book = fake_book

    await agent._refresh_depth_snapshot(symbol)
    await agent._refresh_depth_snapshot(symbol)  # within TTL — must not refetch

    assert len(calls) == 1
    book = agent.order_book_data[symbol]
    assert book["best_bid"] == 100.0 and book["best_ask"] == 100.1
    assert book["bids"] and book["asks"] and book["timestamp"] is not None
    assert agent.state_manager.kv[f"order_book:{symbol}"] == book


# --------------------------------------------------------------------------- #
# the daemon half: demand + linger
# --------------------------------------------------------------------------- #

def bare_daemon():
    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d.registry = None
    d.session_manager = None
    return d


class _Engine:
    """Paper engine lookalike: has check_limit_orders, positions, open orders."""

    def __init__(self, positions=None, orders=None):
        self.positions = positions or {}
        self._orders = orders or []

    def check_limit_orders(self):
        pass

    def get_open_orders(self):
        return self._orders


class _Session:
    def __init__(self, engine):
        self.engine = engine


def test_exposure_symbols_sees_positions_and_resting_orders_paper_only():
    d = bare_daemon()
    live_engine = MagicMock(spec=[])  # no check_limit_orders -> live/keyed, excluded
    d.registry = MagicMock()
    d.registry._sessions = {
        "u1": _Session(_Engine(positions={"BTCUSDT": object()})),
        "u2": _Session(_Engine(orders=[{"symbol": "ETHUSDT"}])),
        "u3": _Session(live_engine),
    }

    assert d._exposure_symbols() == ["BTCUSDT", "ETHUSDT"]


@pytest.mark.asyncio
async def test_stream_demand_prefers_scan_then_prices_then_none(monkeypatch):
    d = bare_daemon()
    monkeypatch.delenv("ANALYSIS_KEEP_WARM", raising=False)

    d.session_manager = MagicMock()
    d.session_manager.active_sessions = lambda: ["a-scan"]
    assert (await d._stream_demand())[0] == "scan"

    d.session_manager.active_sessions = lambda: []
    d.registry = MagicMock()
    d.registry._sessions = {"u1": _Session(_Engine(positions={"BTCUSDT": object()}))}
    profile, symbols = await d._stream_demand()
    assert profile == "prices" and symbols == ["BTCUSDT"]

    d.registry._sessions = {}
    assert await d._stream_demand() == (None, None)


def test_gate_decision_upgrades_immediately_and_downgrades_only_after_linger():
    """Demand flaps (a session ends, the next starts a minute later) and Binance
    rate-limits control frames — so upgrades are instant, downgrades wait out a
    linger. Times are passed in, never slept."""
    decide = MultiUserTradingDaemon._gate_decision

    # upgrade: apply now, no linger state
    assert decide(0, 2, None, now=1000.0, linger=120.0) == (True, None)
    # equal tier: apply now
    assert decide(1, 1, None, now=1000.0, linger=120.0) == (True, None)
    # downgrade: first observation arms the linger
    apply_now, since = decide(2, 0, None, now=1000.0, linger=120.0)
    assert apply_now is False and since == 1000.0
    # still inside the linger: hold
    apply_now, since = decide(2, 0, 1000.0, now=1060.0, linger=120.0)
    assert apply_now is False and since == 1000.0
    # linger elapsed: downgrade applies
    assert decide(2, 0, 1000.0, now=1121.0, linger=120.0) == (True, None)
