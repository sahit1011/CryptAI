#!/usr/bin/env python3
"""
Sync Portfolio State from Historical Trades
Calculates current portfolio based on closed trades in PostgreSQL
and updates Redis state accordingly
"""

import sys
from pathlib import Path
from datetime import datetime
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory.trade_history_manager import TradeHistoryManager
from core.state_manager import StateManager
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Database connection
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

async def sync_portfolio_from_trades():
    """Calculate portfolio from historical trades and update Redis"""
    
    console.print(Panel.fit(
        "[bold cyan]Syncing Portfolio from Historical Trades[/bold cyan]\n"
        "Reading PostgreSQL → Updating Redis"
    ))
    
    try:
        # Connect to trade history manager
        trade_manager = TradeHistoryManager(DATABASE_URL)
        console.print("✅ Connected to PostgreSQL")
        
        # Connect to state manager (Redis)
        state_manager = StateManager()
        await state_manager.connect()
        console.print("✅ Connected to Redis")
        
        # Get all closed trades
        all_trades = trade_manager.get_recent_trades(limit=1000)
        console.print(f"\n📊 Found {len(all_trades)} trades in database")
        
        # Calculate portfolio metrics
        initial_balance = 10000.0
        total_pnl = 0.0
        total_commission = 0.0
        winning_trades = 0
        total_trades = 0
        
        # Create summary table
        table = Table(title="Trade History Summary")
        table.add_column("Trade ID", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Direction", style="yellow")
        table.add_column("Entry", style="green")
        table.add_column("Exit", style="green")
        table.add_column("P&L", style="bold")
        table.add_column("Status", style="bold")
        
        for trade in all_trades:
            # Only count closed trades
            if trade.exit_price and trade.pnl is not None:
                total_trades += 1
                total_pnl += float(trade.pnl)
                
                if trade.pnl > 0:
                    winning_trades += 1
                
                # Estimate commission (0.05% of notional value)
                notional = float(trade.position_size) * float(trade.entry_price)
                commission = notional * 0.0005
                total_commission += commission
                
                # Add to table
                pnl_color = "green" if trade.pnl > 0 else "red"
                table.add_row(
                    trade.trade_id[:15] + "...",
                    trade.symbol,
                    trade.direction,
                    f"${float(trade.entry_price):,.2f}",
                    f"${float(trade.exit_price):,.2f}",
                    f"[{pnl_color}]${float(trade.pnl):+,.2f}[/{pnl_color}]",
                    "✅ WIN" if trade.pnl > 0 else "❌ LOSS"
                )
        
        console.print("\n")
        console.print(table)
        
        # Calculate final metrics
        current_balance = initial_balance + total_pnl - total_commission
        total_equity = current_balance  # No open positions
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        realized_pnl_pct = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0.0
        
        # Calculate peak and drawdown
        peak_balance = current_balance
        max_drawdown = 0.0
        
        # Build portfolio state
        portfolio_state = {
            "initial_balance": initial_balance,
            "current_balance": current_balance,
            "total_equity": total_equity,
            "unrealized_pnl": 0.0,  # No open positions
            "realized_pnl": total_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": win_rate,
            "total_commission": total_commission,
            "peak_balance": peak_balance,
            "max_drawdown": max_drawdown,
            "open_positions": 0,
            "account_balance": current_balance,
            "portfolio_heat": 0.0,
            "daily_pnl": 0.0,
            "current_drawdown": 0.0,
            "circuit_breaker_active": False
        }
        
        # Update Redis
        console.print("\n[bold yellow]Updating Redis...[/bold yellow]")
        await state_manager.update_portfolio(portfolio_state)
        console.print("✅ Portfolio state updated in Redis")
        
        # Display summary
        summary_table = Table(title="[bold green]Updated Portfolio State[/bold green]")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Initial Balance", f"${initial_balance:,.2f}")
        summary_table.add_row("Total P&L", f"${total_pnl:+,.2f}")
        summary_table.add_row("Total Commission", f"${total_commission:,.2f}")
        summary_table.add_row("Current Balance", f"[bold]${current_balance:,.2f}[/bold]")
        summary_table.add_row("Total Equity", f"[bold]${total_equity:,.2f}[/bold]")
        summary_table.add_row("Total Trades", str(total_trades))
        summary_table.add_row("Winning Trades", str(winning_trades))
        summary_table.add_row("Win Rate", f"{win_rate:.1f}%")
        summary_table.add_row("Return", f"{realized_pnl_pct:+.2f}%")
        
        console.print("\n")
        console.print(summary_table)
        
        console.print(f"\n[bold green]✅ Portfolio synced successfully![/bold green]")
        console.print(f"\n[bold cyan]Next Steps:[/bold cyan]")
        console.print(f"  1. Start backend server: python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000")
        console.print(f"  2. Frontend will now show: Portfolio Value: ${total_equity:,.2f}")
        console.print(f"  3. Total P&L: ${total_pnl:+,.2f} ({realized_pnl_pct:+.2f}%)")
        
        await state_manager.disconnect()
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red]")
        console.print(f"  {str(e)}")
        logger.error(f"Failed to sync portfolio: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(sync_portfolio_from_trades())
