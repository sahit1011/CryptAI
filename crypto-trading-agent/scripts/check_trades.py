
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text
from rich.console import Console

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def check_trades():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Count active trades
        result = conn.execute(text("SELECT COUNT(*) FROM trades WHERE exit_time IS NULL"))
        active_count = result.fetchone()[0]
        console.print(f"Active trades (exit_time IS NULL): {active_count}")

        # Show distinct strategy types
        result = conn.execute(text("SELECT DISTINCT strategy_type FROM trades"))
        strategies = result.fetchall()
        console.print(f"Distinct strategy types: {strategies}")

        # Show sample active trades
        result = conn.execute(text("SELECT id, trade_id, symbol, strategy_type, entry_time FROM trades WHERE exit_time IS NULL LIMIT 5"))
        trades = result.fetchall()
        console.print("Sample active trades:")
        for trade in trades:
            console.print(trade)

if __name__ == "__main__":
    check_trades()
