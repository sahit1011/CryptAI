
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sqlalchemy import create_engine, text
from rich.console import Console
from rich.table import Table

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def check_closed_trades():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Select details of closed trades
        query = text("""
            SELECT id, trade_id, symbol, strategy_type, entry_price, exit_price,
                   pnl, pnl_percentage, entry_time, exit_time, is_winner
            FROM trades 
            WHERE exit_time IS NOT NULL
            ORDER BY exit_time DESC
        """)
        result = conn.execute(query)
        trades = result.fetchall()
        
        if not trades:
            console.print("[yellow]No closed trades found.[/yellow]")
            return

        table = Table(title=f"Closed Trades ({len(trades)})")
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Strategy", style="blue")
        table.add_column("Entry", justify="right")
        table.add_column("Exit", justify="right")
        table.add_column("PnL", justify="right", style="bold")
        table.add_column("Result", justify="center")
        table.add_column("Exit Time", style="dim")

        total_pnl = 0.0
        wins = 0
        losses = 0

        for trade in trades:
            pnl = trade.pnl if trade.pnl is not None else 0.0
            total_pnl += pnl
            
            if trade.is_winner:
                wins += 1
                result_str = "[green]WIN[/green]"
                pnl_str = f"[green]+${pnl:,.2f}[/green]"
            else:
                losses += 1
                result_str = "[red]LOSS[/red]"
                pnl_str = f"[red]${pnl:,.2f}[/red]"

            table.add_row(
                str(trade.id),
                trade.symbol,
                trade.strategy_type or "N/A",
                f"${trade.entry_price:,.2f}",
                f"${trade.exit_price:,.2f}",
                pnl_str,
                result_str,
                str(trade.exit_time)
            )
            
        console.print(table)
        
        # Summary
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Total Closed Trades: {len(trades)}")
        console.print(f"  Total PnL: ${total_pnl:,.2f}")
        if len(trades) > 0:
            win_rate = (wins / len(trades)) * 100
            console.print(f"  Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)")

if __name__ == "__main__":
    check_closed_trades()
