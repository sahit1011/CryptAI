
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.state_manager import StateManager
from rich.console import Console

console = Console()

async def check_redis_state():
    manager = StateManager()
    await manager.connect()
    
    portfolio = await manager.get_portfolio_state()
    console.print("\n[bold]Current Redis Portfolio State:[/bold]")
    console.print(portfolio)
    
    await manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_redis_state())
