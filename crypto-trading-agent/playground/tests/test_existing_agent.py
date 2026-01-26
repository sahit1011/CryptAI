"""
Simple Market Analysis Agent Test
Tests the existing analysis agent with live data
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.panel import Panel

console = Console()


async def test_existing_agent():
    """Test the existing market analysis agent"""
    try:
        from src.core.message_bus import MessageBus
        from src.core.state_manager import StateManager
        from src.agents.analysis_agent import MarketAnalysisAgent
        from src.utils.config import get_config
        from playground.data.live_data_fetcher import LiveDataFetcher
        
        console.print(Panel("🔍 Testing Existing Market Analysis Agent", border_style="blue"))
        
        # Get config
        config = get_config()
        
        # Setup infrastructure
        console.print("📨 Connecting to MessageBus...")
        message_bus = MessageBus(config.database.redis_url)
        await message_bus.connect()
        
        console.print("💾 Connecting to StateManager...")
        state_manager = StateManager()
        await state_manager.connect()
        
        # Initialize analysis agent
        console.print("🤖 Initializing Analysis Agent...")
        analysis_agent = MarketAnalysisAgent(message_bus, state_manager)
        await analysis_agent.start()
        
        # Fetch live data
        console.print("📡 Fetching live BTC data from Binance...")
        data_fetcher = LiveDataFetcher()
        await data_fetcher.connect()
        
        market_data = await data_fetcher.fetch_all_data('BTC/USDT', ['1d', '4h', '1h', '15m', '5m'])
        
        console.print(f"[green]✓[/green] Fetched {len(market_data['candles'])} timeframes")
        
        # Store data in state manager
        console.print("💾 Storing data in StateManager...")
        for tf, candles in market_data['candles'].items():
            key = f"candles_{tf}:BTCUSDT"
            await state_manager.set(key, candles)
        
        # Run analysis
        console.print("\n[bold]Running Market Analysis...[/bold]")
        
        result = await analysis_agent.analyze_market(
            symbol='BTCUSDT',
            candles=market_data['candles'],
            order_book=market_data.get('order_book'),
            funding_rate=market_data.get('funding_rate')
        )
        
        # Display results
        console.print("\n[bold green]✅ Analysis Complete![/bold green]")
        console.print(f"\nProvider: {result.get('llm_provider', 'unknown')}")
        console.print(f"Analysis Time: {result.get('analysis_time', 0):.2f}s")
        
        # Show opportunities
        opportunities = result.get('trade_opportunities', [])
        console.print(f"\n[bold]Trade Opportunities: {len(opportunities)}[/bold]")
        
        for i, opp in enumerate(opportunities[:3], 1):
            console.print(f"\n{i}. {opp.get('direction', 'N/A')} - {opp.get('type', 'N/A')}")
            console.print(f"   Confidence: {opp.get('confidence', 0):.1%}")
            console.print(f"   Entry: ${opp.get('entry_price', 0):,.2f}")
        
        # Cleanup
        await data_fetcher.disconnect()
        await analysis_agent.stop()
        await message_bus.disconnect()
        await state_manager.disconnect()
        
        console.print("\n[bold green]✅ Test Complete![/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Test Failed: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_existing_agent())
