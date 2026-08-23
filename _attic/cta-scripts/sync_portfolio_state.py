
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from src.core.state_manager import StateManager
from rich.console import Console

console = Console()
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

async def sync_portfolio():
    # 1. Calculate from DB
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Get total PnL
        result = conn.execute(text("SELECT SUM(pnl) FROM trades WHERE exit_time IS NOT NULL"))
        total_pnl = float(result.fetchone()[0] or 0.0)
        
        # Get win/loss counts
        result = conn.execute(text("SELECT COUNT(*) FROM trades WHERE exit_time IS NOT NULL AND is_winner = TRUE"))
        wins = result.fetchone()[0]
        
        result = conn.execute(text("SELECT COUNT(*) FROM trades WHERE exit_time IS NOT NULL"))
        total_trades = result.fetchone()[0]
        
    # Calculate commissions (0.06% taker fee per side, matching PaperTradingEngine)
    # We need to fetch trade details to calculate this accurately
    result = conn.execute(text("SELECT position_size, entry_price, exit_price FROM trades WHERE exit_time IS NOT NULL"))
    trades = result.fetchall()
    
    total_commission = 0.0
    taker_fee = 0.0006  # 0.06%
    
    for size, entry, exit_price in trades:
        # Entry commission
        entry_notional = float(size) * float(entry)
        total_commission += entry_notional * taker_fee
        
        # Exit commission
        if exit_price:
            exit_notional = float(size) * float(exit_price)
            total_commission += exit_notional * taker_fee
            
    initial_capital = 10000.0
    net_pnl = total_pnl - total_commission
    current_capital = initial_capital + net_pnl
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    
    console.print("\n[bold cyan]Calculated Metrics (Database):[/bold cyan]")
    console.print(f"  Initial: ${initial_capital:,.2f}")
    console.print(f"  Gross PnL: ${total_pnl:+,.2f}")
    console.print(f"  Commissions: -${total_commission:,.2f}")
    console.print(f"  Net PnL: ${net_pnl:+,.2f}")
    console.print(f"  Current Balance: ${current_capital:,.2f}")
    console.print(f"  Trades: {total_trades}")
    console.print(f"  Win Rate: {win_rate:.1f}%")
    
    # 2. Update Redis
    manager = StateManager()
    await manager.connect()
    
    # Get old state
    old_state = await manager.get_portfolio_state()
    console.print("\n[bold yellow]Old Redis State:[/bold yellow]")
    console.print(old_state)
    
    # Update
    new_state = {
        "initial_balance": initial_capital,
        "current_balance": current_capital,
        "total_equity": current_capital,  # Assuming no open positions
        "unrealized_pnl": 0.0,
        "realized_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "total_commission": 0.0,
        "max_drawdown": 0.0,  # Placeholder
        "open_positions": 0
    }
    
    await manager.update_portfolio(new_state)
    
    console.print("\n[bold green]✅ Synced Redis State with Database![/bold green]")
    console.print(new_state)
    
    await manager.disconnect()

if __name__ == "__main__":
    asyncio.run(sync_portfolio())
