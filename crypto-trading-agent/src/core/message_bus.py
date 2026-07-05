"""
Message Bus for inter-agent communication using Redis Pub/Sub
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass, asdict
import redis.asyncio as redis
from loguru import logger

from src.utils.enhanced_logging import PhaseLogger, StepLogger, MetricsLogger
from src.utils.pipeline_logger import PipelineLogger

# Create pipeline logger instance
plog = PipelineLogger()

@dataclass
class AgentMessage:
    """Standard message format"""
    id: str
    sender: str
    receiver: str
    type: str
    payload: Dict[str, Any]
    priority: int = 5
    requires_ack: bool = False
    timestamp: datetime = None
    parent_id: Optional[str] = None
    correlation_id: Optional[str] = None  # CRITICAL FIX: For request/response matching

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d

class MessageBus:
    """
    Redis-based message bus for agent communication
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        # channel -> list of callbacks. A list (not a single callable) so multiple
        # concurrent subscribers to the same channel (e.g. overlapping request/response
        # waiters) don't silently overwrite each other.
        self.subscribers: Dict[str, List[Callable]] = {}
        self.running = False

    async def connect(self):
        """Connect to Redis"""
        plog.method_entry("connect", agent="message_bus", phase="setup")
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            plog.success(
                "Message bus connected to Redis",
                agent="message_bus",
                phase="setup"
            )
            plog.method_exit("connect", result="Redis connection established")
        except Exception as e:
            plog.error(
                f"Failed to connect message bus to Redis: {e}",
                exception=e,
                agent="message_bus",
                phase="setup"
            )
            raise

    async def disconnect(self):
        """Disconnect from Redis (idempotent).

        Always clears self.pubsub / self.redis_client, even on error. This is what
        lets the listen loop's reconnect guard (`if not self.pubsub`) fire after a
        Redis blip — previously the handles were closed but left truthy, so the loop
        kept calling listen() on a dead pubsub and could busy-spin. Never raises:
        both the shutdown path and the error-recovery path call this, and a failing
        teardown must not abort either.
        """
        plog.method_entry("disconnect", agent="message_bus", phase="shutdown")
        pubsub, redis_client = self.pubsub, self.redis_client
        self.pubsub = None
        self.redis_client = None
        try:
            if pubsub:
                await pubsub.close()
            if redis_client:
                await redis_client.close()
            plog.success(
                "Message bus disconnected from Redis",
                agent="message_bus",
                phase="shutdown"
            )
            plog.method_exit("disconnect", result="Redis connection closed")
        except Exception as e:
            plog.warning(
                f"Error during message bus disconnect (ignored): {e}",
                agent="message_bus",
                phase="shutdown"
            )

    async def publish(self, channel: str, message: Dict[str, Any], persist: bool = True):
        """
        Publish message to channel
        
        CRITICAL FIX: Separated pub/sub and queue usage to eliminate message duplication.
        - Pub/sub: Always used for real-time delivery to subscribed agents
        - Queue: Only used when persist=True (for orchestrator responses that need persistence)
        
        Args:
            channel: Channel name to publish to
            message: Message dictionary to publish
            persist: If True, also store in queue for persistence (default: True for backward compatibility)
        """
        try:
            message_type = message.get('type', 'unknown')
            plog.debug(
                f"Publishing message to {channel}: {message_type} (persist={persist})",
                agent="message_bus",
                phase="message_publish"
            )
            
            # DEBUGGING: Log message structure before serialization
            if 'payload' in message and message.get('payload') is not None and 'candles' in message.get('payload', {}):
                candles = message['payload']['candles']
                if isinstance(candles, dict):
                    candle_counts = {tf: len(v) if isinstance(v, list) else 0 for tf, v in candles.items()}
                    plog.debug(
                        f"📦 MessageBus: Publishing message with candles: {candle_counts}",
                        agent="message_bus"
                    )
                else:
                    plog.warning(
                        f"⚠️ MessageBus: Candles is not a dict! Type: {type(candles)}",
                        agent="message_bus"
                    )
            
            message_json = json.dumps(message, default=str)
            
            # DEBUGGING: Log serialized message size
            message_size_kb = len(message_json) / 1024
            plog.debug(
                f"📦 MessageBus: Serialized message size: {message_size_kb:.2f} KB",
                agent="message_bus"
            )
            
            # Check if message is too large (Redis default max is 512MB, but let's warn at 1MB)
            if message_size_kb > 1024:  # 1MB
                plog.warning(
                    f"⚠️ MessageBus: Large message detected ({message_size_kb:.2f} KB), may cause issues",
                    agent="message_bus"
                )
            
            # Always publish to pub/sub for real-time delivery
            await self.redis_client.publish(channel, message_json)

            # Only persist to queue if requested (for orchestrator polling)
            if persist:
                await self.redis_client.lpush(f"queue:{channel}", message_json)
                await self.redis_client.expire(f"queue:{channel}", 3600)  # 1 hour TTL
                plog.debug(
                    f"Message published and queued | channel={channel}, type={message_type}",
                    agent="message_bus"
                )
            else:
                plog.debug(
                    f"Message published (real-time only) | channel={channel}, type={message_type}",
                    agent="message_bus"
                )
        except Exception as e:
            plog.error(
                f"Error publishing message to {channel}: {e}",
                exception=e,
                agent="message_bus",
                phase="message_publish"
            )
            raise

    async def subscribe(self, channel: str, callback: Callable):
        """Subscribe a callback to a channel (multiple callbacks per channel allowed)."""
        plog.method_entry("subscribe", agent="message_bus")
        try:
            is_new_channel = channel not in self.subscribers
            self.subscribers.setdefault(channel, []).append(callback)
            # Only issue the Redis SUBSCRIBE once per channel.
            if is_new_channel:
                await self.pubsub.subscribe(channel)
            plog.info(
                f"Subscribed to channel: {channel}",
                agent="message_bus",
                phase="message_subscribe"
            )

            # Start listener if not running
            if not self.running:
                self.running = True
                asyncio.create_task(self._listen_loop())
                plog.debug(
                    "Started message listener loop",
                    agent="message_bus",
                    phase="message_subscribe"
                )
            
            plog.method_exit("subscribe", result=f"Subscribed to {channel}")
        except Exception as e:
            plog.error(
                f"Error subscribing to channel {channel}: {e}",
                exception=e,
                agent="message_bus",
                phase="message_subscribe"
            )
            raise

    async def unsubscribe(self, channel: str, callback: Optional[Callable] = None):
        """Unsubscribe from a channel.

        If `callback` is given, only that callback is removed and the Redis
        UNSUBSCRIBE is issued only once the channel has no callbacks left — so one
        request/response waiter tearing down does not silence the others still
        listening on the same channel. If `callback` is None, all callbacks for the
        channel are removed (backward-compatible behaviour).
        """
        plog.method_entry("unsubscribe", agent="message_bus")
        try:
            callbacks = self.subscribers.get(channel)
            if callbacks is not None and callback is not None:
                try:
                    callbacks.remove(callback)
                except ValueError:
                    pass
            if callback is None or not self.subscribers.get(channel):
                self.subscribers.pop(channel, None)
                if self.pubsub:
                    await self.pubsub.unsubscribe(channel)
            plog.info(
                f"Unsubscribed from channel: {channel}",
                agent="message_bus",
                phase="message_unsubscribe"
            )
            plog.method_exit("unsubscribe", result=f"Unsubscribed from {channel}")
        except Exception as e:
            plog.error(
                f"Error unsubscribing from channel {channel}: {e}",
                exception=e,
                agent="message_bus",
                phase="message_unsubscribe"
            )
            raise

    async def _listen_loop(self):
        """Listen for messages on subscribed channels with auto-recovery"""
        plog.method_entry("_listen_loop", agent="message_bus", phase="message_listening")
        
        while self.running:
            try:
                # Ensure we're connected
                if not self.redis_client or not self.pubsub:
                    plog.warning(
                        "Redis not connected in listen loop, attempting reconnection...",
                        agent="message_bus",
                        phase="message_listening"
                    )
                    await self.connect()
                    # Resubscribe to all channels
                    channels_count = len(self.subscribers.keys())
                    plog.debug(
                        f"Resubscribing to {channels_count} channels",
                        agent="message_bus",
                        phase="message_listening"
                    )
                    for channel in list(self.subscribers.keys()):
                        await self.pubsub.subscribe(channel)
                
                async for message in self.pubsub.listen():
                    try:
                        if message['type'] == 'message':
                            channel = message['channel'].decode()
                            data = json.loads(message['data'].decode())

                            plog.debug(
                                f"Processing message on {channel}: {data.get('type', 'unknown')}",
                                agent="message_bus",
                                phase="message_listening"
                            )

                            # Fan out to every registered callback for the channel.
                            for cb in list(self.subscribers.get(channel, ())):
                                await cb(data)

                    except Exception as e:
                        plog.error(
                            f"Error processing message in listen loop: {e}",
                            exception=e,
                            agent="message_bus",
                            phase="message_listening"
                        )
                        continue

                # listen() returned without raising -> the connection ended cleanly
                # (or was closed). Drop the handles so the top of the loop reconnects,
                # and pause briefly to avoid a tight spin if it keeps returning empty.
                if self.running:
                    await self.disconnect()
                    await asyncio.sleep(1)

            except Exception as e:
                plog.error(
                    f"Listen loop error: {e}, will retry in 5 seconds...",
                    exception=e,
                    agent="message_bus",
                    phase="message_listening"
                )
                # disconnect() nulls the handles so the loop top reconnects cleanly.
                await self.disconnect()
                await asyncio.sleep(5)
                # Loop will retry connection at the start
        
        plog.method_exit("_listen_loop", result="Listener stopped")

    async def get_queue_length(self, channel: str) -> int:
        """Get number of messages in queue"""
        return await self.redis_client.llen(f"queue:{channel}")

    async def get_from_queue(self, channel: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Pop message from queue"""
        result = await self.redis_client.brpop(f"queue:{channel}", timeout=timeout)
        if result:
            _, message_json = result
            return json.loads(message_json)
        return None

    async def send_to_dlq(self, message: Dict[str, Any], reason: str):
        """Send failed message to Dead Letter Queue"""
        plog.method_entry("send_to_dlq", agent="message_bus")
        try:
            dlq_message = {
                **message,
                "dlq_reason": reason,
                "dlq_timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.lpush("dlq", json.dumps(dlq_message, default=str))
            plog.warning(
                f"Message sent to DLQ: {reason}",
                agent="message_bus",
                phase="message_error"
            )
            plog.method_exit("send_to_dlq", result=f"DLQ message queued: {reason}")
        except Exception as e:
            plog.error(
                f"Error sending message to DLQ: {e}",
                exception=e,
                agent="message_bus",
                phase="message_error"
            )
            raise