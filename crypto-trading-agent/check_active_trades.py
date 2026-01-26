#!/usr/bin/env python3
"""
Check for active trades in Redis and PostgreSQL
"""
import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.state_manager import StateManager
from src.utils.config import get_config
from sqlalchemy import create_engine, text
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

async def check_redis_positions():
    """Check Redis for active positions"""
    console.print("\n[bold cyan]Checking Redis for Active Positions...[/bold cyan]\n")
    
    config = get_config()
    state_manager = StateManager()
    
    try:
        await state_manager.connect()
        
        # Get positions from Redis
        positions = await state_manager.get_positions()
        
        if positions:
            console.print(f"[yellow]Found {len(positions)} position(s) in Redis:[/yellow]\n")
            
            table = Table(title="Redis Active Positions", show_header=True)
            table.add_column("Position ID")
            table.add_column("Symbol")
            table.add_column("Side")
            table.add_column("Quantity")
            table.add_column("Entry Price")
            table.add_column("Unrealized P&L")
            
            for pos in positions:
                table.add_row(
                    pos.get('position_id', 'N/A'),
                    pos.get('symbol', 'N/A'),
                    pos.get('positionSide', 'N/A'),
                    pos.get('positionAmt', 'N/A'),
                    f"${float(pos.get('entryPrice', 0)):,.2f}",
                    f"${float(pos.get('unRealizedProfit', 0)):+,.2f}"
                )
            
            console.print(table)
            
            # Print raw data for debugging
            console.print("\n[dim]Raw Redis Data:[/dim]")
            for i, pos in enumerate(positions, 1):
                console.print(f"[dim]{i}. {json.dumps(pos, indent=2)}[/dim]")
        else:
            console.print("[green]✅ No active positions in Redis[/green]")
        
        await state_manager.disconnect()
        return len(positions) if positions else 0
        
    except Exception as e:
        console.print(f"[red]❌ Error checking Redis: {e}[/red]")
        import traceback
        traceback.print_exc()
        return -1

def check_postgres_trades():
    """Check PostgreSQL for active trades"""
    console.print("\n[bold cyan]Checking PostgreSQL for Active Trades...[/bold cyan]\n")
    
    config = get_config()
    
    try:
        engine = create_engine(config.database.postgres_url)
        
        with engine.connect() as conn:
            # Check for trades without exit_time (active trades)
            query = text("""
                SELECT 
                    trade_id,
                    symbol,
                    direction,
                    position_size,
                    entry_price,
                    exit_price,
                    entry_time,
                    exit_time,
                    pnl,
                    status
                FROM trades
                WHERE exit_time IS NULL OR status = 'OPEN'
                ORDER BY entry_time DESC
            """)
            
            result = conn.execute(query)
            active_trades = result.fetchall()
            
            if active_trades:
                console.print(f"[yellow]Found {len(active_trades)} active trade(s) in PostgreSQL:[/yellow]\n")
                
                table = Table(title="PostgreSQL Active Trades", show_header=True)
                table.add_column("Trade ID")
                table.add_column("Symbol")
                table.add_column("Direction")
                table.add_column("Size")
                table.add_column("Entry Price")
                table.add_column("Entry Time")
                table.add_column("Status")
                
                for trade in active_trades:
                    table.add_row(
                        str(trade[0])[:20],  # trade_id
                        str(trade[1]),        # symbol
                        str(trade[2]),        # direction
                        str(trade[3]),        # position_size
                        f"${float(trade[4]):,.2f}",  # entry_price
                        str(trade[6])[:19] if trade[6] else "N/A",  # entry_time
                        str(trade[9]) if trade[9] else "N/A"  # status
                    )
                
                console.print(table)
                
                # Show detailed info
                console.print("\n[dim]Detailed Trade Information:[/dim]")
                for trade in active_trades:
                    console.print(f"[dim]Trade ID: {trade[0]}[/dim]")
                    console.print(f"[dim]  Symbol: {trade[1]} | Direction: {trade[2]}[/dim]")
                    console.print(f"[dim]  Entry: ${trade[4]} | Exit: {trade[5] or 'None'}[/dim]")
                    console.print(f"[dim]  P&L: {trade[8] or 'None'} | Status: {trade[9] or 'None'}[/dim]")
                    console.print()
            else:
                console.print("[green]✅ No active trades in PostgreSQL[/green]")
            
            # Also check total trades count
            count_query = text("SELECT COUNT(*) FROM trades")
            total_count = conn.execute(count_query).scalar()
            console.print(f"\n[dim]Total trades in database: {total_count}[/dim]")
            
            return len(active_trades)
            
    except Exception as e:
        console.print(f"[red]❌ Error checking PostgreSQL: {e}[/red]")
        import traceback
        traceback.print_exc()
        return -1

async def main():
    """Main function"""
    console.print(Panel.fit(
        "[bold green]Active Trades Checker[/bold green]\n"
        "Checking Redis StateManager and PostgreSQL Database"
    ))
    
    # Check Redis
    redis_count = await check_redis_positions()
    
    # Check PostgreSQL
    postgres_count = check_postgres_trades()
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Redis Active Positions: {redis_count if redis_count >= 0 else 'Error'}")
    console.print(f"  PostgreSQL Active Trades: {postgres_count if postgres_count >= 0 else 'Error'}")
    
    if redis_count > 0 or postgres_count > 0:
        console.print("\n[yellow]⚠️ Active trades found! You may want to close them.[/yellow]")
        console.print("\n[bold]To close all active positions, run:[/bold]")
        console.print("[cyan]python close_all_positions.py[/cyan]")
    else:
        console.print("\n[green]✅ No active trades found in either database[/green]")
    
    console.print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
