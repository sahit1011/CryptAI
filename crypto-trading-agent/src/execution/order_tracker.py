"""
Order Status Tracker
Real-time order status monitoring via WebSocket and polling
"""
from typing import Dict, List, Callable, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
import asyncio
import json
import gzip
import io
import random
import time

# `websockets` is a declared project dependency (requirements.txt: websockets==12.0).
# Imported lazily-tolerant so a missing package degrades to polling instead of crashing.
try:
    import websockets
    from websockets import connect as ws_connect
    _WEBSOCKETS_AVAILABLE = True
except Exception:  # pragma: no cover - defensive: fall back to polling if unavailable
    websockets = None
    ws_connect = None
    _WEBSOCKETS_AVAILABLE = False

from src.execution.exchange_client import ExchangeClient, Order, OrderStatus, OrderSide, OrderType


@dataclass
class OrderUpdate:
    """Order status update"""
    order_id: str
    symbol: str
    status: OrderStatus
    filled_quantity: float
    average_price: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'average_price': self.average_price,
            'timestamp': self.timestamp.isoformat()
        }


class OrderTracker:
    """
    Order Status Tracker
    
    Monitors order status via:
    - WebSocket for real-time updates (primary)
    - Polling as fallback
    
    Provides callbacks for order events
    """
    
    def __init__(
        self,
        exchange_client: ExchangeClient,
        polling_interval: int = 5,
        enable_websocket: bool = True
    ):
        self.exchange = exchange_client
        self.polling_interval = polling_interval
        self.enable_websocket = enable_websocket
        
        # Order tracking
        self.tracked_orders: Dict[str, Order] = {}
        self.order_updates: List[OrderUpdate] = []
        
        # Callbacks
        self.on_fill_callbacks: List[Callable] = []
        self.on_partial_fill_callbacks: List[Callable] = []
        self.on_cancel_callbacks: List[Callable] = []
        self.on_reject_callbacks: List[Callable] = []
        
        # WebSocket state
        self.ws_connected = False
        self.ws_task: Optional[asyncio.Task] = None
        self._listen_key: Optional[str] = None
        self._listen_key_keepalive_task: Optional[asyncio.Task] = None

        # Polling state
        self.polling_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Dedup state shared by the WebSocket and polling paths so a fill detected
        # on both transports only fires callbacks once. Keyed by
        # (order_id, terminal_status) for terminal events and
        # (order_id, 'partial', filled_qty) for partial fills, mapped to the time
        # we last emitted it (used to bound memory growth).
        self._emitted_events: Dict[Tuple, float] = {}
        self._emitted_ttl_seconds = 3600  # forget dedup keys after 1h

        logger.info(
            f"Order tracker initialized (websocket={enable_websocket}, "
            f"polling_interval={polling_interval}s)"
        )
    
    def track_order(self, order: Order):
        """Add order to tracking"""
        self.tracked_orders[order.order_id] = order
        logger.info(f"Tracking order: {order.order_id} ({order.symbol})")
    
    def untrack_order(self, order_id: str):
        """Remove order from tracking"""
        if order_id in self.tracked_orders:
            del self.tracked_orders[order_id]
            logger.info(f"Stopped tracking order: {order_id}")
    
    def register_on_fill(self, callback: Callable):
        """Register callback for order fills"""
        self.on_fill_callbacks.append(callback)
    
    def register_on_partial_fill(self, callback: Callable):
        """Register callback for partial fills"""
        self.on_partial_fill_callbacks.append(callback)
    
    def register_on_cancel(self, callback: Callable):
        """Register callback for order cancellations"""
        self.on_cancel_callbacks.append(callback)
    
    def register_on_reject(self, callback: Callable):
        """Register callback for order rejections"""
        self.on_reject_callbacks.append(callback)
    
    async def start(self):
        """Start order tracking"""
        if self.is_running:
            logger.warning("Order tracker already running")
            return
        
        self.is_running = True
        logger.info("Starting order tracker...")
        
        # Start WebSocket if enabled
        if self.enable_websocket:
            self.ws_task = asyncio.create_task(self._websocket_loop())
        
        # Start polling as fallback
        self.polling_task = asyncio.create_task(self._polling_loop())
        
        logger.info("Order tracker started")
    
    async def stop(self):
        """Stop order tracking"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Stopping order tracker...")
        
        # Cancel tasks
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass

        if self._listen_key_keepalive_task:
            self._listen_key_keepalive_task.cancel()
            try:
                await self._listen_key_keepalive_task
            except asyncio.CancelledError:
                pass

        # Best-effort close of the listenKey so we don't leak server-side streams.
        if self._listen_key:
            try:
                await self._close_listen_key(self._listen_key)
            except Exception as e:  # noqa: BLE001 - shutdown best-effort
                logger.debug(f"Failed to close listenKey on shutdown: {e}")

        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Order tracker stopped")
    
    # ------------------------------------------------------------------ #
    # BingX user-data WebSocket
    #
    # BingX swap user-data stream protocol (validate on VST testnet before live):
    #   1. POST  /openApi/user/auth/userDataStream  -> { "listenKey": "<key>" }
    #   2. PUT   /openApi/user/auth/userDataStream?listenKey=<key>  every <30min
    #      keepalive (server expires a key after ~60min of no keepalive).
    #   3. Connect to the swap WS host with ?listenKey=<key> appended.
    #   4. Messages are GZIP-compressed. The server periodically sends the literal
    #      text "Ping"; we must reply with the literal text "Pong" to stay alive.
    #   5. Account events arrive as JSON with field "e": "ORDER_TRADE_UPDATE"
    #      (order/fill updates) and "ACCOUNT_UPDATE" (balance/position updates).
    # ------------------------------------------------------------------ #

    # BingX user-data REST endpoint (listenKey lifecycle). Validate on VST testnet.
    _LISTEN_KEY_ENDPOINT = "/openApi/user/auth/userDataStream"

    def _ws_base_url(self) -> Optional[str]:
        """Return the BingX swap user-data WS host, or None if unsupported.

        BingX uses the same WS host for testnet (VST) and live; the account is
        scoped by the listenKey + API key, not by host. Validate on VST testnet.
        """
        # Only BingX is wired up here; other exchanges fall back to polling.
        if not hasattr(self.exchange, '_request') or not hasattr(self.exchange, 'base_url'):
            return None
        # BingX swap user-data stream host (same host for VST and live).
        # validate on VST testnet
        return "wss://open-api-swap.bingx.com/swap-market"

    async def _get_listen_key(self) -> Optional[str]:
        """Obtain a user-data-stream listenKey from the exchange.

        Implemented via the BingX client's signed `_request` helper so we do not
        need to add a new method to exchange_client.py. Returns None if the
        exchange does not expose the expected interface (then we stay on polling).
        BingX returns {"listenKey": "..."} (the client unwraps any {"data": ...}).
        Validate the endpoint/field names on VST testnet.
        """
        if not hasattr(self.exchange, '_request'):
            return None
        # listenKey creation is authenticated (signed=True) like other private calls.
        resp = await self.exchange._request('POST', self._LISTEN_KEY_ENDPOINT, signed=True)
        # Response may be {"listenKey": "..."} directly or already-unwrapped.
        listen_key = None
        if isinstance(resp, dict):
            listen_key = resp.get('listenKey')
        if not listen_key:
            logger.error(f"BingX listenKey response missing 'listenKey': {resp}")
            return None
        return listen_key

    async def _keepalive_listen_key(self, listen_key: str) -> None:
        """Extend the listenKey TTL (PUT). Validate cadence on VST testnet."""
        if not hasattr(self.exchange, '_request'):
            return
        await self.exchange._request(
            'PUT', self._LISTEN_KEY_ENDPOINT,
            params={'listenKey': listen_key}, signed=True
        )

    async def _close_listen_key(self, listen_key: str) -> None:
        """Invalidate a listenKey (DELETE) on shutdown. Validate on VST testnet."""
        if not hasattr(self.exchange, '_request'):
            return
        await self.exchange._request(
            'DELETE', self._LISTEN_KEY_ENDPOINT,
            params={'listenKey': listen_key}, signed=True
        )

    async def _listen_key_keepalive_loop(self) -> None:
        """Periodically refresh the listenKey so the stream is not expired.

        BingX expires an idle listenKey after ~60 minutes; we refresh well inside
        that window. Failures are logged but non-fatal (the WS reconnect path will
        re-mint a key if the stream actually drops).
        """
        # Refresh every 30 minutes (half the ~60min expiry). validate on VST testnet
        keepalive_interval = 30 * 60
        while self.is_running:
            try:
                await asyncio.sleep(keepalive_interval)
                if self._listen_key:
                    await self._keepalive_listen_key(self._listen_key)
                    logger.debug("Refreshed BingX listenKey")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - keepalive failures are non-fatal
                logger.warning(f"listenKey keepalive failed (will retry/reconnect): {e}")

    async def _websocket_loop(self):
        """User-data WebSocket monitoring loop with reconnect + jittered backoff.

        Runs alongside the polling loop (polling stays as a fallback). Events are
        deduped against the polling path so a fill is only emitted once.
        """
        logger.info("WebSocket monitoring started")

        if not _WEBSOCKETS_AVAILABLE:
            logger.warning(
                "'websockets' package unavailable; user-data WS disabled, "
                "relying on polling fallback only"
            )
            return

        ws_base = self._ws_base_url()
        if ws_base is None:
            logger.warning(
                "Exchange does not support the BingX user-data WS; "
                "relying on polling fallback only"
            )
            return

        attempt = 0  # consecutive failed connection attempts (for backoff)

        while self.is_running:
            try:
                # (Re)obtain a listenKey for this connection.
                listen_key = await self._get_listen_key()
                if not listen_key:
                    raise RuntimeError("could not obtain listenKey")
                self._listen_key = listen_key

                # Start/refresh the keepalive task tied to this listenKey.
                if self._listen_key_keepalive_task is None or self._listen_key_keepalive_task.done():
                    self._listen_key_keepalive_task = asyncio.create_task(
                        self._listen_key_keepalive_loop()
                    )

                url = f"{ws_base}?listenKey={listen_key}"
                logger.info("Connecting to BingX user-data WebSocket...")

                async with ws_connect(url, ping_interval=None) as ws:
                    self.ws_connected = True
                    attempt = 0  # reset backoff on a successful connect
                    logger.info("BingX user-data WebSocket connected")
                    await self._ws_consume(ws)

            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - any failure -> backoff + reconnect
                self.ws_connected = False
                attempt += 1
                # Exponential backoff capped at 60s with full jitter to avoid
                # thundering-herd reconnects.
                base = min(60.0, 2.0 ** min(attempt, 6))
                delay = random.uniform(0.0, base)
                logger.error(
                    f"User-data WS error (attempt {attempt}): {e}; "
                    f"reconnecting in {delay:.1f}s"
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise

        self.ws_connected = False

    async def _ws_consume(self, ws) -> None:
        """Receive/decode messages from an open user-data WS until it closes."""
        while self.is_running:
            # Time out idle waits so a half-open socket is detected and recycled.
            raw = await asyncio.wait_for(ws.recv(), timeout=60.0)

            # BingX may send the keepalive probe as the literal text "Ping";
            # reply with "Pong". validate on VST testnet
            if isinstance(raw, str) and raw == "Ping":
                await ws.send("Pong")
                continue

            text = self._decode_ws_message(raw)
            if text is None:
                continue

            # Some keepalive probes arrive gzipped as well.
            if text == "Ping":
                await ws.send("Pong")
                continue

            try:
                data = json.loads(text)
            except (ValueError, TypeError):
                logger.debug(f"Ignoring non-JSON WS message: {text[:120]}")
                continue

            await self._handle_ws_event(data)

    @staticmethod
    def _decode_ws_message(raw: Any) -> Optional[str]:
        """Decode a raw WS frame to text, transparently gunzipping if needed.

        BingX user-data frames are GZIP-compressed binary. validate on VST testnet
        """
        try:
            if isinstance(raw, bytes):
                # Try gzip first (BingX default), fall back to raw utf-8.
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                        return gz.read().decode('utf-8')
                except OSError:
                    return raw.decode('utf-8', errors='replace')
            if isinstance(raw, str):
                return raw
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to decode WS frame: {e}")
        return None

    async def _handle_ws_event(self, data: Dict[str, Any]) -> None:
        """Route a decoded BingX user-data event to the order callbacks.

        BingX event shape (validate on VST testnet):
          {
            "e": "ORDER_TRADE_UPDATE",
            "E": <eventTimeMs>,
            "o": {
               "s": "BTC-USDT", "i": <orderId>, "c": <clientOrderId>,
               "S": "BUY"/"SELL", "o": <type>, "X": <orderStatus>,
               "q": <origQty>, "z": <cumFilledQty>, "ap": <avgPrice>, "p": <price>,
               ...
            }
          }
        ACCOUNT_UPDATE carries balance/position deltas under "a"; we log it but the
        authoritative order/fill signal comes from ORDER_TRADE_UPDATE.
        """
        event_type = data.get('e')

        if event_type == 'ORDER_TRADE_UPDATE':
            order_info = data.get('o') or {}
            order = self._parse_ws_order(order_info)
            if order is None:
                return
            await self._dispatch_order_event(order, source='ws')

        elif event_type == 'ACCOUNT_UPDATE':
            # Position/balance update — informational here; position state is owned
            # elsewhere. Logged for observability. validate on VST testnet
            logger.debug(f"Account update (position/balance) received: {data.get('a')}")

        else:
            logger.debug(f"Unhandled user-data event: {event_type}")

    def _parse_ws_order(self, o: Dict[str, Any]) -> Optional[Order]:
        """Build an Order from a BingX ORDER_TRADE_UPDATE 'o' payload.

        Field names follow BingX's abbreviated push schema. validate on VST testnet
        """
        order_id = o.get('i') or o.get('orderId')
        if order_id is None:
            logger.debug(f"WS order event missing order id: {o}")
            return None

        # Map raw status string to OrderStatus; unknown statuses are skipped safely.
        raw_status = o.get('X') or o.get('status') or 'NEW'
        try:
            status = OrderStatus[raw_status]
        except KeyError:
            logger.debug(f"Unknown WS order status '{raw_status}' for {order_id}")
            return None

        raw_side = o.get('S') or o.get('side') or 'BUY'
        side = OrderSide.BUY if raw_side == 'BUY' else OrderSide.SELL

        raw_type = o.get('o') or o.get('type') or 'MARKET'
        try:
            order_type = OrderType[raw_type]
        except KeyError:
            order_type = OrderType.MARKET

        def _f(*keys, default=0.0):
            for k in keys:
                v = o.get(k)
                if v not in (None, ''):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return default

        price = _f('p', 'price', default=0.0)
        return Order(
            order_id=str(order_id),
            client_order_id=str(o.get('c') or o.get('clientOrderId') or ''),
            symbol=o.get('s') or o.get('symbol') or '',
            side=side,
            order_type=order_type,
            price=price if price else None,
            quantity=_f('q', 'origQty'),
            status=status,
            filled_quantity=_f('z', 'executedQty'),
            average_price=_f('ap', 'avgPrice'),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    async def _dispatch_order_event(self, new_order: Order, source: str) -> None:
        """Emit fill/partial/cancel/reject callbacks for an order update, deduped.

        Shared by the WebSocket and (indirectly) the polling path so the same fill
        seen on both transports only triggers callbacks once. Keeps the tracked
        order cache in sync and untracks terminal orders.
        """
        old_order = self.tracked_orders.get(new_order.order_id)

        # Always keep the freshest snapshot so polling doesn't re-detect the change.
        self.tracked_orders[new_order.order_id] = new_order

        status = new_order.status

        if status == OrderStatus.PARTIALLY_FILLED:
            # Dedup partials by cumulative filled quantity so each increment fires once.
            key = (new_order.order_id, 'partial', round(new_order.filled_quantity, 12))
            if self._should_emit(key):
                logger.info(
                    f"[{source}] Order {new_order.order_id} partially filled: "
                    f"{new_order.filled_quantity}/{new_order.quantity} "
                    f"@ ${new_order.average_price}"
                )
                self._record_update(new_order)
                await self._trigger_callbacks(self.on_partial_fill_callbacks, new_order)
            return

        # Terminal states are deduped by (order_id, status).
        terminal_map = {
            OrderStatus.FILLED: self.on_fill_callbacks,
            OrderStatus.CANCELED: self.on_cancel_callbacks,
            OrderStatus.REJECTED: self.on_reject_callbacks,
            OrderStatus.EXPIRED: self.on_cancel_callbacks,  # treat expiry like a cancel
        }
        if status in terminal_map:
            key = (new_order.order_id, status.value)
            if self._should_emit(key):
                old_status = old_order.status.value if old_order else 'UNKNOWN'
                logger.info(
                    f"[{source}] Order {new_order.order_id} status: "
                    f"{old_status} -> {status.value}"
                )
                self._record_update(new_order)
                await self._trigger_callbacks(terminal_map[status], new_order)
            # Stop tracking once terminal regardless of who emitted it.
            self.untrack_order(new_order.order_id)

    def _should_emit(self, key: Tuple) -> bool:
        """Return True if `key` has not been emitted recently (and record it).

        Bounds memory by purging keys older than the TTL on each check.
        """
        now = time.time()
        # Purge stale dedup keys.
        if self._emitted_events:
            expired = [k for k, ts in self._emitted_events.items()
                       if now - ts > self._emitted_ttl_seconds]
            for k in expired:
                del self._emitted_events[k]

        if key in self._emitted_events:
            return False
        self._emitted_events[key] = now
        return True

    def _record_update(self, order: Order) -> None:
        """Append an OrderUpdate audit record for an emitted event."""
        self.order_updates.append(OrderUpdate(
            order_id=order.order_id,
            symbol=order.symbol,
            status=order.status,
            filled_quantity=order.filled_quantity,
            average_price=order.average_price,
            timestamp=datetime.now(),
        ))
    
    async def _polling_loop(self):
        """Polling fallback loop"""
        logger.info("Polling monitoring started")
        
        while self.is_running:
            try:
                await self._poll_orders()
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(self.polling_interval)
    
    async def _poll_orders(self):
        """Poll order status for all tracked orders"""
        if not self.tracked_orders:
            return
        
        for order_id, old_order in list(self.tracked_orders.items()):
            try:
                # Get updated order status
                updated_order = await self.exchange.get_order_status(
                    symbol=old_order.symbol,
                    order_id=order_id
                )

                # Only dispatch when something actually changed; the shared
                # dispatcher dedupes against events already emitted by the WS path,
                # keeps the cache in sync, and untracks terminal orders.
                if (updated_order.status != old_order.status or
                        updated_order.filled_quantity != old_order.filled_quantity):
                    await self._dispatch_order_event(updated_order, source='poll')
                else:
                    # No change, but refresh the cached snapshot.
                    self.tracked_orders[order_id] = updated_order

            except Exception as e:
                logger.error(f"Failed to poll order {order_id}: {e}")
    
    async def _trigger_callbacks(self, callbacks: List[Callable], order: Order):
        """Trigger registered callbacks"""
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.error(f"Callback error: {e}", exc_info=True)
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current order status from cache"""
        return self.tracked_orders.get(order_id)
    
    def get_tracked_orders(self) -> List[Order]:
        """Get all tracked orders"""
        return list(self.tracked_orders.values())

    def get_active_orders(self) -> List[Order]:
        """Get tracked orders that are still open (working) on the exchange.

        Active == NEW or PARTIALLY_FILLED. Terminal orders (FILLED/CANCELED/
        REJECTED/EXPIRED) are excluded so emergency cancel-all only targets orders
        that can actually be cancelled.
        """
        active_statuses = {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
        return [o for o in self.tracked_orders.values() if o.status in active_statuses]
    
    def get_recent_updates(self, limit: int = 10) -> List[OrderUpdate]:
        """Get recent order updates"""
        return self.order_updates[-limit:]
