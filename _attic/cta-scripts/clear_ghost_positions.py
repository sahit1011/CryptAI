"""
Clear Ghost Positions - Simple Version
Removes orphaned positions from Redis StateManager
"""
import redis
import json

def clear_positions():
    """Clear all positions from Redis"""
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Test connection
        r.ping()
        print("✅ Connected to Redis")
        
        # Get current positions
        positions = r.lrange("state:positions", 0, -1)
        count = len(positions)
        
        print(f"\n📊 Found {count} position(s) in Redis:")
        
        if count > 0:
            # Display positions
            for i, pos_json in enumerate(positions, 1):
                pos = json.loads(pos_json)
                print(f"  {i}. {pos.get('symbol')} - {pos.get('positionSide')} - ID: {pos.get('position_id')}")
                print(f"     Entry: ${pos.get('entryPrice')}, P&L: {pos.get('unRealizedProfit')}")
            
            # Clear all positions
            r.delete("state:positions")
            print(f"\n🗑️ Cleared {count} position(s) from Redis")
            
            # Publish empty position update
            r.publish("execution_status", json.dumps({
                "type": "position_update",
                "payload": [],
                "timestamp": "now"
            }))
            print("📡 Published empty position update")
        else:
            print("✅ No positions to clear")
        
        # Verify
        final_count = r.llen("state:positions")
        print(f"\n✅ Final position count: {final_count}")
        print("\n🎉 Done! Refresh your frontend to see the changes.")
        
    except redis.ConnectionError:
        print("❌ Error: Could not connect to Redis")
        print("   Make sure Redis is running and your trading system is active")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧹 Clearing Ghost Positions from Redis...\n")
    clear_positions()
