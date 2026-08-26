#!/usr/bin/env python3
"""
Clear Redis positions and verify clean state
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.state_manager import StateManager
from src.utils.config import get_config
from rich.console import Console

console = Console()

async def clear_redis_positions():
    """Clear all positions from Redis"""
    console.print("\n[bold yellow]Clearing Redis Positions...[/bold yellow]\n")
    
    state_manager = StateManager()
    
    try:
        await state_manager.connect()
        
        # Delete positions key
        await state_manager.redis.delete("state:positions")
        console.print("[green]✅ Cleared state:positions from Redis[/green]")
        
        # Verify it's empty
        positions = await state_manager.get_positions()
        
        if positions:
            console.print(f"[red]❌ Still found {len(positions)} positions after clearing![/red]")
        else:
            console.print("[green]✅ Verified: No positions in Redis[/green]")
        
        await state_manager.disconnect()
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(clear_redis_positions())
