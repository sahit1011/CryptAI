
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text
from rich.console import Console

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def check_portfolio():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Calculate total PnL from closed trades
        result = conn.execute(text("SELECT SUM(pnl) FROM trades WHERE exit_time IS NOT NULL"))
        total_pnl = result.fetchone()[0] or 0.0
        
        # Initial capital (hardcoded or from config, assuming 10k based on previous context)
        initial_capital = 10000.0
        current_capital = initial_capital + float(total_pnl)
        
        console.print(f"\n[bold]Portfolio Status (Database):[/bold]")
        console.print(f"  Initial Capital: ${initial_capital:,.2f}")
        console.print(f"  Total PnL: ${total_pnl:+,.2f}")
        console.print(f"  Current Capital: ${current_capital:,.2f}")

if __name__ == "__main__":
    check_portfolio()
