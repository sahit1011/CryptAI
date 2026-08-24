

"""
Binance WebSocket client for real-time market data
Enhanced with proper callback routing and ticker support

Reconnect strategy (single, supervisor-based):
    A single long-lived "supervisor" task owns the connect -> receive ->
    reconnect lifecycle. It guarantees that exactly ONE message loop is ever
    running at a time, uses jittered exponential backoff between reconnect
    attempts, gives up (and alerts) after a bounded number of failures, and
    treats a socket that has gone silent for too long as dead even if it is
    still nominally "open" (stale-price / money-loss protection).

    The previous implementation layered a Tenacity ``@retry`` decorator on top
    of a manual counter/sleep AND spawned a fresh ``_message_loop`` task on
    every (re)connect. That could leave multiple overlapping message loops
    alive, with stale-but-open sockets feeding stale prices. That dual scheme
    has been removed in favour of this single supervisor.
"""
import asyncio
import json
import os
import random
from datetime import datetime, timezone
from typing import Dict, Any, List, Callable, Optional
from websockets import connect, WebSocketClientProtocol
from loguru import logger


class BinanceWebSocketClient:
    """
    Real-time WebSocket client for Binance Futures
    """

    # Ordered WS endpoints. Futures first (the trading venue); the spot host and
    # the data-mirror serve the SAME market-data streams (ticker/kline/depth) and
    # exist because some networks (corporate MDM filters, regional blocks) let
    # fstream complete a TLS handshake but never deliver a frame — the client
    # then staleness-reconnects into the same dead host forever. Reconnects
    # rotate through this list so live data finds a path. BINANCE_WS_URL (env)
    # is tried first when set.
    WS_URLS = [
        "wss://fstream.binance.com/ws",
        "wss://stream.binance.com:9443/ws",
        "wss://data-stream.binance.vision/ws",
    ]
    # Back-compat alias (external references / logs).
    BASE_URL = WS_URLS[0]
    # Give a blocked host only this long to open before rotating on.
    OPEN_TIMEOUT = 10.0

    # --- Reconnect / liveness tuning -------------------------------------
    # recv() timeout: how long we wait for any frame before sending a keepalive
    # ping. A timeout here is NORMAL on quiet streams and is not, by itself,
    # treated as a dead socket.
    RECV_TIMEOUT = 30.0
    # Staleness timeout: if NO market message has been received within this many
    # seconds the socket is considered dead (stale prices) and we force a
    # reconnect even if the socket still looks open. Must be > RECV_TIMEOUT so a
    # single quiet interval doesn't trip it.
    STALENESS_TIMEOUT = 90.0
    # Backoff bounds (seconds) for jittered exponential backoff.
    BACKOFF_BASE = 1.0
    BACKOFF_MAX = 60.0

    def __init__(
        self,
        on_reconnect_callback: Optional[Callable] = None,
        on_giveup_callback: Optional[Callable] = None,
    ):
        self.ws: Optional[WebSocketClientProtocol] = None
        self.subscriptions: List[str] = []
        self.callbacks: Dict[str, List[Callable]] = {}
        self.running = False
        self.max_reconnect_attempts = 10
        self.on_reconnect_callback = on_reconnect_callback
        # Optional alert hook invoked when we permanently give up reconnecting.
        self.on_giveup_callback = on_giveup_callback

        # --- Lifecycle / single-loop guarantee ---------------------------
        # The supervisor task is the ONLY thing that drives connect/receive/
        # reconnect. Keeping a handle lets connect() be idempotent (it never
        # spawns a second supervisor / message loop).
        self._supervisor_task: Optional[asyncio.Task] = None
        # Timestamp (event-loop clock) of the last market message received.
        # Used for per-socket staleness detection.
        self._last_message_at: float = 0.0
        # Host rotation: BINANCE_WS_URL (env) first when set, then WS_URLS.
        # _url_index advances on every reconnect so a silently-dead host is
        # abandoned instead of retried forever.
        env_url = os.getenv("BINANCE_WS_URL", "").strip()
        self._urls: List[str] = ([env_url] if env_url else []) + list(self.WS_URLS)
        self._url_index = 0

    async def connect(self):
        """
        Start the WebSocket client.

        Idempotent: starts the single supervisor task that owns the full
        connect/receive/reconnect lifecycle. The actual socket is opened inside
        the supervisor. This method returns once the supervisor is running (and,
        on first start, once the initial connection has been established) so the
        existing call sites that ``await connect()`` then subscribe keep working.
        """
        if self._supervisor_task and not self._supervisor_task.done():
            logger.debug("connect() called but supervisor already running; ignoring")
            return

        self.running = True
        # Open the initial connection synchronously so callers can subscribe
        # immediately after connect() returns (preserves prior behaviour where
        # self.ws was set before connect() returned).
        await self._open_connection()
        # Spawn the single supervisor that runs the message loop and handles all
        # future reconnects. No other code path creates a message loop task.
        self._supervisor_task = asyncio.create_task(self._supervisor())

    async def _open_connection(self):
        """Open (or re-open) the underlying socket and resubscribe streams."""
        url = self._urls[self._url_index % len(self._urls)]
        self.ws = await asyncio.wait_for(connect(url), timeout=self.OPEN_TIMEOUT)
        self._mark_message_received()  # treat a fresh connect as "live"
        logger.info(f"✅ Connected to Binance WebSocket ({url.split('/')[2]})")

        # Resubscribe to streams on (re)connect.
        if self.subscriptions:
            await self._resubscribe()

    async def disconnect(self):
        """Close WebSocket connection and stop the supervisor."""
        self.running = False

        # Cancel the supervisor first so it cannot spawn a new connection/loop
        # while we are tearing down.
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:  # defensive: never let teardown raise
                logger.warning(f"Supervisor task ended with error during disconnect: {e}")
        self._supervisor_task = None

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self.ws = None
        logger.info("Disconnected from Binance WebSocket")

    async def subscribe_kline(
        self,
        symbol: str,
        intervals: List[str],
        callback: Callable
    ):
        """
        Subscribe to kline (candlestick) streams

        Args:
            symbol: Trading pair (e.g., 'btcusdt')
            intervals: List of intervals ['5m', '15m', '1h', '4h', '1d']
            callback: Function to call with kline data
        """
        symbol = symbol.lower()

        new_streams = []
        for interval in intervals:
            stream = f"{symbol}@kline_{interval}"

            # Only add if not already subscribed
            if stream not in self.subscriptions:
                self.subscriptions.append(stream)
                new_streams.append(stream)

            self._register_callback(stream, callback)

            logger.info(f"Subscribed to {stream}")

        # Only send subscription for NEW streams
        if self.ws and new_streams:
            await self._subscribe(new_streams)

    async def subscribe_depth(
        self,
        symbol: str,
        levels: int = 20,
        update_speed: str = "100ms",
        callback: Callable = None
    ):
        """
        Subscribe to order book depth stream

        Args:
            symbol: Trading pair
            levels: Depth levels (5, 10, 20)
            update_speed: '100ms' or '500ms'
            callback: Function to call with depth data
        """
        symbol = symbol.lower()
        stream = f"{symbol}@depth{levels}@{update_speed}"

        is_new = stream not in self.subscriptions
        if is_new:
            self.subscriptions.append(stream)
        if callback:
            self._register_callback(stream, callback)

        if self.ws and is_new:
            await self._subscribe([stream])

        logger.info(f"Subscribed to {stream}")

    async def subscribe_funding_rate(self, symbol: str, callback: Callable):
        """Subscribe to mark price updates (includes funding rate info)"""
        symbol = symbol.lower()
        # Use markPrice stream which includes funding rate information
        stream = f"{symbol}@markprice@1s"

        is_new = stream not in self.subscriptions
        if is_new:
            self.subscriptions.append(stream)
        self._register_callback(stream, callback)

        if self.ws and is_new:
            await self._subscribe([stream])

        logger.info(f"Subscribed to mark price (funding rate): {stream}")

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """Subscribe to 24hr ticker updates for live price"""
        symbol = symbol.lower()
        stream = f"{symbol}@ticker"

        is_new = stream not in self.subscriptions
        if is_new:
            self.subscriptions.append(stream)
        self._register_callback(stream, callback)

        if self.ws and is_new:
            await self._subscribe([stream])

        logger.info(f"Subscribed to ticker (live price): {stream}")

    def _register_callback(self, stream: str, callback: Callable) -> None:
        """Attach a callback to a stream exactly once.

        subscribe/unsubscribe cycles re-call the subscribe_* methods with the same
        handler (the feed gate re-acquires the base streams every time a dashboard
        returns; the data agent re-applies its stream profile every demand change).
        An unconditional append accumulated one duplicate per cycle, and every
        duplicate re-delivered every frame — N reopen cycles meant N copies of each
        message hitting the handlers. Equality (not identity) so bound methods and
        module-level functions both dedupe; fresh lambdas never will — callers must
        pass stable handlers.
        """
        handlers = self.callbacks.setdefault(stream, [])
        if callback not in handlers:
            handlers.append(callback)

    async def _subscribe(self, streams: List[str]):
        """Send subscription message"""
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(datetime.now(timezone.utc).timestamp())
        }

        await self.ws.send(json.dumps(subscribe_message))
        logger.info(f"Sent subscription request for {len(streams)} streams")

    async def unsubscribe(self, streams: List[str]):
        """Stop streams at the exchange and drop them from the resubscribe set.

        Removing them from `self.subscriptions` is the half that actually matters: a
        reconnect replays that list, so a stream left in it comes straight back after
        the next socket drop even though nothing asked for it.

        Callbacks are deliberately kept. The map is keyed by stream name, so a stream
        that is re-subscribed later (a dashboard reopening) resumes delivering to the
        same handlers rather than going silently nowhere.
        """
        doomed = {s for s in streams if s in self.subscriptions}
        if not doomed:
            return

        self.subscriptions = [s for s in self.subscriptions if s not in doomed]

        if self.ws:
            unsubscribe_message = {
                "method": "UNSUBSCRIBE",
                "params": sorted(doomed),
                "id": int(datetime.now(timezone.utc).timestamp())
            }
            await self.ws.send(json.dumps(unsubscribe_message))

        logger.info(f"Unsubscribed from {len(doomed)} streams: {', '.join(sorted(doomed))}")

    async def _resubscribe(self):
        """Resubscribe to all streams after reconnection"""
        if self.subscriptions:
            await self._subscribe(self.subscriptions)
            logger.info(f"Resubscribed to {len(self.subscriptions)} streams")

    # ------------------------------------------------------------------ #
    # Single supervisor: owns connect/receive/reconnect lifecycle.
    # ------------------------------------------------------------------ #
    async def _supervisor(self):
        """
        The one and only driver of the connection lifecycle.

        Runs the message loop; when it returns (socket closed/error/stale), it
        reconnects with jittered exponential backoff. Guarantees exactly one
        message loop is active at a time because there is exactly one supervisor
        task and the message loop runs inline within it (never as a separate
        spawned task).
        """
        attempt = 0
        while self.running:
            try:
                # Ensure we have a live socket. On the very first iteration the
                # socket was already opened by connect(); afterwards we open it
                # here as part of each reconnect.
                if self.ws is None:
                    await self._open_connection()

                # Successfully (re)connected -> reset backoff and notify.
                if attempt > 0:
                    logger.info("✅ WebSocket reconnected successfully")
                    await self._notify_reconnect()
                attempt = 0

                # Run the message loop INLINE (not as a separate task) so only
                # one loop can ever be active. It returns when the socket needs
                # to be reconnected.
                await self._message_loop()

            except asyncio.CancelledError:
                # disconnect() cancelled us; propagate so the task ends cleanly.
                raise
            except Exception as e:
                logger.error(f"Supervisor connection error: {e}")

            if not self.running:
                break

            # The current socket is unusable; close it before backing off so we
            # never leave a stale-but-open socket lingering.
            await self._close_socket()

            # Rotate to the next WS host: a host that handshakes but never
            # delivers a frame (MDM filter / regional block) would otherwise be
            # staleness-reconnected forever. All hosts serve the same streams.
            self._url_index += 1

            attempt += 1
            if attempt > self.max_reconnect_attempts:
                logger.critical(
                    f"Max reconnection attempts ({self.max_reconnect_attempts}) "
                    f"reached. Giving up on Binance WebSocket."
                )
                self.running = False
                await self._notify_giveup()
                break

            delay = self._backoff_delay(attempt)
            logger.warning(
                f"Reconnecting... attempt {attempt}/{self.max_reconnect_attempts} "
                f"in {delay:.1f}s"
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

    def _backoff_delay(self, attempt: int) -> float:
        """Jittered exponential backoff capped at BACKOFF_MAX seconds."""
        base = min(self.BACKOFF_BASE * (2 ** (attempt - 1)), self.BACKOFF_MAX)
        # Full jitter: pick uniformly in [0, base] to avoid thundering-herd /
        # synchronized reconnect storms.
        return random.uniform(0.0, base)

    def _mark_message_received(self):
        """Record that the socket is alive right now (for staleness checks)."""
        self._last_message_at = asyncio.get_event_loop().time()

    def _is_stale(self) -> bool:
        """True if no message has arrived within STALENESS_TIMEOUT seconds."""
        if self._last_message_at <= 0:
            return False
        return (asyncio.get_event_loop().time() - self._last_message_at) > self.STALENESS_TIMEOUT

    def _should_reconnect_stale(self) -> bool:
        """Staleness only means 'dead socket' when something SHOULD be flowing.

        With zero subscriptions no data frames ever arrive, so a plain staleness
        check declared the healthy idle socket dead every 90s and reconnected it
        forever (~960 pointless TLS handshakes/day once the feed gate made idle
        backends subscribe nothing). A socket with no streams has nothing to be
        stale about — keepalive pings are enough.
        """
        return bool(self.subscriptions) and self._is_stale()

    async def _close_socket(self):
        """Close the current socket (best-effort) and clear the handle."""
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing stale WebSocket: {e}")
            self.ws = None

    async def _notify_reconnect(self):
        """Invoke the reconnect callback (best-effort)."""
        if self.on_reconnect_callback:
            try:
                await self.on_reconnect_callback()
            except Exception as e:
                logger.error(f"Error in reconnect callback: {e}")

    async def _notify_giveup(self):
        """Invoke the give-up/alert callback (best-effort)."""
        if self.on_giveup_callback:
            try:
                await self.on_giveup_callback()
            except Exception as e:
                logger.error(f"Error in give-up callback: {e}")

    async def _message_loop(self):
        """
        Main message receiving loop.

        Returns (does NOT recurse / reconnect itself) when the socket needs to
        be re-established; the supervisor handles the actual reconnect. This
        keeps reconnection logic in exactly one place.
        """
        while self.running:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=self.RECV_TIMEOUT)
                self._mark_message_received()

                data = json.loads(message)

                # Handle different message types
                if 'e' in data:  # Event type present
                    await self._handle_event(data)
                elif 'result' in data or 'id' in data:
                    # Subscription confirmation
                    logger.debug(f"Subscription response: {data}")

            except asyncio.TimeoutError:
                # No frame within RECV_TIMEOUT. This is normal on quiet streams:
                # send a keepalive ping. But if the socket has been silent past
                # STALENESS_TIMEOUT while streams are subscribed, treat it as dead
                # (stale prices) and let the supervisor reconnect.
                if self._should_reconnect_stale():
                    logger.error(
                        f"WebSocket stale: no messages for >{self.STALENESS_TIMEOUT}s. "
                        f"Treating socket as dead and reconnecting."
                    )
                    return
                await self._send_ping()
            except asyncio.CancelledError:
                # disconnect() cancelled the supervisor; bubble up to end cleanly.
                raise
            except Exception as e:
                # Socket-level error (closed/protocol). Return so the supervisor
                # reconnects; do NOT reconnect from here (single source of truth).
                logger.error(f"Error in message loop: {e}")
                return

    async def _handle_event(self, data: Dict[str, Any]):
        """Handle incoming event with proper routing"""
        event_type = data.get('e')
        stream_symbol = data.get('s', '').lower()

        logger.debug(f"Received event: {event_type} for {stream_symbol}")

        # Route events to appropriate callbacks based on event type
        matching_callbacks = []

        if event_type == 'kline':
            # Kline event: btcusdt@kline_5m
            interval = data.get('k', {}).get('i', '')
            stream_id = f"{stream_symbol}@kline_{interval}"
            if stream_id in self.callbacks:
                matching_callbacks.extend(self.callbacks[stream_id])
                logger.debug(f"Routing kline to {len(self.callbacks[stream_id])} callbacks")

        elif event_type == 'depthUpdate':
            # Depth update: btcusdt@depth20@100ms
            # Match any depth stream for this symbol
            for stream_key in self.callbacks.keys():
                if stream_symbol in stream_key and 'depth' in stream_key:
                    matching_callbacks.extend(self.callbacks[stream_key])
                    logger.debug(f"Routing depth to {len(self.callbacks[stream_key])} callbacks")
                    break

        elif event_type == 'markPriceUpdate':
            # Mark price update: btcusdt@markprice@1s
            stream_id = f"{stream_symbol}@markprice@1s"
            if stream_id in self.callbacks:
                matching_callbacks.extend(self.callbacks[stream_id])
                logger.debug(f"Routing mark price to {len(self.callbacks[stream_id])} callbacks")

        elif event_type == '24hrTicker':
            # 24hr ticker update: btcusdt@ticker
            stream_id = f"{stream_symbol}@ticker"
            if stream_id in self.callbacks:
                matching_callbacks.extend(self.callbacks[stream_id])
                logger.debug(f"Routing ticker to {len(self.callbacks[stream_id])} callbacks")

        # Call all matching callbacks
        if matching_callbacks:
            for callback in matching_callbacks:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        else:
            logger.warning(f"No callbacks found for event: {event_type}, symbol: {stream_symbol}")

    async def _send_ping(self):
        """Send ping to keep connection alive"""
        try:
            await self.ws.ping()
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
