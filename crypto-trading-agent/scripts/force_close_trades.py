#!/usr/bin/env python3
"""
Force close all active trades in the database
"""
import sys
from pathlib import Path
from datetime import datetime

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
    print(f"FORCE CLOSE ACTIVE TRADES")
    print(f"{'='*80}\n")
    
    if not active_trades:
        print("✅ No active trades found in database")
        print("   Nothing to close.\n")
        return
    
    print(f"⚠️  Found {len(active_trades)} active trade(s) to close:\n")
    
    for trade in active_trades:
        print(f"Closing Trade ID: {trade.trade_id}")
        print(f"  Symbol: {trade.symbol}")
        print(f"  Direction: {trade.direction}")
        print(f"  Entry Price: ${trade.entry_price:,.2f}")
        
        # Close the trade at entry price (breakeven)
        exit_price = float(trade.entry_price)
        
        # Calculate P&L (should be 0 if closing at entry)
        if trade.direction == "LONG":
            pnl = (exit_price - float(trade.entry_price)) * float(trade.position_size)
        else:  # SHORT
            pnl = (float(trade.entry_price) - exit_price) * float(trade.position_size)
        
        # Update the trade in database
        trade_manager.update_trade(
            trade_id=trade.trade_id,
            exit_price=exit_price,
            exit_time=datetime.now(),
            pnl=pnl,
            exit_reason="Manual Close - System Restart"
        )
        
        print(f"  ✅ Closed at ${exit_price:,.2f} | P&L: ${pnl:,.2f}")
        print()
    
    print(f"{'='*80}\n")
    print(f"✅ Successfully closed {len(active_trades)} trade(s)")
    print("   You can now restart the system.\n")

if __name__ == "__main__":
    main()
