"""
Force Clear All Positions from Redis
Directly deletes the positions list from Redis
"""
import asyncio
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.state_manager import StateManager
from core.message_bus import MessageBus
from utils.config import get_config
from datetime import datetime

async def force_clear_positions():
    """Force clear all positions from Redis"""
    
    print("=" * 70)
    print("  FORCE CLEAR ALL POSITIONS FROM REDIS")
    print("=" * 70)
    print()
    
    config = get_config()
    state_manager = StateManager()
    await state_manager.connect()
    
    message_bus = MessageBus(redis_url=config.database.redis_url)
    await message_bus.connect()
    
    try:
        # Get current positions
        positions = await state_manager.get_positions()
        
        if not positions or len(positions) == 0:
            print("✅ No positions to clear")
            return
        
        print(f"📊 Found {len(positions)} position(s) in Redis")
        for i, pos in enumerate(positions, 1):
            print(f"  {i}. {pos.get('symbol', 'Unknown')} {pos.get('positionSide', 'Unknown')}")
        
        print("\n⚠️  This will FORCE DELETE all positions from Redis")
        confirmation = input("Continue? (yes/no): ").strip().lower()
        
        if confirmation != 'yes':
            print("❌ Cancelled")
            return
        
        # Force delete the positions list
        await state_manager.redis.delete("state:positions")
        print("\n✅ Deleted positions list from Redis")
        
        # Update portfolio state
        portfolio = await state_manager.get_portfolio_state()
        if portfolio:
            portfolio['unrealized_pnl'] = 0.0
            portfolio['open_positions'] = 0
            await state_manager.update_portfolio(portfolio)
            print("✅ Updated portfolio state")
        
        # Broadcast updates
        await message_bus.publish('execution_status', {
            'type': 'position_update',
            'payload': []
        })
        
        if portfolio:
            await message_bus.publish('execution_status', {
                'type': 'balance_update',
                'payload': portfolio
            })
        
        await message_bus.publish('agent_activity', {
            'sender': 'SYSTEM',
            'action': f'Force closed {len(positions)} position(s)',
            'timestamp': datetime.now().isoformat()
        })
        
        print("✅ Broadcasted updates to frontend")
        print(f"\n🎉 Successfully cleared {len(positions)} position(s)!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await state_manager.disconnect()
        await message_bus.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(force_clear_positions())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
