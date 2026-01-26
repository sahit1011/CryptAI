"""
Quick script to clear corrupted Redis keys
"""
import redis
import sys

try:
    # Connect to Redis
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    # Test connection
    r.ping()
    print("✅ Connected to Redis")
    
    # Delete the corrupted portfolio key
    deleted = r.delete("state:portfolio")
    if deleted:
        print(f"✅ Deleted corrupted 'state:portfolio' key")
    else:
        print("ℹ️  'state:portfolio' key did not exist")
    
    # Also clear positions just in case
    deleted_pos = r.delete("state:positions")
    if deleted_pos:
        print(f"✅ Deleted 'state:positions' key")
    
    print("\n✅ Redis cleaned! You can now restart the system.")
    
except redis.ConnectionError:
    print("❌ Could not connect to Redis. Is it running?")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
