#!/usr/bin/env python3
"""
Real-Time BTC Analysis Testing Script
Fetches live BTC data, runs complete analysis pipeline, displays results
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
import ccxt.async_support as ccxt

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.agents.analysis_agent import MarketAnalysisAgent
from src.agents.strategy_agent import StrategyGenerationAgent
from src.utils.config import get_config
from src.utils.enhanced_logging import (
    LoggingConfig, PhaseLogger, StepLogger, MetricsLogger
)
from src.utils.pipeline_logger import PipelineLogger

# Initialize enhanced logging system
LoggingConfig.setup_logging(
    level="INFO",
    log_file="logs/test_realtime_analysis.log"
)

plog = PipelineLogger()

console = Console(legacy_windows=True)


class RealtimeBTCAnalysisTester:
    """Real-time BTC analysis tester with live data fetching"""

    def __init__(self):
        self.config = get_config()
        self.exchange = None
        self.message_bus = None
        self.state_manager = None
        self.analysis_agent = None
        self.strategy_agent = None
        
    async def setup(self):
        """Initialize all components with enhanced logging"""
        async with PhaseLogger("setup", "System Initialization", agent="system"):
            
            # Step 1.1: Exchange connection
            step = StepLogger("1.1", "Connecting to Binance Exchange", agent="system")
            step.start()
            
            try:
                plog.debug("Initializing Binance futures exchange", agent="system", phase="setup")
                self.exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}
                })
                plog.debug("Binance exchange object created, loading markets...", agent="system", phase="setup")
                await self.exchange.load_markets()
                
                step.complete(
                    success=True,
                    details=f"Connected to Binance - {len(self.exchange.markets)} markets loaded",
                    metrics={'markets_loaded': len(self.exchange.markets)}
                )
                plog.success(
                    f"Exchange initialized: {len(self.exchange.markets)} markets available",
                    agent="system"
                )
            except ccxt.NetworkError as e:
                plog.error(f"Binance Network Error (check internet/firewall): {type(e).__name__}: {str(e)[:500]}", exception=e, agent="system")
                step.complete(success=False, details=f"Network error: {str(e)[:100]}")
                raise
            except ccxt.RateLimitError as e:
                plog.error(f"Binance Rate Limited: {str(e)[:500]}", exception=e, agent="system")
                step.complete(success=False, details="Rate limited by Binance API")
                raise
            except ccxt.ExchangeError as e:
                plog.error(f"Binance Exchange Error: {type(e).__name__}: {str(e)[:500]}", exception=e, agent="system")
                step.complete(success=False, details=f"Exchange error: {str(e)[:100]}")
                raise
            except Exception as e:
                plog.error(f"Exchange initialization failed - {type(e).__name__}: {str(e)[:500]}", exception=e, agent="system")
                step.complete(success=False, details=f"{type(e).__name__}: {str(e)[:100]}")
                raise
            
            # Step 1.2: Message bus
            step = StepLogger("1.2", "Initializing Message Bus (Redis)", agent="system")
            step.start()
            
            try:
                plog.debug("Connecting to Redis message bus", agent="system", phase="setup")
                self.message_bus = MessageBus(self.config.database.redis_url)
                await self.message_bus.connect()
                
                step.complete(success=True, details="Message bus connected and ready")
                plog.success("Message bus initialized", agent="system")
            except Exception as e:
                plog.error(f"Message bus initialization failed: {e}", exception=e, agent="system")
                step.complete(success=False, details=str(e))
                raise
            
            # Step 1.3: State manager
            step = StepLogger("1.3", "Initializing State Manager", agent="system")
            step.start()
            
            try:
                plog.debug("Connecting state manager", agent="system", phase="setup")
                self.state_manager = StateManager()
                await self.state_manager.connect()
                
                step.complete(success=True, details="State manager connected")
                plog.success("State manager initialized", agent="system")
            except Exception as e:
                plog.error(f"State manager initialization failed: {e}", exception=e, agent="system")
                step.complete(success=False, details=str(e))
                raise
            
            # Step 1.4: Analysis agent
            step = StepLogger("1.4", "Initializing Analysis Agent (Claude Sonnet 4.5)", agent="system")
            step.start()
            
            try:
                plog.debug("Starting MarketAnalysisAgent", agent="system", phase="setup")
                self.analysis_agent = MarketAnalysisAgent(
                    self.message_bus,
                    self.state_manager
                )
                await self.analysis_agent.start()
                
                step.complete(
                    success=True,
                    details="Analysis agent started with Claude Sonnet 4.5 LLM",
                    metrics={'llm_model': 'claude-sonnet-4.5'}
                )
                plog.success("Analysis agent initialized", agent="system")
            except Exception as e:
                plog.error(f"Analysis agent initialization failed: {e}", exception=e, agent="system")
                step.complete(success=False, details=str(e))
                raise
            
            # Step 1.5: Strategy agent
            step = StepLogger("1.5", "Initializing Strategy Agent (GPT-4o)", agent="system")
            step.start()
            
            try:
                plog.debug("Starting StrategyGenerationAgent", agent="system", phase="setup")
                self.strategy_agent = StrategyGenerationAgent(
                    self.message_bus,
                    self.state_manager
                )
                await self.strategy_agent.start()
                
                step.complete(
                    success=True,
                    details="Strategy agent started with GPT-4o LLM",
                    metrics={'llm_model': 'gpt-4o'}
                )
                plog.success("Strategy agent initialized", agent="system")
            except Exception as e:
                plog.error(f"Strategy agent initialization failed: {e}", exception=e, agent="system")
                step.complete(success=False, details=str(e))
                raise
            
            # Log final metrics
            MetricsLogger.log_metrics(
                "System Setup Complete",
                {
                    'Exchange Markets': len(self.exchange.markets),
                    'Message Bus': "Redis Connected",
                    'State Manager': "Connected",
                    'Analysis Agent': "Running (Claude Sonnet 4.5)",
                    'Strategy Agent': "Running (GPT-4o)",
                    'Components': 5
                },
                phase='setup',
                agent='system'
            )
            
            plog.success(
                "System initialization complete - all 5 components ready",
                agent="system"
            )

    async def teardown(self):
        """Clean up all components with enhanced logging"""
        async with PhaseLogger("teardown", "System Cleanup", agent="system"):
            
            step = StepLogger("6.1", "Stopping agents and services", agent="system")
            step.start()
            
            try:
                plog.debug("Stopping strategy agent", agent="system", phase="teardown")
                if self.strategy_agent:
                    await self.strategy_agent.stop()
                
                plog.debug("Stopping analysis agent", agent="system", phase="teardown")
                if self.analysis_agent:
                    await self.analysis_agent.stop()
                
                plog.debug("Closing exchange connection", agent="system", phase="teardown")
                if self.exchange:
                    await self.exchange.close()
                
                plog.debug("Disconnecting message bus", agent="system", phase="teardown")
                if self.message_bus:
                    await self.message_bus.disconnect()
                
                plog.debug("Disconnecting state manager", agent="system", phase="teardown")
                if self.state_manager:
                    await self.state_manager.disconnect()
                
                step.complete(success=True, details="All components stopped and disconnected")
                plog.success("System cleanup complete", agent="system")
            except Exception as e:
                plog.error(f"Cleanup error: {e}", exception=e, agent="system")
                step.complete(success=False, details=str(e))

    async def fetch_realtime_candles(
        self,
        symbol: str = "BTC/USDT",
        timeframes: List[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        Fetch real-time candle data from Binance with enhanced logging

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframes: List of timeframes to fetch (e.g., ['1d', '4h', '1h', '15m', '5m'])

        Returns:
            Dictionary with timeframe -> candle list
        """
        if timeframes is None:
            timeframes = ['1d', '4h', '1h', '15m', '5m']
        
        async with PhaseLogger("data_collection", f"Fetching Live Candle Data for {symbol}", agent="data_agent"):
            
            plog.debug(f"Fetching {len(timeframes)} timeframes: {', '.join(timeframes)}", 
                      agent="data_agent", phase="data_collection")
            
            candles_data = {}
            total_candles = 0
            successful_fetches = 0

            for i, tf in enumerate(timeframes, 1):
                step = StepLogger(f"2.{i}", f"Fetching {tf} candles (100 bars)", agent="data_agent")
                step.start()
                
                try:
                    plog.debug(f"Fetching OHLCV data for {symbol} {tf}", agent="data_agent")
                    
                    # Fetch OHLCV data
                    ohlcv = await self.exchange.fetch_ohlcv(
                        symbol=symbol,
                        timeframe=tf,
                        limit=100
                    )

                    # Convert to our format
                    candles = []
                    for candle in ohlcv:
                        candles.append({
                            'timestamp': datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': float(candle[5])
                        })

                    candles_data[tf] = candles
                    successful_fetches += 1
                    total_candles += len(candles)

                    # Calculate price change
                    if candles:
                        first = candles[0]
                        last = candles[-1]
                        price_change = ((last['close'] - first['close']) / first['close']) * 100
                        
                        step.complete(
                            success=True,
                            details=f"Fetched 100 candles for {tf} - Price move: {price_change:+.2f}%",
                            metrics={
                                'candles_count': len(candles),
                                'start_price': first['close'],
                                'end_price': last['close'],
                                'price_change_percent': price_change
                            }
                        )
                        
                        plog.debug(
                            f"{tf} data ready: {len(candles)} candles from ${first['close']:,.2f} to ${last['close']:,.2f}",
                            agent="data_agent"
                        )

                except Exception as e:
                    plog.error(f"Failed to fetch {tf} candles: {e}", exception=e, agent="data_agent")
                    step.complete(success=False, details=str(e))
                    candles_data[tf] = []
            
            # Log final metrics
            MetricsLogger.log_metrics(
                "Candle Data Collection",
                {
                    'Symbol': symbol,
                    'Timeframes Requested': len(timeframes),
                    'Timeframes Successful': successful_fetches,
                    'Total Candles': total_candles,
                    'Average per TF': f"{total_candles // successful_fetches if successful_fetches > 0 else 0}"
                },
                phase='data_collection',
                agent='data_agent'
            )
            
            if successful_fetches == len(timeframes):
                plog.success(
                    f"All {len(timeframes)} timeframes fetched successfully - {total_candles} total candles",
                    agent="data_agent"
                )
            else:
                plog.warning(
                    f"Partial data collection: {successful_fetches}/{len(timeframes)} timeframes successful",
                    agent="data_agent"
                )

        return candles_data

    async def fetch_additional_data(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """Fetch additional market data (order book, funding rate) with enhanced logging"""
        async with PhaseLogger("data_collection", f"Fetching Additional Data for {symbol}", agent="data_agent"):
            
            additional_data = {}
            successful_fetches = 0

            # Step 2.1: Order book
            step = StepLogger("2.1", "Fetching Order Book (Top 10 Bids/Asks)", agent="data_agent")
            step.start()
            
            try:
                plog.debug(f"Fetching order book for {symbol}", agent="data_agent")
                order_book = await self.exchange.fetch_order_book(symbol, limit=20)
                additional_data['order_book'] = {
                    'bids': order_book['bids'][:10],
                    'asks': order_book['asks'][:10],
                    'timestamp': datetime.now(timezone.utc)
                }

                successful_fetches += 1
                bid_price = additional_data['order_book']['bids'][0][0] if additional_data['order_book']['bids'] else 0
                ask_price = additional_data['order_book']['asks'][0][0] if additional_data['order_book']['asks'] else 0
                spread = ask_price - bid_price if bid_price > 0 else 0

                step.complete(
                    success=True,
                    details=f"Order book ready - Bid: ${bid_price:,.2f} | Ask: ${ask_price:,.2f} | Spread: ${spread:,.4f}",
                    metrics={
                        'bids': len(additional_data['order_book']['bids']),
                        'asks': len(additional_data['order_book']['asks']),
                        'bid_price': bid_price,
                        'ask_price': ask_price
                    }
                )
                plog.debug(f"Order book loaded: {len(additional_data['order_book']['bids'])} bids, {len(additional_data['order_book']['asks'])} asks", agent="data_agent")

            except Exception as e:
                plog.warning(f"Failed to fetch order book: {e}", agent="data_agent")
                step.complete(success=False, details=str(e))
                additional_data['order_book'] = None

            # Step 2.2: Funding rate
            step = StepLogger("2.2", "Fetching Funding Rate (Futures)", agent="data_agent")
            step.start()
            
            try:
                plog.debug(f"Fetching funding rate for {symbol}", agent="data_agent")
                funding = await self.exchange.fetch_funding_rate(symbol)
                additional_data['funding_rate'] = {
                    'rate': funding.get('fundingRate'),
                    'timestamp': funding.get('fundingTimestamp'),
                    'next_funding': funding.get('fundingDatetime')
                }

                successful_fetches += 1
                funding_rate = additional_data['funding_rate'].get('rate', 0)

                step.complete(
                    success=True,
                    details=f"Funding rate: {funding_rate*100:.4f}%",
                    metrics={'funding_rate': funding_rate}
                )
                plog.debug(f"Funding rate loaded: {funding_rate*100:.4f}%", agent="data_agent")

            except Exception as e:
                plog.warning(f"Failed to fetch funding rate: {e}", agent="data_agent")
                step.complete(success=False, details=str(e))
                additional_data['funding_rate'] = None

            # Log metrics
            MetricsLogger.log_metrics(
                "Additional Data Collection",
                {
                    'Symbol': symbol,
                    'Data Types': 2,
                    'Successful': successful_fetches,
                    'Order Book': "✓" if additional_data.get('order_book') else "✗",
                    'Funding Rate': "✓" if additional_data.get('funding_rate') else "✗"
                },
                phase='data_collection',
                agent='data_agent'
            )

        return additional_data

    async def run_analysis(self, symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """
        Run complete analysis on real-time data with enhanced logging
        
        Args:
            symbol: Trading pair to analyze
            
        Returns:
            Complete analysis results
        """
        plog.info(f"Starting realtime analysis pipeline for {symbol}", agent="system")
        
        try:
            # Phase 1: Data Collection (already wrapped in its own phases)
            plog.debug("Phase 1: Fetching market data", agent="system", phase="analysis")
            candles = await self.fetch_realtime_candles(symbol)
            
            if not candles or not any(candles.values()):
                plog.error("No candle data available - cannot proceed with analysis", agent="system")
                return None

            additional_data = await self.fetch_additional_data(symbol)
            
            # Phase 2: Data Storage
            async with PhaseLogger("data_storage", "Storing Data in State Manager", agent="system"):
                
                step = StepLogger("3.1", "Storing candle data and market metrics", agent="system")
                step.start()
                
                state_keys = []
                try:
                    # Store candle data
                    for tf in ['5m', '15m', '1h']:
                        key = f"candles_{tf}:{symbol.replace('/', '')}"
                        candle_data = candles.get(tf, [])
                        await self.state_manager.set(key, candle_data)
                        state_keys.append(key)
                        
                        plog.debug(f"Stored {tf} candles ({len(candle_data)} bars) in state manager", agent="system")
                    
                    # Store current price (from latest candle)
                    current_price = None
                    if candles.get('5m') and len(candles['5m']) > 0:
                        current_price = candles['5m'][-1]['close']
                        price_key = f"price:{symbol.replace('/', '')}"
                        await self.state_manager.set(price_key, current_price)
                        state_keys.append(price_key)
                        plog.debug(f"Stored current price: ${current_price:.2f}", agent="system")
                    
                    # Store ATR (calculate from 1H candles)
                    atr = 150.0  # Default ATR
                    if candles.get('1h') and len(candles['1h']) > 1:
                        closes = [c['close'] for c in candles['1h'][-14:]]  # Last 14 periods
                        highs = [c['high'] for c in candles['1h'][-14:]]
                        lows = [c['low'] for c in candles['1h'][-14:]]
                        
                        if len(closes) > 1:
                            tr_values = []
                            for i in range(1, len(closes)):
                                high_low = highs[i] - lows[i]
                                high_close = abs(highs[i] - closes[i-1])
                                low_close = abs(lows[i] - closes[i-1])
                                tr = max(high_low, high_close, low_close)
                                tr_values.append(tr)
                            
                            if tr_values:
                                atr = sum(tr_values) / len(tr_values)
                    
                    atr_key = f"atr:{symbol.replace('/', '')}"
                    await self.state_manager.set(atr_key, atr)
                    state_keys.append(atr_key)
                    plog.debug(f"Stored ATR: ${atr:.2f}", agent="system")
                    
                    # Store account balance
                    account_balance = 10000.0  # Default balance for testing
                    await self.state_manager.set("account_balance", account_balance)
                    state_keys.append("account_balance")
                    plog.debug(f"Stored account balance: ${account_balance:.2f}", agent="system")
                    
                    step.complete(
                        success=True,
                        details=f"Stored candle data for 3 timeframes + market metrics",
                        metrics={'timeframes': 3, 'price': current_price, 'atr': atr, 'balance': account_balance, 'keys': len(state_keys)}
                    )
                except Exception as e:
                    plog.error(f"Failed to store market data: {e}", exception=e, agent="system")
                    step.complete(success=False, details=str(e))
                
                step = StepLogger("3.2", "Storing additional market data", agent="system")
                step.start()
                
                try:
                    if additional_data.get('order_book'):
                        ob_key = f"order_book:{symbol.replace('/', '')}"
                        await self.state_manager.set(ob_key, additional_data['order_book'])
                        state_keys.append(ob_key)
                        plog.debug("Order book stored in state manager", agent="system")

                    if additional_data.get('funding_rate'):
                        fr_key = f"funding_rate:{symbol.replace('/', '')}"
                        await self.state_manager.set(fr_key, additional_data['funding_rate'])
                        state_keys.append(fr_key)
                        plog.debug("Funding rate stored in state manager", agent="system")
                    
                    step.complete(
                        success=True,
                        details=f"Additional data stored",
                        metrics={'data_items': len([k for k in state_keys if 'order_book' in k or 'funding_rate' in k])}
                    )
                    plog.success(f"Market data ready - {len(state_keys)} items in state manager", agent="system")
                except Exception as e:
                    plog.error(f"Failed to store additional data: {e}", exception=e, agent="system")
                    step.complete(success=False, details=str(e))
            
            # Phase 3: Deep Analysis (Claude Sonnet 4.5)
            async with PhaseLogger("analysis", "Market Analysis Pipeline (Claude Sonnet 4.5)", agent="analysis_agent"):
                
                step = StepLogger("4.1", "Running analysis agent - Indicators, SMC, ICT detection", agent="analysis_agent")
                step.start()
                
                try:
                    plog.debug("Starting analysis with market data and order book", agent="analysis_agent", phase="analysis")
                    
                    # Run the full analysis
                    analysis_result = await self.analysis_agent.analyze_market(
                        symbol=symbol.replace('/', ''),
                        candles=candles,
                        order_book=additional_data.get('order_book'),
                        funding_rate=additional_data.get('funding_rate')
                    )
                    
                    trade_opportunities = analysis_result.get('trade_opportunities', [])
                    analysis_id = analysis_result.get('analysis_id', 'N/A')
                    confidence = analysis_result.get('overall_confidence', 0)
                    
                    step.complete(
                        success=True,
                        details=f"Analysis complete - Found {len(trade_opportunities)} opportunities",
                        metrics={
                            'opportunities': len(trade_opportunities),
                            'analysis_id': analysis_id,
                            'confidence': f"{confidence:.2%}"
                        }
                    )
                    
                    plog.success(
                        f"Market analysis complete: {len(trade_opportunities)} trade opportunities identified",
                        agent="analysis_agent"
                    )
                    
                except Exception as e:
                    plog.error(f"Analysis failed: {e}", exception=e, agent="analysis_agent")
                    step.complete(success=False, details=str(e))
                    raise
                
                # Log metrics
                MetricsLogger.log_metrics(
                    "Analysis Results",
                    {
                        'Trade Opportunities': len(trade_opportunities),
                        'Overall Confidence': f"{confidence:.2%}",
                        'Analysis ID': str(analysis_id),
                        'Key Levels': len(analysis_result.get('key_levels', {})),
                        'SMC Patterns': len(analysis_result.get('smc_analysis', {}).get('computational', {}).get('order_blocks', []))
                    },
                    phase='analysis',
                    agent='analysis_agent'
                )
                
                # Display regime-adaptive insights
                self._display_regime_adaptive_insights(analysis_result)

            # Phase 4: Strategy Generation (GPT-4o)
            async with PhaseLogger("strategy_generation", f"Strategy Generation Pipeline (GPT-4o) for {symbol}", agent="strategy_agent"):
                
                step = StepLogger("5.1", "Generating trade setup with LLM reasoning", agent="strategy_agent")
                step.start()
                
                try:
                    plog.debug("Calling strategy generation agent with analysis results", agent="strategy_agent")
                    
                    # Generate strategy
                    strategy_result = await self.strategy_agent.generate_strategy(
                        symbol=symbol.replace('/', ''),
                        analysis=analysis_result
                    )
                    
                    trade_setup = strategy_result.get('trade_setup')
                    
                    if trade_setup:
                        direction = trade_setup.get('direction', 'N/A')
                        confidence = trade_setup.get('confidence_score', 0)
                        rr_ratio = trade_setup.get('risk_reward_ratio', 0)
                        
                        step.complete(
                            success=True,
                            details=f"Strategy generated - Direction: {direction}, Confidence: {confidence:.2%}, RR: {rr_ratio:.2f}",
                            metrics={
                                'direction': direction,
                                'confidence': confidence,
                                'risk_reward': rr_ratio
                            }
                        )
                        
                        plog.success(
                            f"Trade setup generated: {direction} with {confidence:.2%} confidence and {rr_ratio:.2f}:1 R/R ratio",
                            agent="strategy_agent"
                        )
                    else:
                        reason = strategy_result.get('reason', 'Unknown reason')
                        step.complete(
                            success=True,
                            details=f"No strategy generated - {reason}"
                        )
                        plog.info(
                            f"Strategy generation skipped: {reason}",
                            agent="strategy_agent"
                        )
                    
                except Exception as e:
                    plog.error(f"Strategy generation failed: {e}", exception=e, agent="strategy_agent")
                    step.complete(success=False, details=str(e))
                    raise
                
                # Log metrics
                MetricsLogger.log_metrics(
                    "Strategy Generation Results",
                    {
                        'Strategy Generated': "✓" if trade_setup else "✗",
                        'Direction': trade_setup.get('direction', 'N/A') if trade_setup else 'N/A',
                        'Confidence': f"{trade_setup.get('confidence_score', 0):.2%}" if trade_setup else 'N/A',
                        'Risk/Reward Ratio': f"{trade_setup.get('risk_reward_ratio', 0):.2f}" if trade_setup else 'N/A'
                    },
                    phase='strategy_generation',
                    agent='strategy_agent'
                )
            
            # Combine results
            combined_result = {
                **analysis_result,
                'strategy': strategy_result,
                'performance_metrics': {}
            }

            plog.success(
                f"Analysis pipeline complete - {len(analysis_result.get('trade_opportunities', []))} opportunities identified",
                agent="system"
            )

            return combined_result
            
        except Exception as e:
            plog.error(f"Analysis pipeline failed: {e}", exception=e, agent="system")
            return None

    def display_results(self, results: Dict[str, Any]):
        """Display analysis results in a beautiful format"""

        if not results:
            logger.warning("No results to display", extra={'phase': 'results_display'})
            return

        logger.info("Displaying analysis results", extra={
            'phase': 'results_display',
            'symbol': results.get('symbol'),
            'analysis_id': results.get('analysis_id')
        })

        # 1. Summary Panel
        summary_text = f"""
[bold]Symbol:[/bold] {results.get('symbol')}
[bold]Analysis ID:[/bold] {results.get('analysis_id')}
[bold]Timestamp:[/bold] {results.get('timestamp')}
[bold]Overall Confidence:[/bold] {results.get('overall_confidence', 0):.2%}
        """
        console.print(Panel(summary_text.strip(), title="Summary", border_style="cyan"))

        # 2. Market Structure
        market_structure = results.get('market_structure', {})
        if market_structure:
            structure_table = Table(title="Market Structure", box=box.ROUNDED)
            structure_table.add_column("Timeframe", style="cyan")
            structure_table.add_column("Trend", style="yellow")
            structure_table.add_column("Bias", style="magenta")

            for key, value in market_structure.items():
                if 'trend' in key.lower():
                    structure_table.add_row(key, str(value), "")
                elif 'bias' in key.lower():
                    structure_table.add_row("", "", str(value))

            console.print("\n")
            console.print(structure_table)

        # 3. Trade Opportunities
        opportunities = results.get('trade_opportunities', [])
        if opportunities:
            opp_table = Table(
                title=f"Trade Opportunities ({len(opportunities)} found)",
                box=box.DOUBLE_EDGE
            )
            opp_table.add_column("#", style="dim", width=3)
            opp_table.add_column("Direction", style="bold")
            opp_table.add_column("Type", style="cyan")
            opp_table.add_column("Entry Zone", style="yellow")
            opp_table.add_column("Confidence", style="green")
            opp_table.add_column("Confluences", style="magenta")

            for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
                direction = opp.get('direction', 'N/A')
                opp_type = opp.get('type', 'N/A')
                entry_zone = opp.get('entry_zone', [0, 0])
                
                # Safely convert confidence to float
                try:
                    confidence = float(opp.get('confidence', 0))
                except (ValueError, TypeError):
                    confidence = 0.0
                
                # Safely convert confluence_count to int
                try:
                    confluence_count = int(opp.get('confluence_count', 0))
                except (ValueError, TypeError):
                    confluence_count = 0

                direction_style = "green" if direction == "LONG" else "red"
                confidence_display = f"{confidence:.1%}"
                try:
                    entry_low = float(entry_zone[0])
                    entry_high = float(entry_zone[1])
                    entry_display = f"${entry_low:,.2f} - ${entry_high:,.2f}"
                except (ValueError, TypeError, IndexError):
                    entry_display = str(entry_zone)

                opp_table.add_row(
                    str(i),
                    f"[{direction_style}]{direction}[/{direction_style}]",
                    opp_type,
                    entry_display,
                    confidence_display,
                    str(confluence_count)
                )

            console.print("\n")
            console.print(opp_table)

            logger.info("Trade opportunities found", extra={
                'phase': 'results_display',
                'trade_opportunities_count': len(opportunities),
                'best_opportunity_direction': opportunities[0].get('direction') if opportunities else None,
                'best_opportunity_confidence': opportunities[0].get('confidence') if opportunities else None
            })
        else:
            logger.warning("No high-quality trade opportunities found", extra={
                'phase': 'results_display',
                'trade_opportunities_count': 0
            })

        # 4. Key Levels
        key_levels = results.get('key_levels', {})
        if key_levels:
            levels_table = Table(title="Key Levels", box=box.ROUNDED)
            levels_table.add_column("Type", style="cyan")
            levels_table.add_column("Levels", style="yellow")

            for level_type, levels in key_levels.items():
                if isinstance(levels, list):
                    # Safely format list items
                    formatted_levels = []
                    for l in levels[:3]:
                        try:
                            formatted_levels.append(f"${float(l):,.2f}")
                        except (ValueError, TypeError):
                            formatted_levels.append(str(l))
                    levels_str = ", ".join(formatted_levels)
                    levels_table.add_row(level_type.title(), levels_str)
                elif isinstance(levels, dict):
                    levels_table.add_row(level_type.title(), str(levels))
                else:
                    # Handle single values (float, int, etc.)
                    levels_table.add_row(level_type.title(), f"${levels:,.2f}" if isinstance(levels, (int, float)) else str(levels))

            console.print("\n")
            console.print(levels_table)

        # 5. SMC Analysis Summary
        smc_analysis = results.get('smc_analysis', {})
        if smc_analysis:
            smc_computational = smc_analysis.get('computational', {})

            smc_text = f"""
[bold]Order Blocks:[/bold] {len(smc_computational.get('order_blocks', []))} found
[bold]Fair Value Gaps:[/bold] {len(smc_computational.get('fair_value_gaps', []))} found
[bold]Current Trend:[/bold] {smc_computational.get('break_of_structure', {}).get('current_trend', 'N/A')}
[bold]Current Zone:[/bold] {smc_computational.get('current_zone', 'N/A')}
            """
            console.print("\n")
            console.print(Panel(smc_text.strip(), title="SMC Analysis", border_style="blue"))

        # 6. ICT Analysis Summary
        ict_analysis = results.get('ict_analysis', {})
        if ict_analysis:
            ict_computational = ict_analysis.get('computational', {})

            killzone_data = ict_computational.get('killzone', {})
            current_kz = killzone_data.get('current_killzone', 'none')
            setup_quality = ict_computational.get('setup_quality', 'unknown')

            ict_text = f"""
[bold]Current Killzone:[/bold] {current_kz.upper()}
[bold]Setup Quality:[/bold] {setup_quality.upper()}
[bold]Confluence Score:[/bold] {ict_computational.get('confluence_score', 0):.2f}
[bold]Order Flow Phase:[/bold] {ict_computational.get('order_flow', {}).get('phase', 'N/A')}
            """
            console.print("\n")
            console.print(Panel(ict_text.strip(), title="ICT Analysis", border_style="magenta"))

        # 7. Multi-Timeframe Analysis
        mtf_analysis = results.get('mtf_analysis', {})
        if mtf_analysis:
            mtf_text = f"""
[bold]Overall Bias:[/bold] {mtf_analysis.get('overall_bias', 'N/A').upper()}
[bold]Bias Strength:[/bold] {mtf_analysis.get('bias_strength', 0):.2f}
[bold]Alignment:[/bold] {mtf_analysis.get('alignment', 'N/A')}
[bold]Entry Timing:[/bold] {mtf_analysis.get('entry_timing', 'N/A').upper()}
[bold]Confluence Score:[/bold] {mtf_analysis.get('confluence_score', 0):.2f}

[bold yellow]Recommendation:[/bold yellow]
{mtf_analysis.get('recommendation', 'No recommendation available')}
            """
            console.print("\n")
            console.print(Panel(mtf_text.strip(), title="Multi-Timeframe Analysis", border_style="yellow"))

        # 8. LLM Reasoning
        reasoning = results.get('reasoning', '')
        if reasoning:
            console.print("\n")
            console.print(Panel(
                reasoning[:500] + ("..." if len(reasoning) > 500 else ""),
                title="AI Analysis Reasoning",
                border_style="green"
            ))

        # 9. Performance Metrics
        perf_metrics = results.get('performance_metrics', {})
        if perf_metrics:
            perf_table = Table(title="Performance Metrics", box=box.SIMPLE)
            perf_table.add_column("Metric", style="cyan")
            perf_table.add_column("Value", style="yellow")

            for metric, value in perf_metrics.items():
                perf_table.add_row(metric.replace('_', ' ').title(), f"{value:.2f}s")

            console.print("\n")
            console.print(perf_table)

        # 10. Strategy Results
        strategy = results.get('strategy', {})
        if strategy:
            self._display_strategy_results(strategy)
        else:
            logger.info("No strategy section in results - analysis may have failed or no opportunities found", extra={
                'phase': 'results_display',
                'strategy_section_missing': True
            })
            logger.info("ℹ️ System will wait for next analysis cycle", extra={
                'phase': 'results_display',
                'waiting_for': 'next_cycle'
            })

        console.print("\n" + "="*80 + "\n")
    
    def _display_regime_adaptive_insights(self, analysis_result: Dict[str, Any]):
        """Display regime-adaptive analysis insights"""
        regime_analysis = analysis_result.get('regime_adaptive_analysis')
        
        if not regime_analysis:
            console.print("[yellow]⚠️  Regime-adaptive analysis not available in results[/yellow]")
            return
        
        console.print("\n" + "="*80)
        console.print(Panel.fit(
            "🧠 REGIME-ADAPTIVE ANALYSIS INSIGHTS",
            border_style="bold magenta"
        ))
        console.print("="*80 + "\n")
        
        # 1. Market Regime
        regime = regime_analysis.get('regime', {})
        regime_table = Table(title="📊 Market Regime Detection", box=box.ROUNDED)
        regime_table.add_column("Metric", style="cyan", no_wrap=True)
        regime_table.add_column("Value", style="yellow")
        
        regime_table.add_row("Type", regime.get('type', 'Unknown'))
        regime_table.add_row("Confidence", f"{regime.get('confidence', 0):.1%}")
        regime_table.add_row("Trend Strength", f"{regime.get('trend_strength', 0):.1%}")
        regime_table.add_row("Volatility Level", f"{regime.get('volatility_level', 0):.1%}")
        
        console.print(regime_table)
        console.print(f"[dim]{regime.get('reasoning', '')}[/dim]\n")
        
        # 2. Timeframe Strategy
        tf_strategy = regime_analysis.get('timeframe_strategy', {})
        console.print("[bold]⏱️  Optimal Timeframe Strategy:[/bold]")
        console.print(f"  Primary (Focus): {', '.join(tf_strategy.get('primary', []))}")
        console.print(f"  Secondary (Support): {', '.join(tf_strategy.get('secondary', []))}")
        console.print(f"  Avoid (Too Noisy): {', '.join(tf_strategy.get('avoid', []))}")
        console.print(f"[dim]{tf_strategy.get('reasoning', '')}[/dim]\n")
        
        # 3. HTF Bias
        htf_bias = regime_analysis.get('htf_bias', 'NEUTRAL')
        bias_color = "green" if htf_bias == "BULLISH" else "red" if htf_bias == "BEARISH" else "yellow"
        console.print(Panel(
            f"[bold {bias_color}]{htf_bias}[/bold {bias_color}]",
            title="🎯 Higher Timeframe Bias",
            border_style=bias_color
        ))
        console.print()
        
        # 4. Confluence Analysis
        confluence = regime_analysis.get('confluence', {})
        count = confluence.get('count', 0)
        quality = confluence.get('quality_rating', 'POOR')
        quality_color = "green" if quality == "EXCELLENT" else "yellow" if quality == "GOOD" else "red"
        
        conf_table = Table(title="✨ Confluence Analysis", box=box.ROUNDED)
        conf_table.add_column("Metric", style="cyan")
        conf_table.add_column("Value", style="yellow")
        
        conf_table.add_row("Confluence Count", str(count))
        conf_table.add_row("Quality Rating", f"[{quality_color}]{quality}[/{quality_color}]")
        conf_table.add_row("Meets Minimum", "✓ Yes" if confluence.get('meets_minimum') else "✗ No")
        conf_table.add_row("Total Score", f"{confluence.get('total_score', 0):.2f}")
        
        console.print(conf_table)
        
        # By category
        by_category = confluence.get('by_category', {})
        if by_category:
            console.print("\n[cyan]Confluences by Category:[/cyan]")
            for category, cnt in by_category.items():
                console.print(f"  {category}: {cnt}")
        console.print()
        
        # 5. Professional Insights
        from rich.text import Text
        insights = regime_analysis.get('professional_insights', {})
        insights_text = Text()
        insights_text.append("🎓 Professional Trader Insights\n\n", style="bold yellow")
        insights_text.append(f"Top-Down Approach: {insights.get('top_down_approach', '')}\n", style="white")
        insights_text.append(f"Risk Assessment: {insights.get('risk_assessment', '')}\n", style="white")
        
        action = insights.get('recommended_action', 'WAIT')
        action_color = "green" if action == "ANALYZE" else "yellow"
        insights_text.append(f"Recommended Action: ", style="white")
        insights_text.append(f"{action}\n", style=f"bold {action_color}")
        
        console.print(Panel(insights_text, border_style="blue"))
        console.print()

    def save_results(self, results: Dict[str, Any], filename: str = None):
        """Save results to JSON file"""
        if not results:
            return
        
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"analysis_results_{timestamp}.json"
        
        # Convert non-serializable objects
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=serialize)
        
        logger.info(f"Results saved to file", extra={
            'phase': 'results_save',
            'filename': filename,
            'symbol': results.get('symbol'),
            'analysis_id': results.get('analysis_id')
        })

    def _display_strategy_results(self, strategy: Dict[str, Any]):
        """Display strategy generation results"""

        trade_setup = strategy.get('trade_setup')
        logger.info("Displaying strategy generation results", extra={
            'phase': 'results_display',
            'strategy_generated': trade_setup is not None
        })

        if not trade_setup:
            logger.warning("No valid trade setup generated", extra={
                'phase': 'results_display',
                'reason': strategy.get('reason', 'Unknown reason')
            })
            logger.info("ℹ️ System will wait for next analysis cycle with improved market conditions", extra={
                'phase': 'results_display',
                'waiting_for': 'better_market_conditions'
            })
            return

        # Strategy Overview
        overview_text = f"""
[bold]Strategy ID:[/bold] {trade_setup.get('setup_id')}
[bold]Direction:[/bold] {trade_setup.get('direction')}
[bold]Type:[/bold] {trade_setup.get('strategy_type')}
[bold]Confidence:[/bold] {trade_setup.get('confidence_score', 0):.2%}
[bold]Risk-Reward:[/bold] {trade_setup.get('risk_reward_ratio', 0):.2f}
        """
        console.print(Panel(overview_text.strip(), title="Strategy Overview", border_style="magenta"))

        # Entry Details
        entry_text = f"""
[bold]Entry Price:[/bold] ${trade_setup.get('entry_price', 0):,.2f}
[bold]Entry Zone:[/bold] ${trade_setup.get('entry_zone_low', 0):,.2f} - ${trade_setup.get('entry_zone_high', 0):,.2f}
[bold]Stop Loss:[/bold] ${trade_setup.get('stop_loss', 0):,.2f}
[bold]Risk Amount:[/bold] ${trade_setup.get('risk_amount', 0):,.2f}
        """
        console.print(Panel(entry_text.strip(), title="Entry & Risk Management", border_style="yellow"))

        # Take Profit Levels
        tp_levels = trade_setup.get('take_profit_levels', [])
        if tp_levels:
            tp_table = Table(title="Take Profit Levels", box=box.DOUBLE_EDGE)
            tp_table.add_column("Level", style="cyan", width=8)
            tp_table.add_column("Price", style="yellow")
            tp_table.add_column("Size", style="green")
            tp_table.add_column("RR Multiple", style="magenta")

            for tp in tp_levels:
                level = tp.get('level')
                price = tp.get('price', 0)
                size = tp.get('size', 0)
                entry = trade_setup.get('entry_price', 0)
                sl = trade_setup.get('stop_loss', 0)
                risk = abs(entry - sl)
                rr = (price - entry) / risk if risk > 0 else 0

                tp_table.add_row(
                    f"TP{level}",
                    f"${price:,.2f}",
                    f"{size:.1%}",
                    f"{rr:.1f}:1"
                )

            console.print("\n")
            console.print(tp_table)

        # Position Sizing
        sizing = strategy.get('sizing_analysis', {})
        if sizing:
            sizing_text = f"""
[bold]Recommended Size:[/bold] {sizing.get('recommended_size', 0):.6f} BTC
[bold]Max Size:[/bold] {sizing.get('max_size', 0):.6f} BTC
[bold]Risk Amount:[/bold] ${sizing.get('risk_amount', 0):,.2f}
[bold]Account Balance:[/bold] ${sizing.get('account_balance', 0):,.2f}
            """
            console.print("\n")
            console.print(Panel(sizing_text.strip(), title="Position Sizing", border_style="green"))

        # Confluence Analysis
        confluence = strategy.get('confluence_analysis', {})
        if confluence:
            conf_table = Table(title="Confluence Analysis", box=box.ROUNDED)
            conf_table.add_column("Metric", style="cyan")
            conf_table.add_column("Value", style="yellow")

            conf_table.add_row("Total Confluences", str(confluence.get('confluence_count', 0)))
            conf_table.add_row("Quality Rating", confluence.get('quality_rating', 'N/A'))
            conf_table.add_row("Total Score", f"{confluence.get('total_score', 0):.2f}")

            console.print("\n")
            console.print(conf_table)

        # Key Confluences
        confluences = trade_setup.get('confluences', [])
        if confluences:
            conf_text = "[bold]Key Confluences:[/bold]\n"
            for i, conf in enumerate(confluences, 1):
                conf_text += f"{i}. {conf}\n"
            console.print("\n")
            console.print(Panel(conf_text.strip(), title="Setup Confluences", border_style="blue"))

        # Invalidation Conditions
        invalidations = trade_setup.get('invalidation_conditions', [])
        if invalidations:
            inv_text = "[bold]Invalidation Conditions:[/bold]\n"
            for i, inv in enumerate(invalidations, 1):
                inv_text += f"{i}. {inv}\n"
            console.print("\n")
            console.print(Panel(inv_text.strip(), title="Invalidation Conditions", border_style="red"))

        # Performance Metrics
        perf = strategy.get('performance_metrics', {})
        if perf:
            perf_table = Table(title="Strategy Generation Performance", box=box.SIMPLE)
            perf_table.add_column("Phase", style="cyan")
            perf_table.add_column("Time (s)", style="yellow")

            perf_table.add_row("Computational", f"{perf.get('computational_time', 0):.2f}")
            perf_table.add_row("Confluence", f"{perf.get('confluence_time', 0):.2f}")
            perf_table.add_row("LLM Refinement", f"{perf.get('llm_time', 0):.2f}")
            perf_table.add_row("Position Sizing", f"{perf.get('sizing_time', 0):.2f}")
            perf_table.add_row("Total", f"{perf.get('total_time_seconds', 0):.2f}")

            console.print("\n")
            console.print(perf_table)

        # Setup Reasoning
        reasoning = trade_setup.get('setup_reasoning', '')
        if reasoning:
            console.print("\n")
            console.print(Panel(
                reasoning[:800] + ("..." if len(reasoning) > 800 else ""),
                title="Setup Reasoning",
                border_style="cyan"
            ))


async def main():
    """Main test runner with enhanced logging"""
    
    cycle_start = datetime.now(timezone.utc)
    plog.info("🚀 Real-Time BTC Analysis Test Started", agent="system")
    
    # Create tester instance
    tester = RealtimeBTCAnalysisTester()

    try:
        # Phase 1: System Setup
        await tester.setup()
        
        # Phase 2-4: Run complete analysis pipeline
        plog.info("Starting analysis pipeline", agent="system")
        results = await tester.run_analysis(symbol="BTC/USDT")
        
        if results:
            # Phase 5: Display Results
            async with PhaseLogger("results_display", "Displaying Analysis Results", agent="system"):
                step = StepLogger("5.1", "Rendering results to console", agent="system")
                step.start()
                
                try:
                    plog.debug("Formatting and displaying results", agent="system")
                    console.print("\n")
                    tester.display_results(results)
                    
                    step.complete(success=True, details="Results displayed to console")
                    plog.success("Results display complete", agent="system")
                except Exception as e:
                    plog.error(f"Failed to display results: {e}", exception=e, agent="system")
                    step.complete(success=False, details=str(e))
            
            # Phase 6: Save Results
            async with PhaseLogger("results_save", "Saving Analysis Results to File", agent="system"):
                step = StepLogger("6.1", "Writing results to JSON file", agent="system")
                step.start()
                
                try:
                    plog.debug("Saving analysis results", agent="system")
                    tester.save_results(results)
                    
                    step.complete(success=True, details="Results saved to JSON file")
                    plog.success("Results saved successfully", agent="system")
                except Exception as e:
                    plog.error(f"Failed to save results: {e}", exception=e, agent="system")
                    step.complete(success=False, details=str(e))
            
            # Summary metrics
            strategy_generated = results.get('strategy', {}).get('trade_setup') is not None
            trade_opportunities_found = len(results.get('trade_opportunities', []))
            
            console.print("\n" + "="*80)
            
            if strategy_generated:
                plog.success(
                    f"Test cycle complete - {trade_opportunities_found} opportunities identified, strategy generated",
                    agent="system"
                )
            else:
                plog.info(
                    f"Test cycle complete - {trade_opportunities_found} opportunities identified, awaiting better market conditions for strategy",
                    agent="system"
                )
        else:
            plog.error("Analysis failed - no results generated", agent="system")

    except KeyboardInterrupt:
        plog.warning("Test cycle interrupted by user", agent="system")
    except Exception as e:
        plog.error(f"Test cycle failed: {e}", exception=e, agent="system")
    finally:
        # Cleanup
        plog.debug("Starting system cleanup", agent="system", phase="teardown")
        await tester.teardown()

        total_runtime = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        
        MetricsLogger.log_metrics(
            "Test Cycle Summary",
            {
                'Total Runtime': f"{total_runtime:.2f}s",
                'Status': "Complete",
                'Symbol': "BTC/USDT",
                'Test Type': "Real-Time Analysis"
            },
            phase='teardown',
            agent='system'
        )
        
        plog.success(f"Test cycle completed in {total_runtime:.2f}s", agent="system")


if __name__ == "__main__":
    plog.info("🚀 Initializing Real-Time BTC Analysis Tester", agent="system")
    plog.debug("Using: Binance live data + AI-powered analysis (Claude + GPT-4)", agent="system")
    
    asyncio.run(main())


