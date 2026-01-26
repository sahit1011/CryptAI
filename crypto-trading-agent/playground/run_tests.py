"""
Quick Test Runner for Playground
Run all tests or specific agent tests
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.panel import Panel

console = Console()


async def run_analysis_agent_test():
    """Run market analysis agent test"""
    from playground.tests.test_market_analysis_agent import MarketAnalysisAgentTester
    
    console.print(Panel("🔍 Running Market Analysis Agent Test", border_style="blue"))
    
    tester = MarketAnalysisAgentTester()
    
    try:
        await tester.setup()
        results = await tester.test_live_analysis(symbol='BTC/USDT')
        console.print("\n[bold green]✅ Analysis Agent Test Passed![/bold green]")
        return results
    except Exception as e:
        console.print(f"\n[bold red]❌ Analysis Agent Test Failed: {e}[/bold red]")
        raise
    finally:
        await tester.teardown()


async def run_strategy_agent_test():
    """Run strategy generation agent test"""
    from playground.tests.test_strategy_agent import StrategyAgentTester
    
    console.print(Panel("🎯 Running Strategy Generation Agent Test", border_style="blue"))
    
    tester = StrategyAgentTester()
    
    try:
        await tester.setup()
        results = await tester.test_strategy_generation(symbol='BTC/USDT')
        console.print("\n[bold green]✅ Strategy Agent Test Passed![/bold green]")
        return results
    except Exception as e:
        console.print(f"\n[bold red]❌ Strategy Agent Test Failed: {e}[/bold red]")
        raise
    finally:
        await tester.teardown()


async def run_all_tests():
    """Run all agent tests"""
    console.print(Panel("🚀 Running All Playground Tests", border_style="cyan", padding=(1, 2)))
    
    results = {}
    
    # Test 1: Analysis Agent
    try:
        results['analysis'] = await run_analysis_agent_test()
    except Exception as e:
        console.print(f"[yellow]⚠️ Analysis test failed, continuing...[/yellow]")
        results['analysis'] = {'error': str(e)}
    
    console.print("\n" + "="*80 + "\n")
    
    # Test 2: Strategy Agent
    try:
        results['strategy'] = await run_strategy_agent_test()
    except Exception as e:
        console.print(f"[yellow]⚠️ Strategy test failed, continuing...[/yellow]")
        results['strategy'] = {'error': str(e)}
    
    # Summary
    console.print("\n" + "="*80)
    console.print(Panel("📊 Test Summary", border_style="green"))
    
    analysis_passed = 'error' not in results.get('analysis', {})
    strategy_passed = 'error' not in results.get('strategy', {})
    
    console.print(f"Analysis Agent: {'✓ PASS' if analysis_passed else '✗ FAIL'}")
    console.print(f"Strategy Agent: {'✓ PASS' if strategy_passed else '✗ FAIL'}")
    
    if analysis_passed and strategy_passed:
        console.print("\n[bold green]✅ All Tests Passed![/bold green]")
    else:
        console.print("\n[bold yellow]⚠️ Some Tests Failed[/bold yellow]")
    
    return results


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Playground Tests")
    parser.add_argument(
        '--test',
        choices=['all', 'analysis', 'strategy'],
        default='all',
        help='Which test to run'
    )
    
    args = parser.parse_args()
    
    if args.test == 'analysis':
        await run_analysis_agent_test()
    elif args.test == 'strategy':
        await run_strategy_agent_test()
    else:
        await run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
