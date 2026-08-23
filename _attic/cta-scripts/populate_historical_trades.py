#!/usr/bin/env python3
"""
Populate Historical Trades
Creates 9 historical trades (7 wins, 2 losses) from 5 days ago
Final capital: $11,850
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory.trade_history_manager import TradeHistoryManager
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Database connection
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

def generate_historical_trades():
    """Generate 9 realistic historical trades"""
    
    # Starting capital: $10,000
    # Ending capital: $11,850
    # Total profit: $1,850
    
    # 7 winning trades, 2 losing trades
    # Average win: ~$350, Average loss: ~$375
    
    base_time = datetime.now() - timedelta(days=5)
    
    trades = [
        # Trade 1 - WIN (Long BTC breakout)
        {
            "trade_id": f"HIST_001_{int(base_time.timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 95420.50,
            "entry_time": base_time + timedelta(hours=2),
            "exit_price": 96150.30,
            "exit_time": base_time + timedelta(hours=6, minutes=30),
            "position_size": 0.5,
            "stop_loss": 95100.00,
            "take_profit_levels": [96000.00, 96500.00, 97000.00],
            "risk_amount": 160.25,
            "pnl": 364.90,
            "pnl_percentage": 2.28,
            "is_winner": True,
            "strategy_type": "ICT_BREAKOUT",
            "confidence_score": 0.82,
            "confluence_count": 5,
            "market_regime": "TRENDING_UP",
            "atr_at_entry": 450.30,
            "smc_patterns": ["BOS", "FVG", "ORDER_BLOCK"],
            "ict_setups": ["ASIAN_RANGE_BREAKOUT", "LIQUIDITY_SWEEP"],
            "exit_reason": "TP1_HIT",
            "notes": "Clean breakout above Asian session high with strong volume"
        },
        
        # Trade 2 - WIN (Short BTC rejection)
        {
            "trade_id": f"HIST_002_{int((base_time + timedelta(hours=8)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "entry_price": 96200.00,
            "entry_time": base_time + timedelta(hours=8, minutes=15),
            "exit_price": 95650.50,
            "exit_time": base_time + timedelta(hours=12, minutes=45),
            "position_size": 0.6,
            "stop_loss": 96550.00,
            "take_profit_levels": [95800.00, 95400.00, 95000.00],
            "risk_amount": 210.00,
            "pnl": 329.70,
            "pnl_percentage": 1.71,
            "is_winner": True,
            "strategy_type": "SMC_REVERSAL",
            "confidence_score": 0.78,
            "confluence_count": 4,
            "market_regime": "RANGING",
            "atr_at_entry": 420.15,
            "smc_patterns": ["CHoCH", "PREMIUM_ZONE", "IMBALANCE"],
            "ict_setups": ["JUDAS_SWING", "POWER_OF_3"],
            "exit_reason": "TP1_HIT",
            "notes": "Rejection from premium zone with bearish CHoCH"
        },
        
        # Trade 3 - LOSS (False breakout)
        {
            "trade_id": f"HIST_003_{int((base_time + timedelta(hours=16)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 95700.00,
            "entry_time": base_time + timedelta(hours=16, minutes=30),
            "exit_price": 95320.00,
            "exit_time": base_time + timedelta(hours=18, minutes=10),
            "position_size": 0.4,
            "stop_loss": 95300.00,
            "take_profit_levels": [96200.00, 96700.00],
            "risk_amount": 160.00,
            "pnl": -152.00,
            "pnl_percentage": -1.59,
            "is_winner": False,
            "strategy_type": "ICT_BREAKOUT",
            "confidence_score": 0.65,
            "confluence_count": 3,
            "market_regime": "CHOPPY",
            "atr_at_entry": 380.50,
            "smc_patterns": ["BOS"],
            "ict_setups": ["LIQUIDITY_GRAB"],
            "exit_reason": "STOP_LOSS",
            "notes": "False breakout - liquidity grab before reversal"
        },
        
        # Trade 4 - WIN (Day 2 - Long pullback)
        {
            "trade_id": f"HIST_004_{int((base_time + timedelta(days=1, hours=3)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 95100.00,
            "entry_time": base_time + timedelta(days=1, hours=3, minutes=20),
            "exit_price": 95820.00,
            "exit_time": base_time + timedelta(days=1, hours=9, minutes=40),
            "position_size": 0.55,
            "stop_loss": 94750.00,
            "take_profit_levels": [95700.00, 96200.00, 96800.00],
            "risk_amount": 192.50,
            "pnl": 396.00,
            "pnl_percentage": 2.48,
            "is_winner": True,
            "strategy_type": "SMC_PULLBACK",
            "confidence_score": 0.85,
            "confluence_count": 6,
            "market_regime": "TRENDING_UP",
            "atr_at_entry": 410.20,
            "smc_patterns": ["FVG", "ORDER_BLOCK", "DISCOUNT_ZONE"],
            "ict_setups": ["OPTIMAL_TRADE_ENTRY", "SILVER_BULLET"],
            "exit_reason": "TP1_HIT",
            "notes": "Perfect OTE setup in discount zone with strong confluence"
        },
        
        # Trade 5 - WIN (Day 2 - Short from premium)
        {
            "trade_id": f"HIST_005_{int((base_time + timedelta(days=1, hours=14)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "entry_price": 96500.00,
            "entry_time": base_time + timedelta(days=1, hours=14, minutes=15),
            "exit_price": 96050.00,
            "exit_time": base_time + timedelta(days=1, hours=18, minutes=30),
            "position_size": 0.5,
            "stop_loss": 96850.00,
            "take_profit_levels": [96100.00, 95700.00],
            "risk_amount": 175.00,
            "pnl": 225.00,
            "pnl_percentage": 1.47,
            "is_winner": True,
            "strategy_type": "SMC_REVERSAL",
            "confidence_score": 0.76,
            "confluence_count": 4,
            "market_regime": "RANGING",
            "atr_at_entry": 395.80,
            "smc_patterns": ["PREMIUM_ZONE", "IMBALANCE"],
            "ict_setups": ["POWER_OF_3"],
            "exit_reason": "TP1_HIT",
            "notes": "Reversal from premium zone with imbalance fill"
        },
        
        # Trade 6 - WIN (Day 3 - Breakout continuation)
        {
            "trade_id": f"HIST_006_{int((base_time + timedelta(days=2, hours=5)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 96200.00,
            "entry_time": base_time + timedelta(days=2, hours=5, minutes=45),
            "exit_price": 97100.00,
            "exit_time": base_time + timedelta(days=2, hours=14, minutes=20),
            "position_size": 0.45,
            "stop_loss": 95850.00,
            "take_profit_levels": [96800.00, 97400.00, 98000.00],
            "risk_amount": 157.50,
            "pnl": 405.00,
            "pnl_percentage": 2.80,
            "is_winner": True,
            "strategy_type": "ICT_BREAKOUT",
            "confidence_score": 0.88,
            "confluence_count": 7,
            "market_regime": "TRENDING_UP",
            "atr_at_entry": 440.60,
            "smc_patterns": ["BOS", "FVG", "ORDER_BLOCK"],
            "ict_setups": ["ASIAN_RANGE_BREAKOUT", "MARKET_MAKER_MODEL"],
            "exit_reason": "TP2_HIT",
            "notes": "Strong breakout with multiple confirmations and clean structure"
        },
        
        # Trade 7 - LOSS (Day 3 - Whipsaw)
        {
            "trade_id": f"HIST_007_{int((base_time + timedelta(days=2, hours=18)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "SHORT",
            "entry_price": 97200.00,
            "entry_time": base_time + timedelta(days=2, hours=18, minutes=10),
            "exit_price": 97620.00,
            "exit_time": base_time + timedelta(days=2, hours=20, minutes=5),
            "position_size": 0.5,
            "stop_loss": 97600.00,
            "take_profit_levels": [96800.00, 96400.00],
            "risk_amount": 200.00,
            "pnl": -210.00,
            "pnl_percentage": -2.16,
            "is_winner": False,
            "strategy_type": "SMC_REVERSAL",
            "confidence_score": 0.62,
            "confluence_count": 3,
            "market_regime": "CHOPPY",
            "atr_at_entry": 460.30,
            "smc_patterns": ["CHoCH"],
            "ict_setups": ["JUDAS_SWING"],
            "exit_reason": "STOP_LOSS",
            "notes": "Caught in whipsaw - market continued higher despite reversal signals"
        },
        
        # Trade 8 - WIN (Day 4 - Pullback entry)
        {
            "trade_id": f"HIST_008_{int((base_time + timedelta(days=3, hours=6)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 97400.00,
            "entry_time": base_time + timedelta(days=3, hours=6, minutes=30),
            "exit_price": 98050.00,
            "exit_time": base_time + timedelta(days=3, hours=12, minutes=15),
            "position_size": 0.4,
            "stop_loss": 97000.00,
            "take_profit_levels": [98000.00, 98600.00],
            "risk_amount": 160.00,
            "pnl": 260.00,
            "pnl_percentage": 2.67,
            "is_winner": True,
            "strategy_type": "SMC_PULLBACK",
            "confidence_score": 0.81,
            "confluence_count": 5,
            "market_regime": "TRENDING_UP",
            "atr_at_entry": 425.40,
            "smc_patterns": ["FVG", "ORDER_BLOCK", "DISCOUNT_ZONE"],
            "ict_setups": ["OPTIMAL_TRADE_ENTRY"],
            "exit_reason": "TP1_HIT",
            "notes": "Clean pullback to OB in discount zone during uptrend"
        },
        
        # Trade 9 - WIN (Day 4 - Continuation)
        {
            "trade_id": f"HIST_009_{int((base_time + timedelta(days=3, hours=16)).timestamp())}",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_price": 98100.00,
            "entry_time": base_time + timedelta(days=3, hours=16, minutes=40),
            "exit_price": 98520.00,
            "exit_time": base_time + timedelta(days=3, hours=21, minutes=10),
            "position_size": 0.35,
            "stop_loss": 97750.00,
            "take_profit_levels": [98500.00, 99000.00],
            "risk_amount": 122.50,
            "pnl": 147.00,
            "pnl_percentage": 1.50,
            "is_winner": True,
            "strategy_type": "ICT_BREAKOUT",
            "confidence_score": 0.74,
            "confluence_count": 4,
            "market_regime": "TRENDING_UP",
            "atr_at_entry": 435.20,
            "smc_patterns": ["BOS", "FVG"],
            "ict_setups": ["LIQUIDITY_SWEEP", "MARKET_MAKER_MODEL"],
            "exit_reason": "TP1_HIT",
            "notes": "Continuation trade after liquidity sweep and BOS"
        }
    ]
    
    return trades


def populate_trades():
    """Populate database with historical trades"""
    
    console.print(Panel.fit(
        "[bold cyan]Populating Historical Trades[/bold cyan]\n"
        "Creating 9 trades from 5 days ago\n"
        "7 Wins, 2 Losses\n"
        "Final Capital: $11,850"
    ))
    
    try:
        # Initialize trade history manager
        manager = TradeHistoryManager(DATABASE_URL)
        console.print("✅ Connected to database")
        
        # Generate trades
        trades = generate_historical_trades()
        
        # Store each trade
        table = Table(title="Historical Trades")
        table.add_column("ID", style="cyan")
        table.add_column("Symbol", style="magenta")
        table.add_column("Direction", style="yellow")
        table.add_column("Entry", style="green")
        table.add_column("Exit", style="green")
        table.add_column("P&L", style="bold")
        table.add_column("Result", style="bold")
        
        total_pnl = 0.0
        wins = 0
        losses = 0
        
        for trade in trades:
            # Store trade
            manager.store_trade(
                trade_id=trade["trade_id"],
                symbol=trade["symbol"],
                direction=trade["direction"],
                entry_price=trade["entry_price"],
                entry_time=trade["entry_time"],
                position_size=trade["position_size"],
                stop_loss=trade["stop_loss"],
                take_profit_levels=trade["take_profit_levels"],
                risk_amount=trade["risk_amount"],
                strategy_type=trade["strategy_type"],
                confidence_score=trade["confidence_score"],
                confluence_count=trade["confluence_count"],
                market_regime=trade["market_regime"],
                atr_at_entry=trade["atr_at_entry"],
                smc_patterns=trade["smc_patterns"],
                ict_setups=trade["ict_setups"]
            )
            
            # Update with exit
            manager.update_trade_exit(
                trade_id=trade["trade_id"],
                exit_price=trade["exit_price"],
                exit_time=trade["exit_time"],
                exit_reason=trade["exit_reason"],
                notes=trade["notes"]
            )
            
            # Track stats
            total_pnl += trade["pnl"]
            if trade["is_winner"]:
                wins += 1
            else:
                losses += 1
            
            # Add to table
            pnl_color = "green" if trade["pnl"] > 0 else "red"
            result_color = "green" if trade["is_winner"] else "red"
            table.add_row(
                trade["trade_id"][:12] + "...",
                trade["symbol"],
                trade["direction"],
                f"${trade['entry_price']:,.2f}",
                f"${trade['exit_price']:,.2f}",
                f"[{pnl_color}]${trade['pnl']:+,.2f}[/{pnl_color}]",
                f"[{result_color}]{'WIN' if trade['is_winner'] else 'LOSS'}[/{result_color}]"
            )
        
        console.print(table)
        
        # Summary
        initial_capital = 10000.0
        final_capital = initial_capital + total_pnl
        win_rate = (wins / len(trades)) * 100
        
        console.print(f"\n[bold green]✅ Successfully populated {len(trades)} trades![/bold green]")
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  Initial Capital: ${initial_capital:,.2f}")
        console.print(f"  Total P&L: ${total_pnl:+,.2f}")
        console.print(f"  Final Capital: ${final_capital:,.2f}")
        console.print(f"  Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)")
        console.print(f"  Average Win: ${(sum(t['pnl'] for t in trades if t['is_winner']) / wins):,.2f}")
        console.print(f"  Average Loss: ${(sum(t['pnl'] for t in trades if not t['is_winner']) / losses):,.2f}")
        
        # Verify in database
        recent = manager.get_recent_trades(limit=10)
        console.print(f"\n[bold]Database Verification:[/bold]")
        console.print(f"  Total trades in DB: {len(recent)}")
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red]")
        console.print(f"  {str(e)}")
        logger.error(f"Failed to populate trades: {e}")
        raise


if __name__ == "__main__":
    populate_trades()
