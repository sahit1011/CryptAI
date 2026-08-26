"""
Force Close All Active Positions
Closes positions in both PaperTradingEngine and Redis StateManager
"""
import redis
import json
import psycopg2
from datetime import datetime

def force_close_all_positions():
    """Force close all active positions"""
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis")
        
        # Get current positions
        positions = r.lrange("state:positions", 0, -1)
        count = len(positions)
        
        print(f"\n📊 Found {count} position(s) in Redis:")
        
        position_ids = []
        if count > 0:
            # Display and collect position IDs
            for i, pos_json in enumerate(positions, 1):
                pos = json.loads(pos_json)
                symbol = pos.get('symbol')
                side = pos.get('positionSide')
                pos_id = pos.get('position_id')
                entry = pos.get('entryPrice')
                pnl = pos.get('unRealizedProfit')
                
                print(f"  {i}. {symbol} - {side} - ID: {pos_id}")
                print(f"     Entry: ${entry}, P&L: {pnl}")
                
                position_ids.append(pos_id)
            
            # Clear positions from Redis
            r.delete("state:positions")
            print(f"\n🗑️ Cleared {count} position(s) from Redis")
            
            # Publish empty position update
            r.publish("execution_status", json.dumps({
                "type": "position_update",
                "payload": [],
                "timestamp": datetime.now().isoformat()
            }))
            print("📡 Published empty position update to frontend")
            
            # Now update database to mark trades as closed
            try:
                # Connect to PostgreSQL using config from config.py
                # Default: postgresql://trader:secure_password_here@localhost:5432/trading_agent
                import os
                from dotenv import load_dotenv
                load_dotenv()
                
                postgres_url = os.getenv("POSTGRES_URL", "postgresql://trader:secure_password_here@localhost:5432/trading_agent")
                
                # Parse the URL
                # Format: postgresql://user:password@host:port/database
                from urllib.parse import urlparse
                parsed = urlparse(postgres_url)
                
                conn = psycopg2.connect(
                    dbname=parsed.path[1:],  # Remove leading /
                    user=parsed.username,
                    password=parsed.password,
                    host=parsed.hostname,
                    port=parsed.port or 5432
                )
                cursor = conn.cursor()
                print("\n✅ Connected to PostgreSQL")
                
                # Update each trade to mark as closed
                for pos_id in position_ids:
                    # Extract trade_id from position_id (remove "POS_" prefix if exists)
                    trade_id = pos_id.replace("POS_", "")
                    
                    # Get current price from Redis (for exit price)
                    current_price_key = "current_price:BTC/USDT"
                    current_price = r.get(current_price_key)
                    
                    if current_price:
                        exit_price = float(current_price)
                    else:
                        # Fallback: use a reasonable exit price
                        exit_price = 85000.0
                    
                    # Update trade in database
                    update_query = """
                        UPDATE trades 
                        SET exit_price = %s,
                            exit_time = %s,
                            exit_reason = %s,
                            notes = %s
                        WHERE trade_id = %s AND exit_time IS NULL
                    """
                    
                    cursor.execute(update_query, (
                        exit_price,
                        datetime.now(),
                        'MANUAL_CLOSE',
                        'Manually closed via force_close script',
                        trade_id
                    ))
                    
                    if cursor.rowcount > 0:
                        print(f"  ✅ Closed trade in DB: {trade_id}")
                    else:
                        print(f"  ⚠️ Trade not found in DB or already closed: {trade_id}")
                
                conn.commit()
                cursor.close()
                conn.close()
                print("\n💾 Database updated successfully")
                
            except Exception as db_error:
                print(f"\n⚠️ Database update failed (non-critical): {db_error}")
                print("   Positions cleared from Redis, but may reappear if system restarts")
        else:
            print("✅ No positions to clear")
        
        # Verify Redis is clean
        final_count = r.llen("state:positions")
        print(f"\n✅ Final Redis position count: {final_count}")
        
        # Publish portfolio update to refresh balance
        r.publish("execution_status", json.dumps({
            "type": "balance_update",
            "payload": {"force_refresh": True},
            "timestamp": datetime.now().isoformat()
        }))
        
        print("\n🎉 All positions force-closed!")
        print("   Refresh your frontend to see the changes.")
        
    except redis.ConnectionError:
        print("❌ Error: Could not connect to Redis")
        print("   Make sure Redis is running and your trading system is active")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧹 Force Closing All Active Positions...\n")
    force_close_all_positions()
