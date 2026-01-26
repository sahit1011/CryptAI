
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text
from rich.console import Console

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def delete_active_trades():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Check count before
        result = conn.execute(text("SELECT COUNT(*) FROM trades WHERE exit_time IS NULL"))
        count_before = result.fetchone()[0]
        console.print(f"Active trades before: {count_before}")
        
        if count_before > 0:
            # Delete active trades
            conn.execute(text("DELETE FROM trades WHERE exit_time IS NULL"))
            conn.commit()
            console.print("[bold green]Deleted active trades.[/bold green]")
            
            # Check count after
            result = conn.execute(text("SELECT COUNT(*) FROM trades WHERE exit_time IS NULL"))
            count_after = result.fetchone()[0]
            console.print(f"Active trades after: {count_after}")
        else:
            console.print("No active trades to delete.")

if __name__ == "__main__":
    delete_active_trades()
