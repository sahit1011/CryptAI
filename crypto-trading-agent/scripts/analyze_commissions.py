
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from rich.console import Console
from rich.table import Table

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def analyze_commissions():
    engine = create_engine(DATABASE_URL)
    
    # Taker fee from PaperTradingEngine (0.06%)
    TAKER_FEE = 0.0006
    
    with engine.connect() as conn:
        # Fetch detailed trade info
        query = text("""
            SELECT 
                trade_id, 
                symbol, 
                position_size, 
                entry_price, 
                exit_price, 
                leverage,
                pnl
            FROM trades 
            WHERE exit_time IS NOT NULL
            ORDER BY created_at ASC
        """)
        result = conn.execute(query)
        trades = result.fetchall()
        
    table = Table(title="Commission Analysis Breakdown", show_header=True, header_style="bold magenta")
    table.add_column("Trade ID", style="cyan")
    table.add_column("Size (BTC)", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Notional Value", justify="right", style="yellow")
    table.add_column("Commission (0.06% x 2)", justify="right", style="red")
    
    total_commission = 0.0
    total_notional = 0.0
    
    for trade in trades:
        trade_id = trade.trade_id
        size = float(trade.position_size)
        entry = float(trade.entry_price)
        exit_price = float(trade.exit_price)
        
        # Calculate Notional Values
        entry_notional = size * entry
        exit_notional = size * exit_price
        
        # Calculate Commissions
        entry_comm = entry_notional * TAKER_FEE
        exit_comm = exit_notional * TAKER_FEE
        total_trade_comm = entry_comm + exit_comm
        
        total_commission += total_trade_comm
        total_notional += entry_notional
        
        table.add_row(
            trade_id[-8:],  # Short ID
            f"{size:.4f}",
            f"${entry:,.2f}",
            f"${entry_notional:,.2f}",
            f"${total_trade_comm:,.2f}"
        )
        
    console.print(table)
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"Total Traded Volume (Notional): [yellow]${total_notional:,.2f}[/yellow]")
    console.print(f"Total Commission Paid: [red]${total_commission:,.2f}[/red]")
    console.print(f"Effective Fee Rate: {(total_commission/total_notional*100):.3f}% (of entry volume)")
    console.print("\n[italic]Note: Commissions are calculated on the NOTIONAL value (Size * Price), not your margin.[/italic]")

if __name__ == "__main__":
    analyze_commissions()
