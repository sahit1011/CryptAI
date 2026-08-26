"""
Delete Specific Trade (Latest)
Deletes the trade: BTC/USDT SHORT @ $85,100
"""
import psycopg2
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

def delete_trade():
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
        
        # Find the trade
        query = """
            SELECT trade_id, symbol, direction, entry_price, exit_reason, entry_time 
            FROM trades 
            WHERE symbol = 'BTC/USDT' 
            AND direction = 'SHORT' 
            AND entry_price = 85100 
        """
        
        cursor.execute(query)
        trades = cursor.fetchall()
        
        if not trades:
            print("❌ No matching trade found to delete.")
            return

        print(f"\nFound {len(trades)} matching trade(s):")
        for t in trades:
            print(f"  - ID: {t[0]} | {t[1]} {t[2]} @ ${t[3]} | Reason: {t[4]} | Time: {t[5]}")
            
        # Delete them
        delete_query = """
            DELETE FROM trades 
            WHERE symbol = 'BTC/USDT' 
            AND direction = 'SHORT' 
            AND entry_price = 85100 
        """
        
        cursor.execute(delete_query)
        deleted_count = cursor.rowcount
        conn.commit()
        
        print(f"\n🗑️ Successfully deleted {deleted_count} trade(s) from database.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    delete_trade()
