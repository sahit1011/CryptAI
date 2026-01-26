

"""
Binance WebSocket client for real-time market data
Enhanced with proper callback routing and ticker support
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Callable, Optional
from websockets import connect, WebSocketClientProtocol
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

class BinanceWebSocketClient:
    """
    Real-time WebSocket client for Binance Futures
    """

    BASE_URL = "wss://fstream.binance.com/ws"

    def __init__(self, on_reconnect_callback: Optional[Callable] = None):
        self.ws: Optional[WebSocketClientProtocol] = None
        self.subscriptions: List[str] = []
        self.callbacks: Dict[str, List[Callable]] = {}
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.on_reconnect_callback = on_reconnect_callback

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.ws = await connect(self.BASE_URL)
            self.running = True
            self.reconnect_attempts = 0
            logger.info("✅ Connected to Binance WebSocket")

            # Resubscribe to streams
            if self.subscriptions:
                await self._resubscribe()

            # Start message loop
            asyncio.create_task(self._message_loop())

        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            await self._handle_reconnect()

    async def disconnect(self):
        """Close WebSocket connection"""
        self.running = False
        if self.ws:
            await self.ws.close()
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

            if stream not in self.callbacks:
                self.callbacks[stream] = []
            self.callbacks[stream].append(callback)

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

        self.subscriptions.append(stream)
        if callback:
            if stream not in self.callbacks:
                self.callbacks[stream] = []
            self.callbacks[stream].append(callback)

        if self.ws:
            await self._subscribe([stream])

        logger.info(f"Subscribed to {stream}")

    async def subscribe_funding_rate(self, symbol: str, callback: Callable):
        """Subscribe to mark price updates (includes funding rate info)"""
        symbol = symbol.lower()
        # Use markPrice stream which includes funding rate information
        stream = f"{symbol}@markprice@1s"

        self.subscriptions.append(stream)
        if stream not in self.callbacks:
            self.callbacks[stream] = []
        self.callbacks[stream].append(callback)

        if self.ws:
            await self._subscribe([stream])

        logger.info(f"Subscribed to mark price (funding rate): {stream}")

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """Subscribe to 24hr ticker updates for live price"""
        symbol = symbol.lower()
        stream = f"{symbol}@ticker"

        self.subscriptions.append(stream)
        if stream not in self.callbacks:
            self.callbacks[stream] = []
        self.callbacks[stream].append(callback)

        if self.ws:
            await self._subscribe([stream])

        logger.info(f"Subscribed to ticker (live price): {stream}")

    async def _subscribe(self, streams: List[str]):
        """Send subscription message"""
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(datetime.now(timezone.utc).timestamp())
        }

        await self.ws.send(json.dumps(subscribe_message))
        logger.info(f"Sent subscription request for {len(streams)} streams")

    async def _resubscribe(self):
        """Resubscribe to all streams after reconnection"""
        if self.subscriptions:
            await self._subscribe(self.subscriptions)
            logger.info(f"Resubscribed to {len(self.subscriptions)} streams")

    async def _message_loop(self):
        """Main message receiving loop"""
        while self.running:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=30.0)
                data = json.loads(message)

                # Handle different message types
                if 'e' in data:  # Event type present
                    await self._handle_event(data)
                elif 'result' in data or 'id' in data:
                    # Subscription confirmation
                    logger.debug(f"Subscription response: {data}")

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await self._send_ping()
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                await self._handle_reconnect()
                break

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

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=4, max=60)
    )
    async def _handle_reconnect(self):
        """Handle reconnection with exponential backoff"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.critical("Max reconnection attempts reached. Stopping.")
            self.running = False
            return

        self.reconnect_attempts += 1
        logger.warning(f"Reconnecting... Attempt {self.reconnect_attempts}")

        await self.disconnect()
        await asyncio.sleep(2 ** self.reconnect_attempts)
        await self.connect()
        
        # Notify callback after successful reconnection
        if self.on_reconnect_callback:
            try:
                await self.on_reconnect_callback()
            except Exception as e:
                logger.error(f"Error in reconnect callback: {e}")