"""
List and Delete All Trades
"""
import psycopg2
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

def list_and_delete():
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
        
        # List ALL trades
        query = """
            SELECT trade_id, symbol, direction, entry_price, exit_price, exit_reason, entry_time 
            FROM trades 
            ORDER BY entry_time DESC
            LIMIT 20
        """
        
        cursor.execute(query)
        trades = cursor.fetchall()
        
        if not trades:
            print("✅ No trades found in database.")
        else:
            print(f"\n📊 Found {len(trades)} recent trades:")
            for i, t in enumerate(trades, 1):
                print(f"  {i}. ID: {t[0]}")
                print(f"     {t[1]} {t[2]} @ Entry: ${t[3]} | Exit: ${t[4]} | Reason: {t[5]}")
                print(f"     Time: {t[6]}\n")
                
            # Delete ALL trades
            print("🗑️ Deleting ALL trades from database...")
            delete_query = "DELETE FROM trades"
            cursor.execute(delete_query)
            deleted_count = cursor.rowcount
            conn.commit()
            
            print(f"✅ Deleted {deleted_count} trades from database.")

        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    list_and_delete()
