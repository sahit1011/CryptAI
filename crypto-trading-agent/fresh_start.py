"""
Fresh Start Script
Completely wipes all trade history and active positions to start fresh.
"""
import psycopg2
import redis
import os
import json
from dotenv import load_dotenv
from urllib.parse import urlparse

def fresh_start():
    print("🧹 Starting Fresh Start Cleanup...")
    
    # 1. Clear Redis
    try:
        load_dotenv()
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        
        # Keys to delete
        keys_to_delete = [
            "positions", 
            "portfolio", 
            "trades", 
            "orders",
            "active_trade_ids"
        ]
        
        # Also find any keys starting with 'position:' or 'trade:'
        for key in r.keys("position:*"):
            keys_to_delete.append(key)
        for key in r.keys("trade:*"):
            keys_to_delete.append(key)
            
        if keys_to_delete:
            r.delete(*keys_to_delete)
            print(f"✅ Cleared {len(keys_to_delete)} keys from Redis")
        else:
            print("✅ Redis already clean")
            
        # Send force refresh signal
        r.publish("execution_status", json.dumps({
            "type": "full_refresh",
            "timestamp": "now"
        }))
        
    except Exception as e:
        print(f"❌ Redis Error: {e}")

    # 2. Clear Database
    try:
        postgres_url = os.getenv("POSTGRES_URL", "postgresql://trader:secure_password_here@localhost:5432/trading_agent")
        parsed = urlparse(postgres_url)
        
        conn = psycopg2.connect(
            dbname=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432
        )
        cursor = conn.cursor()
        
        # Delete ALL trades
        cursor.execute("DELETE FROM trades")
        deleted_count = cursor.rowcount
        conn.commit()
        
        print(f"✅ Deleted {deleted_count} trades from PostgreSQL database")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database Error: {e}")

    print("\n✨ System is completely clean! You can restart now.")

if __name__ == "__main__":
    fresh_start()
