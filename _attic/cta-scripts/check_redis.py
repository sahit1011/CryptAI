import asyncio
from src.core.message_bus import MessageBus
from src.utils.config import get_config

async def check_redis():
    try:
        config = get_config()
        print(f"Checking Redis at {config.database.redis_url}")
        bus = MessageBus(config.database.redis_url)
        await bus.connect()
        print("Redis connection successful!")
        await bus.disconnect()
    except Exception as e:
        print(f"Redis connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_redis())
