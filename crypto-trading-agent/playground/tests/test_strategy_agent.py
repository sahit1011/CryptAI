"""
Isolated Strategy Agent Test
Tests the strategy generation agent with live data using existing infrastructure
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.agents.strategy_agent import StrategyGenerationAgent
from src.agents.analysis_agent import MarketAnalysisAgent
from src.utils.config import get_config
from playground.data.live_data_fetcher import LiveDataFetcher

console = Console()


class StrategyAgentTester:
    """
    Isolated testing for Strategy Generation Agent
    
    Tests strategy agent's ability to:
    - Transform analysis into actionable trade setups
    - Calculate proper entry/SL/TP levels
    - Assess risk-reward ratios
    - Generate execution plans
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize tester with existing infrastructure"""
        self.config = get_config()
        
        # Load test config
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "test_config.yaml"
        
        with open(config_path, 'r') as f:
            self.test_config = yaml.safe_load(f)
        
        # Use REAL infrastructure
        self.message_bus = None
        self.state_manager = None
        self.analysis_agent = None
        self.strategy_agent = None
        
        # Testing components
        self.data_fetcher = LiveDataFetcher(config_path)
        
        # Results
        self.test_results = {}
        
        logger.info("StrategyAgentTester initialized (using real infrastructure)")
    
    async def setup(self):
        """Setup test environment"""
        console.print(Panel("🔧 Setting Up Strategy Agent Test", border_style="cyan"))
        
        try:
            # Connect to live data
            console.print("📡 Connecting to Binance...")
            await self.data_fetcher.connect()
            console.print("[green]✓[/green] Binance connected")
            
            # Connect to MessageBus
            console.print("📨 Connecting to MessageBus (Redis)...")
            self.message_bus = MessageBus(self.config.database.redis_url)
            await self.message_bus.connect()
            console.print("[green]✓[/green] MessageBus connected")
            
            # Connect to StateManager
            console.print("💾 Connecting to StateManager (Redis)...")
            self.state_manager = StateManager()
            await self.state_manager.connect()
            console.print("[green]✓[/green] StateManager connected")
            
            # Initialize analysis agent (needed to generate analysis)
            console.print("🤖 Initializing Analysis Agent...")
            self.analysis_agent = MarketAnalysisAgent(
                self.message_bus,
                self.state_manager
            )
            await self.analysis_agent.start()
            console.print("[green]✓[/green] Analysis Agent started")
            
            # Initialize strategy agent
            console.print("🎯 Initializing Strategy Agent...")
            self.strategy_agent = StrategyGenerationAgent(
                self.message_bus,
                self.state_manager
            )
            await self.strategy_agent.start()
            console.print("[green]✓[/green] Strategy Agent started")
            
            console.print("\n[bold green]✅ Setup Complete![/bold green]\n")
            
        except Exception as e:
            console.print(f"[red]❌ Setup failed: {e}[/red]")
            raise
    
    async def teardown(self):
        """Clean up resources"""
        console.print("\n🧹 Cleaning up...")
        
        if self.strategy_agent:
            await self.strategy_agent.stop()
        
        if self.analysis_agent:
            await self.analysis_agent.stop()
        
        if self.message_bus:
            await self.message_bus.disconnect()
        
        if self.state_manager:
            await self.state_manager.disconnect()
        
        if self.data_fetcher:
            await self.data_fetcher.disconnect()
        
        console.print("[green]✓[/green] Cleanup complete")
    
    async def test_strategy_generation(
        self,
        symbol: str = "BTC/USDT",
        timeframes: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Test strategy agent with live market data
        
        Args:
            symbol: Trading pair to analyze
            timeframes: Timeframes to fetch
        
        Returns:
            Test results
        """
        if timeframes is None:
            timeframes = self.test_config.get('timeframes', ['1d', '4h', '1h', '15m', '5m'])
        
        console.print(Panel(
            f"🎯 Testing Strategy Generation Agent\nSymbol: {symbol}\nTimeframes: {', '.join(timeframes)}",
            border_style="blue"
        ))
        
        start_time = datetime.now()
        
        try:
            # Step 1: Fetch live data
            console.print("\n[bold]Step 1: Fetching Live Market Data[/bold]")
            market_data = await self.data_fetcher.fetch_all_data(symbol, timeframes)
            console.print(f"[green]✓[/green] Fetched {len(market_data['candles'])} timeframes")
            
            # Step 2: Store data in state manager
            console.print("\n[bold]Step 2: Storing Data in StateManager[/bold]")
            await self._store_market_data(symbol, market_data)
            console.print("[green]✓[/green] Data stored")
            
            # Step 3: Run analysis (prerequisite for strategy)
            console.print("\n[bold]Step 3: Running Market Analysis[/bold]")
            analysis_result = await self.analysis_agent.analyze_market(
                symbol=symbol.replace('/', ''),
                candles=market_data['candles'],
                order_book=market_data.get('order_book'),
                funding_rate=market_data.get('funding_rate')
            )
            console.print(f"[green]✓[/green] Analysis complete: {len(analysis_result.get('trade_opportunities', []))} opportunities")
            
            # Step 4: Generate strategy
            console.print("\n[bold]Step 4: Generating Trading Strategy[/bold]")
            strategy_result = await self.strategy_agent.generate_strategy(
                symbol=symbol.replace('/', ''),
                analysis=analysis_result
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Step 5: Evaluate strategy
            console.print("\n[bold]Step 5: Evaluating Strategy Quality[/bold]")
            evaluation = self._evaluate_strategy(strategy_result, analysis_result, elapsed)
            
            self._display_results(strategy_result, evaluation)
            
            # Store test results
            self.test_results = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis_result,
                'strategy': strategy_result,
                'evaluation': evaluation,
                'elapsed_seconds': elapsed
            }
            
            return self.test_results
            
        except Exception as e:
            console.print(f"[red]❌ Test failed: {e}[/red]")
            logger.error(f"Test failed: {e}", exc_info=True)
            raise
    
    async def _store_market_data(self, symbol: str, market_data: Dict[str, Any]):
        """Store market data in state manager"""
        symbol_key = symbol.replace('/', '')
        
        # Store candles
        for tf, candles in market_data['candles'].items():
            key = f"candles_{tf}:{symbol_key}"
            await self.state_manager.set(key, candles)
        
        # Store current price
        if market_data['candles'].get('5m'):
            current_price = market_data['candles']['5m'][-1]['close']
            await self.state_manager.set(f"price:{symbol_key}", current_price)
        
        # Store ATR for risk calculation
        if market_data['candles'].get('1h'):
            candles_1h = market_data['candles']['1h']
            atr = self._calculate_simple_atr(candles_1h)
            await self.state_manager.set(f"atr:{symbol_key}", atr)
        
        # Store account balance (for position sizing)
        await self.state_manager.set("account_balance", 10000.0)
    
    def _calculate_simple_atr(self, candles: list, period: int = 14) -> float:
        """Calculate simple ATR from candles"""
        if len(candles) < period + 1:
            return 150.0  # Default
        
        tr_values = []
        for i in range(1, min(period + 1, len(candles))):
            high_low = candles[i]['high'] - candles[i]['low']
            high_close = abs(candles[i]['high'] - candles[i-1]['close'])
            low_close = abs(candles[i]['low'] - candles[i-1]['close'])
            tr = max(high_low, high_close, low_close)
            tr_values.append(tr)
        
        return sum(tr_values) / len(tr_values) if tr_values else 150.0
    
    def _evaluate_strategy(
        self,
        strategy: Dict[str, Any],
        analysis: Dict[str, Any],
        elapsed: float
    ) -> Dict[str, Any]:
        """Evaluate strategy quality"""
        trade_setup = strategy.get('trade_setup')
        
        evaluation = {
            'performance': {
                'elapsed_seconds': elapsed,
                'target_seconds': 90,  # Analysis + Strategy
                'passed': elapsed < 90
            },
            'strategy_generated': {
                'has_setup': trade_setup is not None,
                'passed': trade_setup is not None
            }
        }
        
        if trade_setup:
            evaluation['quality'] = {
                'has_entry': trade_setup.get('entry_price') is not None,
                'has_stop_loss': trade_setup.get('stop_loss') is not None,
                'has_take_profit': trade_setup.get('take_profit') is not None,
                'risk_reward_ratio': trade_setup.get('risk_reward_ratio', 0),
                'rr_acceptable': trade_setup.get('risk_reward_ratio', 0) >= 2.0,
                'confidence': trade_setup.get('confidence_score', 0),
                'confidence_acceptable': trade_setup.get('confidence_score', 0) >= 0.65
            }
            
            evaluation['quality']['passed'] = (
                evaluation['quality']['has_entry'] and
                evaluation['quality']['has_stop_loss'] and
                evaluation['quality']['has_take_profit'] and
                evaluation['quality']['rr_acceptable'] and
                evaluation['quality']['confidence_acceptable']
            )
        
        evaluation['overall_passed'] = (
            evaluation['performance']['passed'] and
            evaluation['strategy_generated']['passed'] and
            (evaluation.get('quality', {}).get('passed', False) if trade_setup else False)
        )
        
        return evaluation
    
    def _display_results(self, strategy: Dict[str, Any], evaluation: Dict[str, Any]):
        """Display strategy results and evaluation"""
        # Performance table
        perf_table = Table(title="⚡ Performance Metrics", show_header=True)
        perf_table.add_column("Metric", style="cyan")
        perf_table.add_column("Value", style="yellow")
        perf_table.add_column("Status", style="green")
        
        perf = evaluation['performance']
        status = "✓ PASS" if perf['passed'] else "✗ FAIL"
        perf_table.add_row(
            "Total Time",
            f"{perf['elapsed_seconds']:.2f}s / {perf['target_seconds']}s",
            status
        )
        
        console.print("\n")
        console.print(perf_table)
        
        # Strategy details
        trade_setup = strategy.get('trade_setup')
        if trade_setup:
            setup_table = Table(title="📋 Trade Setup Details", show_header=True)
            setup_table.add_column("Parameter", style="cyan")
            setup_table.add_column("Value", style="yellow")
            
            setup_table.add_row("Direction", trade_setup.get('direction', 'N/A'))
            setup_table.add_row("Entry Price", f"${trade_setup.get('entry_price', 0):,.2f}")
            setup_table.add_row("Stop Loss", f"${trade_setup.get('stop_loss', 0):,.2f}")
            setup_table.add_row("Take Profit", f"${trade_setup.get('take_profit', 0):,.2f}")
            setup_table.add_row("Risk/Reward", f"{trade_setup.get('risk_reward_ratio', 0):.2f}:1")
            setup_table.add_row("Confidence", f"{trade_setup.get('confidence_score', 0):.2%}")
            setup_table.add_row("Position Size", f"${trade_setup.get('position_size', 0):,.2f}")
            
            console.print("\n")
            console.print(setup_table)
            
            # Quality evaluation
            if 'quality' in evaluation:
                quality = evaluation['quality']
                quality_status = "✓ PASS" if quality['passed'] else "✗ FAIL"
                
                console.print(f"\n[bold]Strategy Quality: {quality_status}[/bold]")
                console.print(f"  Entry/SL/TP: {'✓' if quality['has_entry'] and quality['has_stop_loss'] and quality['has_take_profit'] else '✗'}")
                console.print(f"  R/R Ratio: {'✓' if quality['rr_acceptable'] else '✗'} ({quality['risk_reward_ratio']:.2f}:1)")
                console.print(f"  Confidence: {'✓' if quality['confidence_acceptable'] else '✗'} ({quality['confidence']:.2%})")
        else:
            reason = strategy.get('reason', 'Unknown')
            console.print(f"\n[yellow]⚠️ No strategy generated: {reason}[/yellow]")


async def main():
    """Main test entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Strategy Generation Agent")
    parser.add_argument('--symbol', default='BTC/USDT', help='Trading symbol')
    parser.add_argument('--timeframes', default='1d,4h,1h,15m,5m', help='Comma-separated timeframes')
    
    args = parser.parse_args()
    
    timeframes = args.timeframes.split(',')
    
    tester = StrategyAgentTester()
    
    try:
        await tester.setup()
        
        results = await tester.test_strategy_generation(
            symbol=args.symbol,
            timeframes=timeframes
        )
        
        console.print("\n[bold green]✅ Test Complete![/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Test Failed: {e}[/bold red]")
        raise
    
    finally:
        await tester.teardown()


if __name__ == "__main__":
    asyncio.run(main())
