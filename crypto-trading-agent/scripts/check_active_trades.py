#!/usr/bin/env python3
"""
Quick script to check for active trades in the database
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory.trade_history_manager import TradeHistoryManager
from src.utils.config import get_config

def main():
    config = get_config()
    trade_manager = TradeHistoryManager(config.database.postgres_url)
    
    # Get all trades
    all_trades = trade_manager.get_recent_trades(limit=100)
    
    # Filter for active trades (no exit_time)
    active_trades = [t for t in all_trades if t.exit_time is None]
    
    print(f"\n{'='*80}")
    print(f"ACTIVE TRADES CHECK")
    print(f"{'='*80}\n")
    
    if not active_trades:
        print("✅ No active trades found in database")
        print("   System is ready to start a new trading cycle.\n")
        return
    
    print(f"⚠️  Found {len(active_trades)} active trade(s):\n")
    
    for trade in active_trades:
        print(f"Trade ID: {trade.trade_id}")
        print(f"  Symbol: {trade.symbol}")
        print(f"  Direction: {trade.direction}")
        print(f"  Entry Price: ${trade.entry_price:,.2f}")
        print(f"  Position Size: {trade.position_size}")
        print(f"  Entry Time: {trade.entry_time}")
        print(f"  Status: ACTIVE (exit_time is NULL)")
        
        # Calculate current P&L if we have current price
        if hasattr(trade, 'pnl') and trade.pnl is not None:
            pnl_color = "🟢" if trade.pnl >= 0 else "🔴"
            print(f"  Current P&L: {pnl_color} ${trade.pnl:,.2f}")
        
        print()
    
    print(f"{'='*80}\n")
    print("💡 The system will monitor these trades and skip new analysis cycles")
    print("   until they are closed.\n")

if __name__ == "__main__":
    main()
