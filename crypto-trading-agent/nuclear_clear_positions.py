"""
Nuclear Option: Clear All Position State
Clears positions from Redis, Database, and sends shutdown signal to force refresh
"""
import redis
import json
import psycopg2
from datetime import datetime
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

def nuclear_clear():
    """Clear everything and force system refresh"""
    print("🚨 NUCLEAR OPTION: Clearing all position state...\n")
    
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis")
        
        # 1. Clear positions from Redis
        positions = r.lrange("state:positions", 0, -1)
        count = len(positions)
        print(f"\n📊 Found {count} position(s) in Redis")
        
        if count > 0:
            for i, pos_json in enumerate(positions, 1):
                pos = json.loads(pos_json)
                print(f"  {i}. {pos.get('symbol')} - {pos.get('positionSide')} - ID: {pos.get('position_id')}")
        
        # Clear Redis positions
        r.delete("state:positions")
        print(f"🗑️ Cleared positions from Redis")
        
        # 2. Clear portfolio state to force recalculation
        r.delete("state:portfolio")
        print("🗑️ Cleared portfolio state")
        
        # 3. Publish empty position update
        r.publish("execution_status", json.dumps({
            "type": "position_update",
            "payload": [],
            "timestamp": datetime.now().isoformat()
        }))
        print("📡 Published empty position update")
        
        # 4. Publish force refresh signal
        r.publish("execution_status", json.dumps({
            "type": "force_refresh",
            "payload": {"clear_positions": True},
            "timestamp": datetime.now().isoformat()
        }))
        print("📡 Published force refresh signal")
        
        # 5. Update database to close ALL open trades
        try:
            load_dotenv()
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
            print("\n✅ Connected to PostgreSQL")
            
            # Get current price for exit
            current_price_key = "current_price:BTC/USDT"
            current_price = r.get(current_price_key)
            exit_price = float(current_price) if current_price else 85000.0
            
            # Close ALL open trades
            update_query = """
                UPDATE trades 
                SET exit_price = %s,
                    exit_time = %s,
                    exit_reason = %s,
                    notes = %s
                WHERE exit_time IS NULL
            """
            
            cursor.execute(update_query, (
                exit_price,
                datetime.now(),
                'FORCE_CLOSE',
                'Force closed via nuclear_clear script'
            ))
            
            closed_count = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"💾 Closed {closed_count} open trade(s) in database")
            
        except Exception as db_error:
            print(f"⚠️ Database update failed: {db_error}")
        
        # 6. Verify everything is clean
        final_positions = r.llen("state:positions")
        final_portfolio = r.exists("state:portfolio")
        
        print(f"\n✅ Verification:")
        print(f"   - Redis positions: {final_positions}")
        print(f"   - Redis portfolio exists: {bool(final_portfolio)}")
        
        print("\n🎉 Nuclear clear complete!")
        print("\n⚠️ IMPORTANT: You should restart your trading system now")
        print("   This will ensure PaperTradingEngine reloads with clean state")
        
    except redis.ConnectionError:
        print("❌ Error: Could not connect to Redis")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("NUCLEAR OPTION: Clear All Position State")
    print("="*60)
    print("\nThis will:")
    print("  1. Clear all positions from Redis")
    print("  2. Clear portfolio state")
    print("  3. Close all open trades in database")
    print("  4. Send force refresh signals")
    print("\n⚠️ WARNING: This is a forceful reset!")
    print("="*60)
    
    nuclear_clear()
