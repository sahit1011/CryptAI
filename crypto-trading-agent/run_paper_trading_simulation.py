#!/usr/bin/env python3
"""
Paper Trading Simulation
Full 24-hour simulation with realistic order execution
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
import ccxt.async_support as ccxt

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.core.orchestrator import TradingOrchestrator  # PHASE 4 FIX: Add orchestrator
from src.core.event_coordinator import EventCoordinator  # PHASE 2: Add event coordinator
from src.agents.data_agent import DataCollectionAgent
from src.agents.analysis_agent import MarketAnalysisAgent
from src.agents.strategy_agent import StrategyGenerationAgent
from src.agents.risk_agent import RiskManagementAgent
from src.agents.memory_agent import MemoryAgent
from src.execution.execution_agent import ExecutionAgent
from src.execution.paper_trading_engine import PaperTradingEngine, OrderSide, OrderType
from src.utils.config import get_config
from src.utils.pipeline_logger import PipelineLogger
from src.core.health_monitor import AgentHealthMonitor  # Fix #4: Health Monitor


# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/paper_trading_{time}.log", rotation="1 day", retention="7 days")

plog = PipelineLogger()
console = Console()

class PaperTradingSimulation:
    """Full system simulation with paper trading"""
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        symbol: str = "BTC/USDT",
        cycle_interval: int = 300,  # PHASE 4 FIX: Changed from 180 to 300 (5 minutes)
        max_cycles: int = 288  # 24 hours at 5-minute intervals
    ):
        self.config = get_config()
        self.initial_balance = initial_balance
        self.symbol = symbol
        self.cycle_interval = cycle_interval
        self.max_cycles = max_cycles
        
        # Infrastructure
        self.message_bus = None
        self.state_manager = None
        
        # PHASE 4 FIX: Add orchestrator
        self.orchestrator = None
        
        # PHASE 2: Add event coordinator for hybrid architecture
        self.event_coordinator = None
        self.enable_event_driven = True  # Set to False to disable event-driven system

        # Agents
        self.data_agent = None
        self.analysis_agent = None
        self.strategy_agent = None
        self.risk_agent = None
        self.memory_agent = None
        self.execution_agent = None
        
        # Fix #4: Health Monitor
        self.health_monitor = None

        
        # Paper trading
        self.paper_engine = None
        
        # Simulation state
        self.cycle_count = 0
        self.start_time = datetime.now()
        self.trades_executed = 0
        self.opportunities_found = 0
        
    async def setup(self):
        """Initialize all components"""
        console.print(Panel.fit(
            "[bold cyan]Paper Trading Simulation Setup[/bold cyan]\n"
            f"Initial Balance: ${self.initial_balance:,.2f}\n"
            f"Symbol: {self.symbol}\n"
            f"Cycle Interval: {self.cycle_interval}s\n"
            f"Max Cycles: {self.max_cycles}"
        ))
        
        # Infrastructure
        self.message_bus = MessageBus(self.config.database.redis_url)
        await self.message_bus.connect()
        
        self.state_manager = StateManager()
        await self.state_manager.connect()
        
        # Initialize Paper Trading Engine with MessageBus and StateManager
        self.paper_engine = PaperTradingEngine(
            initial_balance=self.initial_balance,
            message_bus=self.message_bus,
            state_manager=self.state_manager  # CRITICAL FIX: Pass StateManager for state persistence
        )
        
        # CRITICAL FIX: Restore state from historical trades in database
        console.print("[yellow]🔄 Checking for historical trades...[/yellow]")
        await self.paper_engine.restore_from_historical_trades(
            self.config.database.postgres_url
        )
        
        # Publish initial state immediately so frontend displays capital right away
        await self.paper_engine.publish_initial_state()
        perf = self.paper_engine.get_performance_summary()
        console.print(
            f"✅ Paper Trading Engine initialized - "
            f"Balance: ${perf['current_balance']:,.2f} | "
            f"Trades: {perf['total_trades']} | "
            f"Win Rate: {perf['win_rate']:.1f}%"
        )
        
        # Initialize agents
        self.data_agent = DataCollectionAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager
        )
        await self.data_agent.start()
        console.print("✅ Data Agent initialized")
        
        # CRITICAL FIX: Wait for initial data to load before proceeding
        console.print("[yellow]⏳ Waiting for initial market data to load...[/yellow]")
        max_wait = 60  # Maximum 60 seconds
        wait_interval = 2  # Check every 2 seconds
        waited = 0
        
        while waited < max_wait:
            if self.data_agent.initial_data_loaded:
                console.print(f"[green]✅ Initial data loaded after {waited}s[/green]")
                break
            await asyncio.sleep(wait_interval)
            waited += wait_interval
            console.print(f"[yellow]  Still loading... ({waited}s)[/yellow]")
        
        if not self.data_agent.initial_data_loaded:
            console.print(f"[red]⚠️ Warning: Initial data not fully loaded after {max_wait}s, proceeding anyway[/red]")
        
        self.analysis_agent = MarketAnalysisAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager
        )
        await self.analysis_agent.start()
        console.print("✅ Analysis Agent initialized")
        
        self.memory_agent = MemoryAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager
        )
        await self.memory_agent.start()
        console.print("✅ Memory Agent initialized")
        
        self.strategy_agent = StrategyGenerationAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager
        )
        await self.strategy_agent.start()
        console.print("✅ Strategy Agent initialized")
        
        self.risk_agent = RiskManagementAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            initial_balance=self.initial_balance
        )
        await self.risk_agent.start()
        console.print("✅ Risk Agent initialized")
        
        self.execution_agent = ExecutionAgent(
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            paper_trading_engine=self.paper_engine,  # CRITICAL FIX: Pass paper engine
            realtime_trading=False  # CRITICAL FIX: Use paper trading mode
        )
        await self.execution_agent.start()
        console.print("✅ Execution Agent initialized (Paper Trading Mode)")
        
        # CRITICAL FIX: Restore balance from historical trades
        try:
            console.print("\n[bold yellow]Restoring account balance from history...[/bold yellow]")
            stats = await asyncio.to_thread(self.memory_agent.trade_history.calculate_stats)
            if stats and stats.total_pnl != 0:
                restored_balance = self.initial_balance + stats.total_pnl
                self.paper_engine.balance = restored_balance
                console.print(
                    f"✅ Restored Balance: [bold green]${restored_balance:,.2f}[/bold green] "
                    f"(Initial: ${self.initial_balance:,.2f} + P&L: ${stats.total_pnl:+,.2f})"
                )
            else:
                console.print(f"ℹ️ No historical P&L found. Starting with initial balance: ${self.initial_balance:,.2f}")
        except Exception as e:
            console.print(f"[red]❌ Failed to restore balance: {e}[/red]")
        
        # PHASE 4 FIX: Initialize orchestrator for sequential execution
        console.print("\n[bold yellow]Initializing Orchestrator...[/bold yellow]")
        self.orchestrator = TradingOrchestrator(
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            symbol=self.symbol,
            cycle_interval=self.cycle_interval
        )
        console.print("✅ Orchestrator initialized")
        
        # PHASE 2: Initialize EventCoordinator for hybrid event-driven architecture
        if self.enable_event_driven:
            console.print("\n[bold yellow]Initializing Event Coordinator (Phase 2)...[/bold yellow]")
            self.event_coordinator = EventCoordinator(
                message_bus=self.message_bus,
                state_manager=self.state_manager,
                cycle_interval=self.cycle_interval,
                cycle_timeout=300,  # 5 minutes max per cycle
                enabled=True
            )
            await self.event_coordinator.start()
            console.print("✅ Event Coordinator initialized and started")
            console.print("[bold cyan]📊 Hybrid Architecture Active: Sequential + Event-Driven[/bold cyan]")
        
        console.print("\n[bold green]All systems ready! Starting simulation...[/bold green]\n")
        
        # Start continuous P&L updates in background
        self.pnl_update_task = asyncio.create_task(self.continuous_pnl_updates())
        console.print("✅ Continuous P&L updates started (10s interval)")
        
        # Fix #4: Initialize and start Health Monitor
        self.health_monitor = AgentHealthMonitor(
            message_bus=self.message_bus,
            state_manager=self.state_manager
        )
        
        # Register agents for monitoring
        if self.data_agent: self.health_monitor.register_agent("data_agent", self.data_agent)
        if self.analysis_agent: self.health_monitor.register_agent("analysis_agent", self.analysis_agent)
        if self.strategy_agent: self.health_monitor.register_agent("strategy_agent", self.strategy_agent)
        if self.risk_agent: self.health_monitor.register_agent("risk_agent", self.risk_agent)
        if self.memory_agent: self.health_monitor.register_agent("memory_agent", self.memory_agent)
        if self.execution_agent: self.health_monitor.register_agent("execution_agent", self.execution_agent)
        
        await self.health_monitor.start()
        console.print("✅ Agent Health Monitor started")



    
    async def continuous_pnl_updates(self):
        """
        Continuously update position P&L and broadcast to frontend
        Runs every 10 seconds independently of trading cycles
        
        This ensures the dashboard shows real-time P&L updates
        even when no trading cycle is active.
        """
        console.print("[bold cyan]📊 Starting continuous P&L updates (10s interval)[/bold cyan]")
        
        while True:
            try:
                # Get all open positions
                positions = self.paper_engine.get_positions()
                
                if positions:
                    # Update each position with current price
                    for position in positions:
                        symbol = position['symbol']
                        
                        # Get current price from state manager
                        # Try both formats (BTC/USDT and BTCUSDT)
                        current_price = await self.state_manager.get_price(symbol)
                        if not current_price:
                            current_price = await self.state_manager.get_price(symbol.replace("/", ""))
                        
                        if current_price:
                            # Update position P&L
                            await self.paper_engine.update_positions(symbol, float(current_price))
                            
                            # Check if any limit orders should fill
                            await self.paper_engine.check_limit_orders(symbol, float(current_price))
                    
                    # Broadcast updated portfolio to frontend
                    await self.paper_engine.publish_portfolio_update()
                    
                    # Log to feed if significant change or periodically
                    # We'll rely on ExecutionAgent for detailed monitoring logs
                    # This is just a backend heartbeat for P&L
                    logger.debug(f"📊 Updated P&L for {len(positions)} positions")
                
                # Wait 10 seconds before next update
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logger.info("Continuous P&L updates cancelled")
                break
            except Exception as e:
                logger.error(f"Error in continuous P&L updates: {e}")
                await asyncio.sleep(10)  # Continue even on error
    
    async def run_cycle(self, cycle_num: int) -> Dict[str, Any]:
        """
        PHASE 4 FIX: Run a single trading cycle using the orchestrator
        
        The orchestrator now handles the entire sequential pipeline:
        Data → Analysis → Strategy → Risk → Execution → Memory
        
        This ensures no overlapping cycles and proper sequential execution.
        """
        cycle_start = datetime.now()
        console.print(f"\n{'='*80}")
        console.print(f"[bold cyan]Cycle #{cycle_num} - {cycle_start.strftime('%H:%M:%S')}[/bold cyan]")
        console.print(f"{'='*80}\n")
        
        result = {
            "cycle": cycle_num,
            "timestamp": cycle_start,
            "opportunity_found": False,
            "trade_executed": False,
            "error": None
        }
        
        try:
            # CRITICAL CHECK 1: Active positions (MARKET orders filled)
            # If we have an active position, SKIP the trading cycle and just monitor
            active_positions = self.paper_engine.get_positions()
            if active_positions:
                console.print(
                    f"[yellow]⚠️ Active position found ({len(active_positions)}), "
                    f"SKIPPING analysis cycle to monitor trade...[/yellow]"
                )
                
                # Just update P&L and check limits
                symbol_clean = self.symbol.replace('/', '')
                current_price = await self.state_manager.get(f"current_price:{symbol_clean}")
                if current_price:
                    await self.paper_engine.update_positions(symbol_clean, current_price)
                    await self.paper_engine.check_limit_orders(symbol_clean, current_price)
                    await self.paper_engine.publish_portfolio_update()
                    
                return result
            
            # CRITICAL CHECK 2: Pending trades (LIMIT orders unfilled)
            # If we have pending trades, CONTINUE the trading cycle to check for better setups
            pending_trades = self.execution_agent.pending_trades_queue.get_all_pending()
            if pending_trades:
                console.print(
                    f"[cyan]ℹ️ Pending trade found ({len(pending_trades)}), "
                    f"CONTINUING analysis to check for better setups...[/cyan]"
                )
                for pt in pending_trades:
                    console.print(
                        f"   - {pt.symbol} {pt.direction} @ ${pt.entry_price:.2f} "
                        f"(Confidence: {pt.confidence_score:.3f}, Remaining: {pt.time_remaining()}s)"
                    )

            console.print("[bold yellow]🔄 Orchestrator executing sequential trading pipeline...[/bold yellow]\n")
            
            # PHASE 4 FIX: Use orchestrator instead of manual agent calls
            # The orchestrator will:
            # 1. Request data from Data Agent (on-demand)
            # 2. Send to Analysis Agent (with memory context)
            # 3. Send to Strategy Agent
            # 4. Send to Risk Agent
            # 5. Execute if approved
            # 6. Log to Memory Agent
            
            # Start orchestrator cycle (it will handle everything sequentially)
            # PHASE 4 FIX: Explicitly run one cycle
            await self.orchestrator.run_cycle()
            
            console.print("[bold green]✅ Orchestrator cycle completed[/bold green]\n")
            
            # Check if any opportunities were found (from state manager)
            symbol_clean = self.symbol.replace('/', '')
            last_analysis = await self.state_manager.get(f"last_analysis:{symbol_clean}")
            
            if last_analysis and last_analysis.get('trade_opportunities'):
                self.opportunities_found += 1
                result["opportunity_found"] = True
                console.print(f"[bold green]✅ Found {len(last_analysis['trade_opportunities'])} opportunities[/bold green]")
                
                # Check if trade was executed
                last_trade = await self.state_manager.get(f"last_trade:{symbol_clean}")
                if last_trade and last_trade.get('timestamp'):
                    # Check if trade is from this cycle (within last 5 minutes)
                    trade_time = datetime.fromisoformat(last_trade['timestamp'])
                    if (cycle_start - trade_time).total_seconds() < self.cycle_interval:
                        self.trades_executed += 1
                        result["trade_executed"] = True
                        console.print(f"[bold green]🚀 Trade executed: {last_trade.get('direction')}[/bold green]")
            else:
                console.print("[yellow]No high-quality setups found this cycle[/yellow]")
            
            # Update paper trading engine positions
            current_price = await self.state_manager.get(f"current_price:{symbol_clean}")
            if current_price:
                await self.paper_engine.update_positions(symbol_clean, current_price)
                await self.paper_engine.check_limit_orders(symbol_clean, current_price)
                await self.paper_engine.publish_portfolio_update()
            
        except Exception as e:
            logger.error(f"Error in cycle {cycle_num}: {e}")
            result["error"] = str(e)
            console.print(f"[red]❌ Error: {e}[/red]")
        
        # Log cycle completion
        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        console.print(f"\n[bold cyan]Cycle #{cycle_num} complete in {cycle_duration:.1f}s[/bold cyan]")
        
        # PHASE 2: Display event coordinator statistics if enabled
        if self.enable_event_driven and self.event_coordinator:
            stats = await self.event_coordinator.get_statistics()
            if stats.get('total_cycles', 0) > 0:
                console.print(f"\n[bold magenta]Event-Driven Stats:[/bold magenta]")
                console.print(
                    f"  Cycles: {stats.get('total_cycles', 0)} | "
                    f"Completed: {stats.get('completed_cycles', 0)} | "
                    f"Failed: {stats.get('failed_cycles', 0)}"
                )
                perf = stats.get('performance', {})
                console.print(
                    f"  Completion Rate: {stats.get('completion_rate', 0):.1f}% | "
                    f"Avg Time: {perf.get('avg_cycle_time', 0):.1f}s"
                )
        
        return result
    
    def display_performance(self):
        """Display current performance"""
        perf = self.paper_engine.get_performance_summary()
        positions = self.paper_engine.get_positions()
        
        # Create performance table
        table = Table(title="[bold cyan]Paper Trading Performance[/bold cyan]", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Initial Balance", f"${perf['initial_balance']:,.2f}")
        table.add_row("Current Balance", f"${perf['current_balance']:,.2f}")
        table.add_row("Total Equity", f"${perf['total_equity']:,.2f}")
        table.add_row("Realized P&L", f"${perf['realized_pnl']:+,.2f} ({perf['realized_pnl_pct']:+.2f}%)")
        table.add_row("Unrealized P&L", f"${perf['unrealized_pnl']:+,.2f}")
        table.add_row("Total Trades", str(perf['total_trades']))
        table.add_row("Win Rate", f"{perf['win_rate']:.1f}%")
        table.add_row("Total Commission", f"${perf['total_commission']:,.2f}")
        table.add_row("Max Drawdown", f"{perf['max_drawdown']:.2f}%")
        table.add_row("Open Positions", str(perf['open_positions']))
        
        console.print("\n")
        console.print(table)
        
        # Display open positions
        if positions:
            pos_table = Table(title="[bold yellow]Open Positions[/bold yellow]", show_header=True)
            pos_table.add_column("Symbol")
            pos_table.add_column("Side")
            pos_table.add_column("Quantity")
            pos_table.add_column("Entry")
            pos_table.add_column("Current")
            pos_table.add_column("Unrealized P&L")
            
            for pos in positions:
                pnl = float(pos['unRealizedProfit'])
                pnl_color = "green" if pnl >= 0 else "red"
                pos_table.add_row(
                    pos['symbol'],
                    pos['positionSide'],
                    pos['positionAmt'],
                    f"${float(pos['entryPrice']):,.2f}",
                    f"${float(pos['markPrice']):,.2f}",
                    f"[{pnl_color}]${pnl:+,.2f}[/{pnl_color}]"
                )
            
            console.print("\n")
            console.print(pos_table)
    
    async def run_simulation(self):
        """Run full simulation"""
        console.print(Panel.fit(
            "[bold green]Starting 24-Hour Paper Trading Simulation[/bold green]\n"
            f"Cycles: {self.max_cycles} | Interval: {self.cycle_interval}s"
        ))
        
        # CRITICAL FIX: Start continuous P&L update task
        pnl_task = asyncio.create_task(self.continuous_pnl_updates())
        console.print("[bold cyan]✅ Started continuous P&L updates (10s interval)[/bold cyan]\n")
        
        try:
            for cycle in range(1, self.max_cycles + 1):
                self.cycle_count = cycle
                
                # Run cycle
                result = await self.run_cycle(cycle)
                
                # Display performance every 10 cycles
                if cycle % 10 == 0:
                    self.display_performance()
                
                # Wait for next cycle (or skip if this is the last one)
                if cycle < self.max_cycles:
                    await asyncio.sleep(self.cycle_interval)
        finally:
            # Cancel P&L task when simulation ends
            pnl_task.cancel()
            try:
                await pnl_task
            except asyncio.CancelledError:
                pass
        
        # Final performance report
        console.print("\n" + "="*80)
        console.print("[bold cyan]SIMULATION COMPLETE[/bold cyan]")
        console.print("="*80 + "\n")
        
        self.display_performance()
        
        # Summary statistics
        elapsed = datetime.now() - self.start_time
        console.print(f"\n[bold]Simulation Summary:[/bold]")
        console.print(f"  Duration: {elapsed}")
        console.print(f"  Total Cycles: {self.cycle_count}")
        console.print(f"  Opportunities Found: {self.opportunities_found}")
        console.print(f"  Trades Executed: {self.trades_executed}")
        console.print(f"  Opportunity Rate: {self.opportunities_found/self.cycle_count*100:.1f}%")
        console.print(f"  Execution Rate: {self.trades_executed/max(self.opportunities_found,1)*100:.1f}%")
    
    async def cleanup(self):
        """Cleanup resources"""
        # Stop continuous P&L updates
        if hasattr(self, 'pnl_update_task'):
            self.pnl_update_task.cancel()
            try:
                await self.pnl_update_task
            except asyncio.CancelledError:
                pass
            console.print("✅ Continuous P&L updates stopped")
            
        # CRITICAL FIX: Close all positions with verification
        if self.paper_engine:
            console.print("[yellow]🚨 Closing all active positions...[/yellow]")
            result = await self.paper_engine.close_all_positions(reason="System Shutdown")
            
            if result['closed_positions']:
                console.print(f"[green]✅ Closed {len(result['closed_positions'])} position(s)[/green]")
                for pos in result['closed_positions']:
                    console.print(f"   - {pos['symbol']} ({pos['side']}): P&L ${pos['pnl']:+.2f}")
                console.print(f"[bold green]Total P&L: ${result['total_realized_pnl']:+.2f}[/bold green]")
            
            if result['failed_positions']:
                console.print(f"[red]⚠️ Failed to close {len(result['failed_positions'])} position(s)[/red]")
                for pos in result['failed_positions']:
                    console.print(f"   - {pos['symbol']}: {pos['error']}")
            
            if result['errors']:
                console.print(f"[yellow]⚠️ Encountered {len(result['errors'])} error(s) during shutdown[/yellow]")
            
            # CRITICAL FIX: Wait for broadcasts to complete before disconnecting
            console.print("[cyan]⏳ Waiting for final broadcasts to complete...[/cyan]")
            await asyncio.sleep(1.0)  # Give broadcasts time to reach frontend
        
        # PHASE 2: Stop event coordinator first
        if self.event_coordinator:
            await self.event_coordinator.stop()
            console.print("✅ Event Coordinator stopped")
        
        if self.data_agent: await self.data_agent.stop()
        if self.analysis_agent: await self.analysis_agent.stop()
        if self.strategy_agent: await self.strategy_agent.stop()
        if self.risk_agent: await self.risk_agent.stop()
        if self.memory_agent: await self.memory_agent.stop()
        if self.execution_agent: await self.execution_agent.stop()
        
        # Fix #4: Stop Health Monitor
        if self.health_monitor: await self.health_monitor.stop()

        
        if self.message_bus: await self.message_bus.disconnect()
        if self.state_manager: await self.state_manager.disconnect()

async def main():
    """Main entry point"""
    # CRITICAL FIX: Add signal handlers for graceful shutdown
    import signal
    
    simulation = None
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        console.print(f"\n[yellow]⚠️ Received signal {signum}, initiating graceful shutdown...[/yellow]")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Kill command
    
    # PHASE 4 FIX: Updated simulation parameters for 5-minute cycles
    initial_balance = 10000.0
    symbol = "BTC/USDT"
    cycle_interval = 300  # 5 minutes (changed from 180)
    max_cycles = 12  # 12 cycles * 5 mins = 60 mins (1 hour)
    
    simulation = PaperTradingSimulation(
        initial_balance=initial_balance,
        symbol=symbol,
        cycle_interval=cycle_interval,
        max_cycles=max_cycles
    )
    
    try:
        await simulation.setup()
        
        # Run simulation with shutdown monitoring
        simulation_task = asyncio.create_task(simulation.run_simulation())
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        # Wait for either simulation to complete or shutdown signal
        done, pending = await asyncio.wait(
            [simulation_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if shutdown_event.is_set():
            console.print("[yellow]Shutdown signal received, cleaning up...[/yellow]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Simulation interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Simulation error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
    finally:
        if simulation:
            await simulation.cleanup()
        console.print("\n[bold green]Simulation ended. Goodbye![/bold green]")

if __name__ == "__main__":
    asyncio.run(main())

