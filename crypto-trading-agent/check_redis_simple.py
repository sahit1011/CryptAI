#!/usr/bin/env python3
"""Simple Redis State Check"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.state_manager import StateManager

async def main():
    sm = StateManager()
    await sm.connect()
    
    print("\n=== PORTFOLIO STATE ===")
    portfolio = await sm.get_portfolio_state()
    if portfolio:
        print(f"✅ Portfolio found:")
        for k, v in portfolio.items():
            print(f"  {k}: {v}")
    else:
        print("❌ NO PORTFOLIO DATA IN REDIS")
        print("\nThis is why frontend shows $0.00")
        print("\nSOLUTION:")
        print("1. The paper trading simulation must be RUNNING")
        print("2. It publishes initial state ($10,000) to Redis")
        print("3. Run: python run_paper_trading_simulation.py")
    
    print("\n=== POSITIONS STATE ===")
    positions = await sm.get_positions()
    if positions:
        print(f"✅ {len(positions)} positions found")
    else:
        print("No open positions (normal if no active trades)")
    
    print("\n=== ALL STATE KEYS ===")
    keys = []
    async for key in sm.redis.scan_iter("state:*"):
        keys.append(key)
    
    if keys:
        print(f"✅ {len(keys)} state keys:")
        for key in keys[:20]:
            print(f"  - {key}")
    else:
        print("❌ NO STATE KEYS - Backend simulation not running!")
    
    await sm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
