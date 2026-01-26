"""
Close Active Position Script
Closes the currently active position in the paper trading engine
"""
import sys
from pathlib import Path
from datetime import datetime
import asyncio
from loguru import logger

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import after adding to path
import importlib.util

# Load PaperTradingEngine
spec = importlib.util.spec_from_file_location(
    "paper_trading_engine",
    src_path / "execution" / "paper_trading_engine.py"
)
paper_trading_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper_trading_module)
PaperTradingEngine = paper_trading_module.PaperTradingEngine
OrderSide = paper_trading_module.OrderSide

# Load TradeHistoryManager
spec2 = importlib.util.spec_from_file_location(
    "trade_history_manager",
    src_path / "memory" / "trade_history_manager.py"
)
trade_history_module = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(trade_history_module)
TradeHistoryManager = trade_history_module.TradeHistoryManager

# Database configuration
DATABASE_URL = "sqlite:///trading_data.db"

def close_active_position():
    """Close the active position in the paper trading engine"""
    
    print("=" * 70)
    print("  CLOSE ACTIVE POSITION")
    print("=" * 70)
    
    # Initialize paper trading engine
    engine = PaperTradingEngine(initial_balance=10000.0)
    
    # Restore state from database
    print("\n📊 Restoring portfolio state from database...")
    try:
        engine.restore_from_historical_trades(DATABASE_URL)
    except Exception as e:
        logger.warning(f"Could not restore from historical trades: {e}")
    
    # Get current positions
    positions = engine.get_positions()
    
    if not positions:
        print("\n✅ No active positions found.")
        return
    
    print(f"\n📈 Found {len(positions)} active position(s):\n")
    
    # Display positions
    for pos in positions:
        symbol = pos.get('symbol', 'N/A')
        side = pos.get('side', 'N/A')
        quantity = pos.get('quantity', 0)
        entry_price = pos.get('entry_price', 0)
        current_price = pos.get('current_price', 0)
        unrealized_pnl = pos.get('unrealized_pnl', 0)
        
        print(f"  Symbol: {symbol}")
        print(f"  Side: {side}")
        print(f"  Quantity: {quantity}")
        print(f"  Entry Price: ${entry_price:.2f}")
        print(f"  Current Price: ${current_price:.2f}")
        print(f"  Unrealized P&L: ${unrealized_pnl:.2f}")
        print("-" * 70)
    
    # Ask for confirmation
    print("\n⚠️  This will close ALL active positions at current market price.")
    confirmation = input("Do you want to proceed? (yes/no): ").strip().lower()
    
    if confirmation != 'yes':
        print("❌ Operation cancelled.")
        return
    
    # Close all positions
    print("\n🔄 Closing positions...")
    
    try:
        result = engine.close_all_positions(reason="Manual close via script")
        
        if result.get('success'):
            closed_positions = result.get('closed_positions', [])
            total_pnl = result.get('total_realized_pnl', 0)
            
            print(f"\n✅ Successfully closed {len(closed_positions)} position(s)!")
            print(f"💰 Total Realized P&L: ${total_pnl:.2f}")
            
            # Display closed positions
            for pos in closed_positions:
                print(f"\n  Closed: {pos.get('symbol')}")
                print(f"  Side: {pos.get('side')}")
                print(f"  Exit Price: ${pos.get('exit_price', 0):.2f}")
                print(f"  Realized P&L: ${pos.get('realized_pnl', 0):.2f}")
            
            # Now update the database
            print("\n📝 Updating trade history in database...")
            trade_manager = TradeHistoryManager(DATABASE_URL)
            
            for pos in closed_positions:
                symbol = pos.get('symbol')
                exit_price = pos.get('exit_price')
                
                # Find the corresponding trade in database
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                
                engine_db = create_engine(DATABASE_URL)
                SessionLocal = sessionmaker(bind=engine_db)
                session = SessionLocal()
                
                try:
                    TradeRecord = trade_history_module.TradeRecord
                    
                    # Find active trade for this symbol
                    active_trade = session.query(TradeRecord).filter(
                        TradeRecord.symbol == symbol,
                        TradeRecord.exit_time.is_(None)
                    ).first()
                    
                    if active_trade:
                        # Update with exit details
                        trade_manager.update_trade_exit(
                            trade_id=active_trade.trade_id,
                            exit_price=exit_price,
                            exit_time=datetime.now(),
                            exit_reason="manual_close",
                            notes="Closed manually via close_active_position.py script"
                        )
                        print(f"  ✅ Updated trade {active_trade.trade_id} in database")
                    else:
                        print(f"  ⚠️  No active trade found in database for {symbol}")
                        
                except Exception as e:
                    logger.error(f"Error updating database: {e}")
                    print(f"  ❌ Error updating database: {e}")
                finally:
                    session.close()
            
            print("\n✅ All positions closed successfully!")
            
        else:
            error = result.get('error', 'Unknown error')
            print(f"\n❌ Failed to close positions: {error}")
            
    except Exception as e:
        logger.error(f"Error closing positions: {e}")
        print(f"\n❌ Error: {e}")
        raise

if __name__ == "__main__":
    logger.add("logs/close_position_{time}.log", rotation="1 day")
    
    try:
        close_active_position()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
