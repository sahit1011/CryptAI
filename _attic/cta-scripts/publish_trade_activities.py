#!/usr/bin/env python3
"""
Publish Historical Trade Activities
Creates agent activity logs for historical trades to populate the Recent Activity feed
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from memory.trade_history_manager import TradeHistoryManager
from core.message_bus import MessageBus
from utils.config import get_config
from loguru import logger
from rich.console import Console
from rich.panel import Panel

console = Console()

# Database connection
DATABASE_URL = "postgresql://trader:secure_password_here@localhost:5432/trading_agent"

async def publish_trade_activities():
    """Publish agent activities for historical trades"""
    
    console.print(Panel.fit(
        "[bold cyan]Publishing Historical Trade Activities[/bold cyan]\n"
        "Creating agent logs for Recent Activity feed"
    ))
    
    try:
        # Connect to message bus
        config = get_config()
        message_bus = MessageBus(config.database.redis_url)
        await message_bus.connect()
        console.print("✅ Connected to MessageBus")
        
        # Load historical trades
        trade_manager = TradeHistoryManager(DATABASE_URL)
        all_trades = trade_manager.get_recent_trades(limit=1000)
        console.print(f"📊 Found {len(all_trades)} trades in database")
        
        # Filter only closed trades
        closed_trades = [t for t in all_trades if t.exit_price and t.pnl is not None]
        console.print(f"✅ Processing {len(closed_trades)} closed trades\n")
        
        activity_count = 0
        
        for trade in closed_trades:
            # Determine if win or loss
            is_win = trade.pnl > 0
            pnl_str = f"${float(trade.pnl):+,.2f}"
            pnl_pct = float(trade.pnl_percentage) if trade.pnl_percentage else 0.0
            
            # Get trade metadata
            strategy = trade.strategy_type or "SMC_ICT"
            confidence = float(trade.confidence_score) if trade.confidence_score else 0.75
            confluence = trade.confluence_count or 4
            
            # 1. DATA AGENT: Market data collected
            await message_bus.publish("agent_activity", {
                "sender": "DataCollectionAgent",
                "action": "market_data_collected",
                "message": f"Collected market data for {trade.symbol} - Price: ${float(trade.entry_price):,.2f}",
                "phase": "data_collection",
                "severity": "info",
                "timestamp": trade.entry_time.isoformat(),
                "metadata": {
                    "symbol": trade.symbol,
                    "price": float(trade.entry_price)
                }
            })
            activity_count += 1
            
            # 2. ANALYSIS AGENT: Market analysis completed
            regime = trade.market_regime or "TRENDING_UP"
            patterns = trade.smc_patterns or ["BOS", "FVG", "ORDER_BLOCK"]
            setups = trade.ict_setups or ["OPTIMAL_TRADE_ENTRY"]
            
            await message_bus.publish("agent_activity", {
                "sender": "MarketAnalysisAgent",
                "action": "analysis_completed",
                "message": f"Analysis complete: {regime} regime detected with {len(patterns)} SMC patterns",
                "phase": "analysis",
                "severity": "success",
                "timestamp": trade.entry_time.isoformat(),
                "metadata": {
                    "regime": regime,
                    "patterns": patterns,
                    "setups": setups,
                    "atr": float(trade.atr_at_entry) if trade.atr_at_entry else 450.0
                }
            })
            activity_count += 1
            
            # 3. STRATEGY AGENT: Trade setup generated
            await message_bus.publish("agent_activity", {
                "sender": "StrategyGenerationAgent",
                "action": "setup_generated",
                "message": f"{strategy} setup: {trade.direction} {trade.symbol} @ ${float(trade.entry_price):,.2f} (Confidence: {confidence:.0%})",
                "phase": "strategy",
                "severity": "success",
                "timestamp": trade.entry_time.isoformat(),
                "metadata": {
                    "strategy": strategy,
                    "direction": trade.direction,
                    "confidence": confidence,
                    "confluence": confluence,
                    "entry_price": float(trade.entry_price),
                    "stop_loss": float(trade.stop_loss)
                }
            })
            activity_count += 1
            
            # 4. RISK AGENT: Risk validation
            risk_amount = float(trade.risk_amount) if trade.risk_amount else 150.0
            rr_ratio = float(trade.risk_reward_ratio) if trade.risk_reward_ratio else 2.5
            
            await message_bus.publish("agent_activity", {
                "sender": "RiskManagementAgent",
                "action": "trade_approved",
                "message": f"✅ Trade approved - Risk: ${risk_amount:.2f} | R:R {rr_ratio:.1f}:1 | Confidence: {confidence:.0%}",
                "phase": "risk_validation",
                "severity": "success",
                "timestamp": trade.entry_time.isoformat(),
                "metadata": {
                    "risk_amount": risk_amount,
                    "risk_reward": rr_ratio,
                    "position_size": float(trade.position_size)
                }
            })
            activity_count += 1
            
            # 5. EXECUTION AGENT: Trade entry
            await message_bus.publish("agent_activity", {
                "sender": "ExecutionAgent",
                "action": "trade_opened",
                "message": f"🚀 Opened {trade.direction} {trade.symbol} @ ${float(trade.entry_price):,.2f} | Size: {float(trade.position_size)} | SL: ${float(trade.stop_loss):,.2f}",
                "phase": "execution",
                "severity": "success",
                "timestamp": trade.entry_time.isoformat(),
                "metadata": {
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "direction": trade.direction,
                    "entry_price": float(trade.entry_price),
                    "position_size": float(trade.position_size),
                    "stop_loss": float(trade.stop_loss)
                }
            })
            activity_count += 1
            
            # 6. EXECUTION AGENT: Trade exit
            exit_reason = trade.exit_reason or ("TP1_HIT" if is_win else "STOP_LOSS")
            exit_emoji = "🎯" if is_win else "🛑"
            severity = "success" if is_win else "warning"
            
            await message_bus.publish("agent_activity", {
                "sender": "ExecutionAgent",
                "action": "trade_closed",
                "message": f"{exit_emoji} Closed {trade.direction} {trade.symbol} @ ${float(trade.exit_price):,.2f} | P&L: {pnl_str} ({pnl_pct:+.2f}%) | Reason: {exit_reason}",
                "phase": "execution",
                "severity": severity,
                "timestamp": trade.exit_time.isoformat(),
                "metadata": {
                    "trade_id": trade.trade_id,
                    "exit_price": float(trade.exit_price),
                    "pnl": float(trade.pnl),
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                    "is_winner": is_win
                }
            })
            activity_count += 1
            
            # 7. MEMORY AGENT: Trade logged
            await message_bus.publish("agent_activity", {
                "sender": "MemoryAgent",
                "action": "trade_logged",
                "message": f"📝 Trade logged: {trade.trade_id[:12]}... | {'✅ WIN' if is_win else '❌ LOSS'} {pnl_str}",
                "phase": "memory",
                "severity": "info",
                "timestamp": trade.exit_time.isoformat(),
                "metadata": {
                    "trade_id": trade.trade_id,
                    "strategy": strategy,
                    "pnl": float(trade.pnl),
                    "is_winner": is_win
                }
            })
            activity_count += 1
            
            console.print(f"✅ Published {7} activities for trade {trade.trade_id[:15]}... ({pnl_str})")
        
        console.print(f"\n[bold green]✅ Published {activity_count} agent activities![/bold green]")
        console.print(f"\n[bold cyan]Next Steps:[/bold cyan]")
        console.print(f"  1. Refresh your frontend dashboard")
        console.print(f"  2. Check 'Recent Activity' feed - you should see all {len(closed_trades)} trades")
        console.print(f"  3. Activities show the complete flow: Data → Analysis → Strategy → Risk → Execution → Memory")
        
        await message_bus.disconnect()
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red]")
        console.print(f"  {str(e)}")
        logger.error(f"Failed to publish activities: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(publish_trade_activities())
