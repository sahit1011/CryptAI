"""
Check Positions in Redis
Quick script to check if there are any active positions
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state_manager import StateManager

async def check_positions():
    """Check positions in Redis"""
    
    state_manager = StateManager()
    await state_manager.connect()
    
    try:
        positions = await state_manager.get_positions()
        
        if not positions or len(positions) == 0:
            print("✅ No active positions in Redis")
        else:
            print(f"📊 Found {len(positions)} active position(s):")
            for pos in positions:
                print(f"  - {pos.get('symbol')} {pos.get('side')} | P&L: ${pos.get('unrealized_pnl', 0):.2f}")
    finally:
        await state_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_positions())
