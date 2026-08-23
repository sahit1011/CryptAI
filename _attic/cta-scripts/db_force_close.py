"""
Inspect and Close Open Trades in Database
"""
import psycopg2
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime

def inspect_and_close():
    try:
        # Connect to PostgreSQL
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
        print("✅ Connected to PostgreSQL")
        
        # 1. List ALL trades that don't have an exit time (Open Trades)
        query = """
            SELECT trade_id, symbol, direction, entry_price, entry_time 
            FROM trades 
            WHERE exit_time IS NULL
        """
        
        cursor.execute(query)
        open_trades = cursor.fetchall()
        
        if not open_trades:
            print("✅ No open trades found in database.")
        else:
            print(f"\n⚠️ Found {len(open_trades)} OPEN trades in database:")
            for t in open_trades:
                print(f"  - ID: {t[0]} | {t[1]} {t[2]} @ ${t[3]} | Time: {t[4]}")
                
            # 2. Force Close/Delete them
            print("\n🧹 Force closing these trades in DB...")
            
            # Option A: Mark as closed
            update_query = """
                UPDATE trades 
                SET exit_time = %s, exit_price = entry_price, exit_reason = 'FORCE_CLOSE_SCRIPT', pnl = 0
                WHERE exit_time IS NULL
            """
            cursor.execute(update_query, (datetime.now(),))
            
            # Option B: Delete them (uncomment if you prefer deletion)
            # delete_query = "DELETE FROM trades WHERE exit_time IS NULL"
            # cursor.execute(delete_query)
            
            count = cursor.rowcount
            conn.commit()
            print(f"✅ Closed {count} trades in database.")

        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    inspect_and_close()
