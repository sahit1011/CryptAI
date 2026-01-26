"""
Database initialization script
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.data.data_models import Base
from src.utils.config import get_config
import redis

async def setup_postgresql():
    """Initialize PostgreSQL database"""
    config = get_config()

    # Create engine
    engine = create_engine(config.database.postgres_url)

    # Create all tables
    Base.metadata.create_all(engine)

    print("PostgreSQL tables created successfully!")

    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()

    return session

async def setup_redis():
    """Initialize Redis structure"""
    config = get_config()

    r = redis.from_url(config.database.redis_url)

    # Define Redis key structure
    redis_structure = {
        # Market data cache (TTL: 5 minutes)
        "market_data:{symbol}:{timeframe}": "hash",

        # Current state
        "state:current_prices": "hash",
        "state:positions": "list",
        "state:portfolio": "hash",

        # Agent states
        "agent:{agent_name}:state": "string",
        "agent:{agent_name}:last_update": "string",

        # Message queues
        "queue:{agent_name}_inbox": "list",

        # Pub/Sub channels
        "channel:market_data": "pubsub",
        "channel:trade_signals": "pubsub",
        "channel:alerts": "pubsub",

        # Cache
        "cache:analysis:{context_hash}": "string",  # TTL: 30 min

        # Rate limiting
        "ratelimit:llm_calls:{model}": "string",  # TTL: 1 hour
    }

    print("Redis structure initialized!")
    print("\nRedis Key Structure:")
    for key, type_ in redis_structure.items():
        print(f"  • {key} ({type_})")

    return r

async def main():
    print("Initializing databases...")

    # Setup PostgreSQL
    pg_session = await setup_postgresql()

    # Setup Redis
    redis_client = await setup_redis()

    print("\nAll databases initialized successfully!")
    print("\nYou can now:")
    print("  1. View PostgreSQL: http://localhost:5050")
    print("  2. Connect to Redis: redis-cli")

if __name__ == "__main__":
    asyncio.run(main())