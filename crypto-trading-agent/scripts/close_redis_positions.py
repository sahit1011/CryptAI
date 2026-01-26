"""
Check and Close Positions in Redis StateManager
This script checks Redis for active positions and closes them
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from core.state_manager import StateManager
from core.message_bus import MessageBus
from utils.config import get_config

async def check_and_close_positions():
    """Check Redis for active positions and close them"""
    
    print("=" * 70)
    print("  CHECK AND CLOSE POSITIONS IN REDIS")
    print("=" * 70)
    print()
    
    config = get_config()
    
    # Initialize StateManager
    state_manager = StateManager()
    await state_manager.connect()
    
    # Initialize MessageBus
    message_bus = MessageBus(redis_url=config.database.redis_url)
    await message_bus.connect()
    
    try:
        # Get positions from Redis
        positions = await state_manager.get_positions()
        
        if not positions or len(positions) == 0:
            print("✅ No active positions found in Redis.")
            return
        
        print(f"📊 Found {len(positions)} active position(s) in Redis:\n")
        
        # Display positions
        for pos in positions:
            symbol = pos.get('symbol', 'N/A')
            side = pos.get('side', 'N/A')
            quantity = pos.get('quantity', 0)
            entry_price = pos.get('entry_price', 0)
            current_price = pos.get('current_price', 0)
            unrealized_pnl = pos.get('unrealized_pnl', 0)
            position_id = pos.get('position_id', 'N/A')
            
            print(f"  Position ID: {position_id}")
            print(f"  Symbol: {symbol}")
            print(f"  Side: {side}")
            print(f"  Quantity: {quantity}")
            print(f"  Entry Price: ${entry_price:.2f}")
            print(f"  Current Price: ${current_price:.2f}")
            print(f"  Unrealized P&L: ${unrealized_pnl:.2f}")
            print("-" * 70)
        
        # Ask for confirmation
        print("\n⚠️  This will clear all positions from Redis.")
        confirmation = input("Do you want to proceed? (yes/no): ").strip().lower()
        
        if confirmation != 'yes':
            print("❌ Operation cancelled.")
            return
        
        print("\n🔄 Closing positions...")
        
        # Remove each position from Redis
        for pos in positions:
            position_id = pos.get('position_id')
            if position_id:
                await state_manager.remove_position(position_id)
                print(f"  ✅ Removed position: {position_id}")
        
        # Update portfolio state
        portfolio = await state_manager.get_portfolio_state()
        if portfolio:
            portfolio['unrealized_pnl'] = 0.0
            portfolio['open_positions'] = 0
            await state_manager.update_portfolio(portfolio)
        
        # Broadcast updates to frontend
        await message_bus.publish('execution_status', {
            'type': 'position_update',
            'payload': []
        })
        
        if portfolio:
            await message_bus.publish('execution_status', {
                'type': 'balance_update',
                'payload': portfolio
            })
        
        # Log activity
        await message_bus.publish('agent_activity', {
            'sender': 'SYSTEM',
            'action': f'Closed {len(positions)} position(s) manually',
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"\n✅ Successfully closed {len(positions)} position(s)!")
        print("📡 Updates broadcasted to frontend")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await state_manager.disconnect()
        await message_bus.disconnect()

if __name__ == "__main__":
    logger.add("logs/close_redis_positions_{time}.log", rotation="1 day")
    
    try:
        asyncio.run(check_and_close_positions())
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
