"""Owner-controlled AI-engine switch.

The trading daemon burns LLM calls every cycle (analysis + strategy per symbol). On a
free OpenRouter key that exhausts the daily quota in under an hour, so the engine must
NOT run unattended — the owner turns it on when they want analysis, and it auto-stops
after a chosen window.

State lives in a single Redis key `engine:on`:
  - key present  -> engine ON. Its TTL is the auto-off timer (or none = "always on").
  - key absent   -> engine OFF (the default, and the safe failure mode).

Because auto-off is just Redis key expiry, there is no timestamp bookkeeping, and a
Redis restart (Render's free tier has no persistence) fails the engine OFF — no
runaway credit burn if the switch state is ever lost.
"""
import json
from typing import Optional

from loguru import logger

ENGINE_KEY = "engine:on"


class EngineSwitch:
    """Async wrapper over the Redis engine flag. Share one Redis client with the app."""

    def __init__(self, redis_client):
        # redis.asyncio client (same one StateManager/MessageBus use).
        self.redis = redis_client

    async def is_on(self) -> bool:
        """True if the engine is currently enabled (key present and unexpired)."""
        try:
            return bool(await self.redis.exists(ENGINE_KEY))
        except Exception as e:
            # Fail OFF: if we can't read the switch, don't burn credits.
            logger.warning(f"engine switch read failed, treating as OFF: {e}")
            return False

    async def turn_on(self, *, duration_seconds: Optional[int], enabled_by: str = "owner") -> dict:
        """Enable the engine. duration_seconds=None means 'always on' (no auto-off)."""
        payload = json.dumps({"enabled_by": enabled_by, "duration_seconds": duration_seconds})
        if duration_seconds and duration_seconds > 0:
            await self.redis.set(ENGINE_KEY, payload, ex=int(duration_seconds))
        else:
            await self.redis.set(ENGINE_KEY, payload)
        logger.info(f"AI engine turned ON by {enabled_by} (duration={duration_seconds or 'always'})")
        return await self.status()

    async def turn_off(self, *, disabled_by: str = "owner") -> dict:
        """Disable the engine immediately."""
        await self.redis.delete(ENGINE_KEY)
        logger.info(f"AI engine turned OFF by {disabled_by}")
        return await self.status()

    async def status(self) -> dict:
        """Current state: {enabled, expires_in_seconds (None if always/off), enabled_by}."""
        try:
            raw = await self.redis.get(ENGINE_KEY)
            if raw is None:
                return {"enabled": False, "expires_in_seconds": None, "enabled_by": None}
            ttl = await self.redis.ttl(ENGINE_KEY)  # -1 = no expiry, >=0 = seconds left
            meta = {}
            try:
                meta = json.loads(raw)
            except (ValueError, TypeError):
                pass
            return {
                "enabled": True,
                "expires_in_seconds": ttl if (ttl is not None and ttl >= 0) else None,
                "enabled_by": meta.get("enabled_by"),
            }
        except Exception as e:
            logger.warning(f"engine switch status failed, reporting OFF: {e}")
            return {"enabled": False, "expires_in_seconds": None, "enabled_by": None}
