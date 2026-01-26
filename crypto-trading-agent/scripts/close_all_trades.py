"""
Close All Active Trades Script
Closes all active trades in the database and updates their status
"""
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import after adding to path
import importlib.util
spec = importlib.util.spec_from_file_location(
    "trade_history_manager",
    src_path / "memory" / "trade_history_manager.py"
)
trade_history_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trade_history_module)
TradeRecord = trade_history_module.TradeRecord

# Database configuration
DATABASE_URL = "sqlite:///trading_data.db"

def close_all_active_trades():
    """Close all active trades in the database"""
    
    # Create database connection
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # Find all active trades (trades without exit_time)
        active_trades = session.query(TradeRecord).filter(
            TradeRecord.exit_time.is_(None)
        ).all()
        
        if not active_trades:
            logger.info("No active trades found in the database.")
            print("✅ No active trades to close.")
            return
        
        logger.info(f"Found {len(active_trades)} active trade(s) to close")
        print(f"\n📊 Found {len(active_trades)} active trade(s):\n")
        
        # Display active trades
        for trade in active_trades:
            print(f"  Trade ID: {trade.trade_id}")
            print(f"  Symbol: {trade.symbol}")
            print(f"  Direction: {trade.direction}")
            print(f"  Entry Price: ${trade.entry_price:.2f}")
            print(f"  Entry Time: {trade.entry_time}")
            print(f"  Position Size: {trade.position_size}")
            print(f"  Stop Loss: ${trade.stop_loss:.2f}")
            print("-" * 50)
        
        # Ask for confirmation
        print("\n⚠️  This will close all active trades at their current market price.")
        confirmation = input("Do you want to proceed? (yes/no): ").strip().lower()
        
        if confirmation != 'yes':
            print("❌ Operation cancelled.")
            return
        
        # Close each trade
        current_time = datetime.now()
        closed_count = 0
        
        for trade in active_trades:
            try:
                # Use stop loss as exit price (you can modify this to use current market price)
                # For now, we'll use the stop loss price as a conservative exit
                exit_price = trade.stop_loss
                
                # Update trade with exit details
                trade.exit_price = exit_price
                trade.exit_time = current_time
                trade.exit_reason = "manual_close"
                
                # Calculate P&L
                if trade.direction == 'LONG':
                    trade.pnl = (exit_price - trade.entry_price) * trade.position_size
                else:
                    trade.pnl = (trade.entry_price - exit_price) * trade.position_size
                
                trade.pnl_percentage = (trade.pnl / (trade.entry_price * trade.position_size)) * 100
                
                # Calculate actual RR ratio
                if trade.risk_amount > 0:
                    if trade.pnl > 0:
                        trade.risk_reward_ratio = abs(trade.pnl) / trade.risk_amount
                    else:
                        trade.risk_reward_ratio = -(abs(trade.pnl) / trade.risk_amount)
                else:
                    trade.risk_reward_ratio = 0.0
                
                # Duration
                trade.duration_minutes = (current_time - trade.entry_time).total_seconds() / 60
                
                # Winner/loser
                trade.is_winner = trade.pnl > 0
                
                # Add note
                trade.notes = "Manually closed via close_all_trades.py script"
                
                closed_count += 1
                
                logger.info(
                    f"Closed trade {trade.trade_id}: "
                    f"P&L: ${trade.pnl:.2f} ({trade.pnl_percentage:.2f}%)"
                )
                
                print(f"\n✅ Closed {trade.trade_id}:")
                print(f"   Exit Price: ${exit_price:.2f}")
                print(f"   P&L: ${trade.pnl:.2f} ({trade.pnl_percentage:.2f}%)")
                print(f"   Duration: {trade.duration_minutes:.1f} minutes")
                
            except Exception as e:
                logger.error(f"Failed to close trade {trade.trade_id}: {e}")
                print(f"❌ Error closing {trade.trade_id}: {e}")
        
        # Commit all changes
        session.commit()
        
        print(f"\n✅ Successfully closed {closed_count} trade(s)!")
        logger.info(f"Successfully closed {closed_count} active trades")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error closing trades: {e}")
        print(f"\n❌ Error: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    logger.add("logs/close_trades_{time}.log", rotation="1 day")
    
    print("=" * 50)
    print("  CLOSE ALL ACTIVE TRADES")
    print("=" * 50)
    
    try:
        close_all_active_trades()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
