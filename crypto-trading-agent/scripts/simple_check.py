
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def check():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, trade_id, pnl, strategy_type FROM trades WHERE exit_time IS NULL"))
        rows = result.fetchall()
        print(f"Found {len(rows)} active trades:")
        for row in rows:
            print(row)

if __name__ == "__main__":
    check()
