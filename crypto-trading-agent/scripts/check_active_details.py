
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text
from rich.console import Console
from rich.table import Table

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def check_active_trades_details():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Select details of active trades
        query = text("""
            SELECT id, trade_id, symbol, strategy_type, entry_price, position_size, 
                   pnl, pnl_percentage, created_at, notes
            FROM trades 
            WHERE exit_time IS NULL
            ORDER BY created_at DESC
        """)
        result = conn.execute(query)
        trades = result.fetchall()
        
        if not trades:
            console.print("[yellow]No active trades found.[/yellow]")
            return

        table = Table(title="Active Trades")
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Strategy", style="green")
        table.add_column("Entry Price", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("PnL", justify="right")
        table.add_column("Created At", style="blue")
        table.add_column("Notes")

        for trade in trades:
            pnl_str = f"{trade.pnl:.2f}" if trade.pnl is not None else "N/A"
            table.add_row(
                str(trade.id),
                trade.symbol,
                trade.strategy_type or "N/A",
                f"${trade.entry_price:,.2f}",
                str(trade.position_size),
                pnl_str,
                str(trade.created_at),
                trade.notes or ""
            )
            
        console.print(table)

if __name__ == "__main__":
    check_active_trades_details()
