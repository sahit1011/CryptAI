#!/usr/bin/env python3
"""
Check Redis State
Verify what's stored in Redis for portfolio and positions
"""

import asyncio
import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.state_manager import StateManager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

async def check_redis_state():
    """Check current Redis state"""
    
    console.print(Panel.fit(
        "[bold cyan]Checking Redis State[/bold cyan]\n"
        "Verifying portfolio and position data"
    ))
    
    try:
        # Connect to StateManager
        state_manager = StateManager()
        await state_manager.connect()
        console.print("✅ Connected to Redis")
        
        # Check portfolio state
        console.print("\n[bold]Portfolio State:[/bold]")
        portfolio = await state_manager.get_portfolio_state()
        
        if portfolio:
            table = Table(title="Portfolio Data in Redis")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")
            
            for key, value in portfolio.items():
                table.add_row(key, str(value))
            
            console.print(table)
        else:
            console.print("[red]❌ No portfolio data found in Redis![/red]")
            console.print("[yellow]This is why your frontend shows default values.[/yellow]")
        
        # Check positions
        console.print("\n[bold]Positions State:[/bold]")
        positions = await state_manager.get_positions()
        
        if positions:
            console.print(f"[green]✅ Found {len(positions)} positions[/green]")
            for i, pos in enumerate(positions, 1):
                console.print(f"\nPosition {i}:")
                console.print(json.dumps(pos, indent=2))
        else:
            console.print("[yellow]No open positions (this is normal if no trades are active)[/yellow]")
        
        # Check if paper trading engine has published initial state
        console.print("\n[bold]Checking for Initial State Publication:[/bold]")
        
        # Try to get raw Redis keys
        keys = []
        async for key in state_manager.redis.scan_iter("state:*"):
            keys.append(key)
        
        if keys:
            console.print(f"[green]✅ Found {len(keys)} state keys in Redis:[/green]")
            for key in keys[:10]:  # Show first 10
                console.print(f"  - {key}")
        else:
            console.print("[red]❌ No state keys found in Redis![/red]")
            console.print("\n[bold yellow]DIAGNOSIS:[/bold yellow]")
            console.print("  The PaperTradingEngine has NOT published its initial state to Redis.")
            console.print("  This means the backend simulation is not running.")
            console.print("\n[bold cyan]SOLUTION:[/bold cyan]")
            console.print("  1. Start the backend server: python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000")
            console.print("  2. Start the paper trading simulation: python run_paper_trading_simulation.py")
            console.print("  3. The simulation will publish initial state ($10,000) to Redis")
            console.print("  4. Frontend will then receive this data via WebSocket")
        
        await state_manager.disconnect()
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red]")
        console.print(f"  {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_redis_state())
