"""
Check Positions - Write to File
"""
import asyncio
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state_manager import StateManager

async def check_positions():
    state_manager = StateManager()
    await state_manager.connect()
    
    try:
        positions = await state_manager.get_positions()
        
        with open("position_check_result.txt", "w") as f:
            if not positions or len(positions) == 0:
                f.write("NO_POSITIONS\n")
                print("✅ No active positions")
            else:
                f.write(f"FOUND_{len(positions)}_POSITIONS\n")
                for pos in positions:
                    f.write(f"{pos}\n")
                print(f"Found {len(positions)} positions")
    finally:
        await state_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_positions())
