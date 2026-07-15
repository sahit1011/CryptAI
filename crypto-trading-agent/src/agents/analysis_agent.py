"""
Market Analysis Agent
Orchestrates comprehensive market analysis using computational methods + LLM reasoning
"""
import asyncio
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from anthropic import AsyncAnthropic
import openai
import pandas as pd
import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.analysis.indicators import TechnicalIndicators
from src.analysis.smc_detector import SMCDetector
from src.analysis.ict_detector import ICTDetector
from src.analysis.pattern_recognition import PatternRecognizer
from src.analysis.llm_context_builder import LLMContextBuilder
from src.analysis.mtf_analyzer import MultiTimeframeAnalyzer
from src.utils.config import get_config
from src.utils.enhanced_logging import PhaseLogger, StepLogger, MetricsLogger
from src.utils.pipeline_logger import PipelineLogger
from src.utils.llm_cache import analysis_llm_cache
from src.strategy.confluence_scorer import ConfluenceScorer
from src.analysis.data_models import AnalysisResult
from src.utils.serialize_utils import serialize_for_message_bus  # CRITICAL FIX: Pandas serialization

# Import regime-adaptive components
try:
    from playground.evaluation.regime_detector import RegimeDetector
    from playground.evaluation.adaptive_timeframe_selector import AdaptiveTimeframeSelector
    # ConfluenceScorer moved to src.strategy
    REGIME_ADAPTIVE_AVAILABLE = True
except ImportError:
    REGIME_ADAPTIVE_AVAILABLE = False
    logger.warning("Regime-adaptive components not available - using standard analysis")

# Create pipeline logger instance
plog = PipelineLogger()

# Gate verbose per-message payload-dump logging behind LOG_LEVEL=DEBUG so production
# stdout stays clean. These dumps can emit ~100 lines (full payloads, per-candle
# structure) on every analysis request, which is noise in normal operation.
_DEBUG_PAYLOAD_LOGGING = os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"

class MarketAnalysisAgent(BaseAgent):
    """
    Market Analysis Agent

    Responsibilities:
    1. Receive market data from Data Agent
    2. Run computational analysis (indicators, SMC, ICT, patterns)
    3. Prepare optimized LLM context
    4. Call Claude Sonnet 4.5 for deep analysis
    5. Parse and validate results
    6. Send analysis to Strategy Agent
    """

    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager
    ):
        super().__init__("analysis_agent", message_bus, state_manager)

        self.config = get_config()

        # Initialize analysis modules
        self.indicators_calc = TechnicalIndicators()
        self.smc_detector = SMCDetector()
        self.ict_detector = ICTDetector()
        self.pattern_recognizer = PatternRecognizer()
        self.context_builder = LLMContextBuilder()
        self.mtf_analyzer = MultiTimeframeAnalyzer()
        
        # Initialize Confluence Scorer (Core Component)
        self.confluence_scorer = ConfluenceScorer()

        # Initialize regime-adaptive components (if available)
        if REGIME_ADAPTIVE_AVAILABLE:
            self.regime_detector = RegimeDetector()
            self.timeframe_selector = AdaptiveTimeframeSelector()
            plog.info("Regime-adaptive framework enabled", agent="analysis_agent")
        else:
            self.regime_detector = None
            self.timeframe_selector = None

        # Initialize LLM clients. Anthropic client ONLY when a key is set — constructing
        # AsyncAnthropic(api_key=None) raises, which would crash the whole agent even
        # when OpenRouter alone is configured (the selection falls back to OpenRouter).
        self.llm_client = None
        if self.config.llm.anthropic_api_key:
            self.llm_client = AsyncAnthropic(api_key=self.config.llm.anthropic_api_key)

        # OpenRouter client for fallback (DeepSeek) - only initialize if key is available
        self.openrouter_client = None
        if self.config.llm.openrouter_api_key:
            self.openrouter_client = openai.OpenAI(
                api_key=self.config.llm.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )

        # Groq client for final fallback
        self.groq_client = None
        if self.config.llm.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.config.llm.groq_api_key)
            except ImportError:
                logger.warning("Groq package not installed, skipping Groq client initialization")

        # Analysis cache
        self.last_analysis = {}
        self.analysis_count = 0

    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("market_data_update", self._handle_market_data)
        self.register_handler("analyze_market", self._handle_analysis_request_debug)  # For orchestrator
        self.register_handler("request_analysis", self._handle_analysis_request_debug)
        
        # CRITICAL FIX: Log registered handlers
        plog.info(
            f"📋 Analysis Agent handlers registered: {list(self.handlers.keys())}",
            agent="analysis_agent"
        )
        plog.info(
            f"📋 'analyze_market' handler points to: {self.handlers.get('analyze_market').__name__}",
            agent="analysis_agent"
        )

    async def start(self):
        """Start the analysis agent"""
        await super().start()
        plog.info("Analysis Agent started successfully", agent="analysis_agent", phase="setup")

    async def stop(self):
        """Stop the agent"""
        # Log cache statistics before stopping
        await analysis_llm_cache.log_stats()
        await super().stop()
        plog.info("Analysis Agent stopped", agent="analysis_agent", phase="teardown")

    async def _handle_market_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle market data update from Data Agent
        Trigger comprehensive analysis
        """
        try:
            symbol = payload['symbol']
            candles = payload['candles']

            plog.info(f"Received market data for {symbol}", agent="analysis_agent", phase="data_reception")

            # Run complete analysis
            analysis_result = await self.analyze_market(
                symbol=symbol,
                candles=candles,
                order_book=payload.get('order_book'),
                funding_rate=payload.get('funding_rate')
            )

            # Send results to Strategy Agent
            if analysis_result['trade_opportunities']:
                await self.send_message(
                    receiver="strategy_agent",
                    message_type="analysis_complete",
                    payload=analysis_result,
                    priority=8
                )
                plog.success(
                    f"Analysis complete: found {len(analysis_result['trade_opportunities'])} opportunities",
                    agent="analysis_agent"
                )
            else:
                plog.warning("Analysis complete but no high-quality setups found", agent="analysis_agent")

            return {"status": "success"}

        except Exception as e:
            plog.error(f"Error handling market data: {e}", exception=e, agent="analysis_agent")
            return {"status": "error", "message": str(e)}

    async def _handle_analysis_request_debug(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle analysis request from orchestrator
        """
        plog.info(
            f"🎯 _handle_analysis_request CALLED with payload keys: {list(payload.keys())}",
            agent="analysis_agent"
        )

        # Publish activity
        await self.publish_activity(
            action="analysis_request_received",
            message=f"Received analysis request for {payload.get('symbol', 'unknown')}",
            phase="analysis_request",
            severity="info"
        )


        try:
            symbol = payload.get('symbol')
            candles = payload.get('candles', {})
            market_data = payload.get('market_data', {})

            # Verbose per-message payload inspection: full raw structure, per-timeframe
            # candle types, sample-candle keys, timestamp types. Useful when debugging
            # orchestrator wiring, but ~100 lines of noise in production - gate it.
            if _DEBUG_PAYLOAD_LOGGING:
                plog.debug(f"📩 Raw payload type: {type(payload)}", agent="analysis_agent")
                plog.debug(f"📩 Raw payload keys: {list(payload.keys())}", agent="analysis_agent")
                plog.debug(f"📩 Candles type after .get(): {type(candles)}", agent="analysis_agent")

                if isinstance(candles, dict):
                    plog.debug(f"📩 Candles dict keys: {list(candles.keys())}", agent="analysis_agent")
                    # Log each timeframe's candles structure
                    for tf, candle_list in candles.items():
                        plog.debug(
                            f"📩 {tf}: type={type(candle_list)}, len={len(candle_list) if isinstance(candle_list, list) else 'N/A'}",
                            agent="analysis_agent"
                        )
                        # Log sample candle if available
                        if isinstance(candle_list, list) and len(candle_list) > 0:
                            sample = candle_list[0]
                            plog.debug(
                                f"📩 {tf} sample candle keys: {list(sample.keys()) if isinstance(sample, dict) else 'N/A'}",
                                agent="analysis_agent"
                            )
                            if isinstance(sample, dict) and 'timestamp' in sample:
                                plog.debug(
                                    f"📩 {tf} sample timestamp type: {type(sample['timestamp'])}, value: {sample['timestamp']}",
                                    agent="analysis_agent"
                                )

            plog.info(f"Received analysis request for {symbol}", agent="analysis_agent", phase="analysis_request")

            # Essential input validation (kept at INFO/ERROR): candle counts and the
            # critical empty/invalid-candles guards that indicate real upstream failures.
            if isinstance(candles, dict):
                candle_counts = {tf: len(candle_list) if isinstance(candle_list, list) else 0
                                for tf, candle_list in candles.items()}
                total_candles = sum(candle_counts.values())
                plog.info(
                    f"📊 Candles received: {candle_counts} (total: {total_candles})",
                    agent="analysis_agent"
                )

                if total_candles == 0:
                    plog.error(
                        "❌ CRITICAL: Received empty candles dict from orchestrator!",
                        agent="analysis_agent"
                    )
            else:
                plog.error(
                    f"❌ CRITICAL: Candles is not a dict! Type: {type(candles)}",
                    agent="analysis_agent"
                )

            # Run complete analysis
            analysis_result = await self.analyze_market(
                symbol=symbol,
                candles=candles,
                order_book=market_data.get('order_book'),
                funding_rate=market_data.get('funding_rate')
            )
            
            # CRITICAL FIX: Serialize pandas objects before sending
            # This prevents DataFrames/Series from being converted to string representations
            serialized_analysis = serialize_for_message_bus(analysis_result)
            
            plog.debug(
                f"📤 Serialized analysis result - type: {type(serialized_analysis)}",
                agent="analysis_agent"
            )
            
            return {
                "success": True,
                "analysis": serialized_analysis
            }
            
        except Exception as e:
            plog.error(f"Error handling analysis request: {e}", exception=e, agent="analysis_agent")
            return {"success": False, "error": str(e)}

    async def analyze_market(
        self,
        symbol: str,
        candles: Dict[str, List[Dict]],
        order_book: Optional[Dict] = None,
        funding_rate: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Complete market analysis pipeline

        Pipeline:
        1. Computational Analysis (Indicators, SMC, ICT, Patterns)
        2. Context Preparation
        3. LLM Deep Analysis
        4. Result Synthesis

        Returns:
            Complete analysis with trade opportunities
        """
        start_time = datetime.now()

        # Initialize before the try so the except/fallback path can always reference
        # it. Otherwise an exception raised before the assignment at Step 1.1 (e.g. in
        # regime/context setup, or even during computational analysis itself) would
        # trigger an UnboundLocalError in the fallback and kill graceful degradation.
        computational_results: Dict[str, Any] = {}

        async with PhaseLogger("analysis", f"Market Analysis for {symbol}", agent="analysis_agent"):

            try:
                # Step 1: Computational Analysis
                step = StepLogger("1.1", "Running computational analysis", agent="analysis_agent")
                step.start()
                
                await self.publish_activity(
                    action="computational_analysis",
                    message="Running technical indicators, SMC, and ICT analysis",
                    phase="analysis",
                    severity="info"
                )

                
                plog.debug(f"Starting computational analysis for {len(candles)} timeframes", 
                          agent="analysis_agent", phase="analysis")
                computational_results = await self._run_computational_analysis(candles)
                
                # Log detailed computational results summary
                try:
                    plog.info("=" * 80, agent="analysis_agent")
                    plog.info("COMPUTATIONAL ANALYSIS RESULTS SUMMARY", agent="analysis_agent")
                    plog.info("=" * 80, agent="analysis_agent")
                    
                    for tf in computational_results['indicators'].keys():
                        smc_data = computational_results['smc'].get(tf, {})
                        ict_data = computational_results['ict'].get(tf, {})
                        pattern_data = computational_results['patterns'].get(tf, {})
                        
                        ob_count = len(smc_data.get('order_blocks', []))
                        fvg_count = len(smc_data.get('fair_value_gaps', []))
                        bos_detected = smc_data.get('break_of_structure', {}).get('bos', False)
                        
                        sweep_count = len(ict_data.get('liquidity_sweeps', []))
                        in_ote = ict_data.get('ote_zones', {}).get('in_ote_zone', False)
                        killzone = ict_data.get('killzone', {}).get('current_killzone', 'none')
                        
                        pattern_count = len(pattern_data.get('patterns', []))
                        
                        # Use string concatenation to avoid formatting issues
                        log_msg = (
                            f"[{tf.upper()}] OBs={ob_count}, FVGs={fvg_count}, BOS={bos_detected}, "
                            f"Sweeps={sweep_count}, OTE={in_ote}, KZ={killzone}, Patterns={pattern_count}"
                        )
                        plog.info(log_msg, agent="analysis_agent")
                    
                    plog.info("=" * 80, agent="analysis_agent")
                except Exception as log_err:
                    plog.debug(f"Error logging computational summary: {log_err}", agent="analysis_agent")
                
                step.complete(
                    success=True,
                    details=f"Computed indicators, SMC, ICT, and patterns across {len(computational_results['indicators'])} timeframes",
                    metrics={
                        'timeframes': len(computational_results['indicators']),
                        'total_order_blocks': sum(len(smc.get('order_blocks', [])) for smc in computational_results['smc'].values()),
                        'total_fvgs': sum(len(smc.get('fair_value_gaps', [])) for smc in computational_results['smc'].values()),
                        'total_patterns': sum(len(p.get('patterns', [])) for p in computational_results['patterns'].values())
                    }
                )

                # Step 2: Regime-Adaptive Analysis (Enhanced)
                step = StepLogger("1.2", "Running regime-adaptive analysis", agent="analysis_agent")
                step.start()
                
                await self.publish_activity(
                    action="regime_analysis",
                    message="Detecting market regime and optimal timeframes",
                    phase="analysis",
                    severity="info"
                )

                
                # Detect market regime and adapt strategy
                regime_analysis = {}
                try:
                    regime_analysis = await self._run_regime_adaptive_analysis(
                        candles=candles,
                        computational_results=computational_results
                    )
                    
                    step.complete(
                        success=True,
                        details=f"Regime: {regime_analysis.get('regime', {}).get('type', 'unknown')}",
                        metrics={
                            'regime': regime_analysis.get('regime', {}).get('type', 'unknown'),
                            'confluences': regime_analysis.get('confluence', {}).get('count', 0)
                        }
                    )
                except Exception as e:
                    plog.error(f"Error in regime-adaptive analysis: {e}", exception=e, agent="analysis_agent")
                    step.complete(success=False, details=f"Failed: {str(e)}")
                    # Continue without regime analysis
                    regime_analysis = {}

                # Step 3: Enhanced Context Preparation
                step = StepLogger("1.3", "Preparing enhanced LLM context", agent="analysis_agent")
                step.start()

                plog.debug("Building enhanced LLM context with regime-adaptive insights", agent="analysis_agent")
                # Get historical context
                historical_trades = await self._get_historical_trades(symbol, limit=20)
                market_regime = await self.state_manager.get('market_regime')

                # Extract timeframe strategy if available
                timeframe_strategy = None
                if regime_analysis and 'timeframe_strategy' in regime_analysis:
                    timeframe_strategy = regime_analysis['timeframe_strategy']
                    active_tfs = timeframe_strategy.get('primary', []) + timeframe_strategy.get('secondary', [])
                    plog.info(f"Timeframe filtering enabled: {active_tfs} (avoiding: {timeframe_strategy.get('avoid', [])})", agent="analysis_agent")
                else:
                    plog.info("No timeframe filtering - using all available timeframes", agent="analysis_agent")

                # Build enhanced context with regime-adaptive insights
                llm_context = self.context_builder.build_analysis_context(
                    symbol=symbol,
                    candles=candles,
                    indicators=computational_results['indicators'],
                    smc_results=computational_results['smc'],
                    ict_results=computational_results['ict'],
                    patterns=computational_results['patterns'],
                    historical_trades=historical_trades,
                    market_regime=market_regime,
                    timeframe_strategy=timeframe_strategy
                )
                
                # Enhance context with regime-adaptive analysis
                if regime_analysis:
                    llm_context['regime_adaptive_analysis'] = regime_analysis

                # Safe JSON encoding with fallback
                try:
                    context_json = json.dumps(llm_context)
                except TypeError:
                    class SafeEncoder(json.JSONEncoder):
                        def default(self, o):
                            if isinstance(o, (np.bool_, bool)):
                                return str(o)
                            return str(o)
                    context_json = json.dumps(llm_context, cls=SafeEncoder)
                
                # DETAILED LOGGING: Show what's being sent to LLM
                try:
                    plog.info("=" * 80, agent="analysis_agent")
                    plog.info("LLM CONTEXT BREAKDOWN", agent="analysis_agent")
                    plog.info("=" * 80, agent="analysis_agent")
                    
                    # Calculate token estimates per section
                    def estimate_section_tokens(data):
                        try:
                            return int(len(json.dumps(data, cls=SafeEncoder)) * 0.25)
                        except:
                            return 0
                    
                    # Log each section size
                    sections_info = []
                    for key in ['system_prompt', 'current_data', 'indicators', 'smc_analysis', 
                               'ict_analysis', 'patterns', 'historical_context', 'task_instructions',
                               'regime_adaptive_analysis']:
                        if key in llm_context:
                            tokens = estimate_section_tokens(llm_context[key])
                            sections_info.append(f"{key}: ~{tokens} tokens")
                            
                            # Show data structure details
                            if key == 'current_data':
                                timeframes = list(llm_context[key].keys())
                                candle_counts = {tf: len(llm_context[key][tf]) for tf in timeframes}
                                log_msg = f"  • current_data: {timeframes} with {candle_counts} candles"
                                plog.info(log_msg, agent="analysis_agent")
                            elif key == 'indicators':
                                timeframes = list(llm_context[key].keys())
                                log_msg = f"  • indicators: {len(timeframes)} timeframes = {timeframes}"
                                plog.info(log_msg, agent="analysis_agent")
                            elif key == 'smc_analysis':
                                total_obs = sum(len(tf_data.get('order_blocks', [])) for tf_data in llm_context[key].values() if isinstance(tf_data, dict))
                                total_fvgs = sum(len(tf_data.get('fair_value_gaps', [])) for tf_data in llm_context[key].values() if isinstance(tf_data, dict))
                                log_msg = f"  • smc_analysis: {total_obs} OBs, {total_fvgs} FVGs across {len(llm_context[key])} timeframes"
                                plog.info(log_msg, agent="analysis_agent")
                            elif key == 'ict_analysis':
                                total_sweeps = sum(len(tf_data.get('liquidity_sweeps', [])) for tf_data in llm_context[key].values() if isinstance(tf_data, dict))
                                log_msg = f"  • ict_analysis: {total_sweeps} sweeps across {len(llm_context[key])} timeframes"
                                plog.info(log_msg, agent="analysis_agent")
                            elif key == 'patterns':
                                total_patterns = sum(len(tf_data.get('patterns', [])) for tf_data in llm_context[key].values() if isinstance(tf_data, dict))
                                log_msg = f"  • patterns: {total_patterns} patterns across {len(llm_context[key])} timeframes"
                                plog.info(log_msg, agent="analysis_agent")
                            elif key == 'regime_adaptive_analysis' and llm_context[key]:
                                regime_type = llm_context[key].get('regime', {}).get('type', 'unknown')
                                confluence_count = llm_context[key].get('confluence', {}).get('count', 0)
                                log_msg = f"  • regime_adaptive: {regime_type}, {confluence_count} confluences"
                                plog.info(log_msg, agent="analysis_agent")
                    
                    total_tokens = int(len(context_json) * 0.25)
                    plog.info(f"\nTotal Context Size: {len(context_json):,} chars = ~{total_tokens:,} tokens", agent="analysis_agent")
                    plog.info("=" * 80, agent="analysis_agent")
                except Exception as log_err:
                    plog.debug(f"Error logging LLM context breakdown: {log_err}", agent="analysis_agent")
                    # Still calculate total tokens for metrics
                    total_tokens = int(len(context_json) * 0.25)
                
                step.complete(
                    success=True,
                    details=f"LLM context prepared with all analysis data (~{total_tokens:,} tokens)",
                    metrics={
                        'context_size_kb': len(context_json) // 1024,
                        'context_size_chars': len(context_json),
                        'estimated_tokens': total_tokens
                    }
                )

                # Step 4: LLM Deep Analysis (with enhanced context)
                step = StepLogger("1.4", "Running LLM analysis (Claude Sonnet 4.5)", agent="analysis_agent")
                step.start()
                
                await self.publish_activity(
                    action="llm_analysis",
                    message="Calling Claude Sonnet 4.5 for deep market analysis",
                    phase="analysis",
                    severity="info"
                )


                plog.debug("Calling Claude Sonnet 4.5 for deep analysis", agent="analysis_agent", phase="llm_analysis")

                # Populate the exact keys the LLM cache derives its key from.
                # The cache (`LLMResponseCache._generate_cache_key`) reads
                # `symbol`, `primary_timeframe`, and a `computational_analysis` sub-tree.
                # `context_builder.build_analysis_context` does NOT set those keys, so
                # every request previously hashed identical defaults -> one constant key:
                # distinct symbols/timeframes/windows collided (wrong/stale results) and
                # the cache was effectively useless. Deriving the key from real inputs
                # (symbol, primary timeframe, structural counts, last-candle timestamps)
                # makes distinct requests miss and identical snapshots hit correctly.
                llm_context['symbol'] = symbol
                llm_context['primary_timeframe'] = (
                    (timeframe_strategy or {}).get('primary', [None])[0]
                    if timeframe_strategy else None
                ) or next(iter(candles.keys()), None)
                llm_context['computational_analysis'] = self._build_cache_discriminator(
                    computational_results, candles
                )

                llm_analysis = await self._call_llm_analysis(llm_context)

                step.complete(
                    success=True,
                    details="LLM analysis complete",
                    metrics={'opportunities': len(llm_analysis.get('trade_opportunities', []))}
                )

                # Step 5: Result Synthesis & Validation
                step = StepLogger("1.5", "Synthesizing and validating results", agent="analysis_agent")
                step.start()

                plog.debug(f"Synthesizing results for {symbol}", agent="analysis_agent", phase="results_compilation")

                final_result = self._synthesize_results(
                    symbol=symbol,
                    computational=computational_results,
                    llm_analysis=llm_analysis,
                    order_book=order_book,
                    funding_rate=funding_rate,
                    candles=candles,
                    regime_analysis=regime_analysis
                )
            
                # Validate with Pydantic
                try:
                    # Ensure timestamps are strings
                    if isinstance(final_result.get('timestamp'), datetime):
                        final_result['timestamp'] = final_result['timestamp'].isoformat()
                        
                    validated_result = AnalysisResult(**final_result)
                    # Return validated dict
                    final_result = validated_result.dict()
                    step.complete(success=True, details="Result validation passed")
                except Exception as e:
                    plog.error(f"Validation failed: {e}", agent="analysis_agent")
                    step.complete(success=False, details=f"Validation failed: {e}")
                    final_result['validation_error'] = str(e)

                total_time = (datetime.now() - start_time).total_seconds()
                
                MetricsLogger.log_metrics(
                    "Market Analysis Complete",
                    {
                        'Total Duration': f"{total_time:.2f}s",
                        'Regime': final_result.get('market_regime', {}).get('type', 'unknown'),
                        'Opportunities': len(final_result.get('trade_opportunities', [])),
                        'Validation': 'Passed' if 'validation_error' not in final_result else 'Failed'
                    },
                    phase='analysis',
                    agent='analysis_agent'
                )

                plog.method_exit(
                    "analyze_market",
                    result=f"Analysis complete for {symbol}: {len(final_result.get('trade_opportunities', []))} opportunities"
                )

                final_result['performance_metrics'] = {
                    'total_time_seconds': round(total_time, 2)
                }

                # Create summary table
                summary_table = Table(title="🔍 Market Analysis Summary", show_header=True, header_style="bold magenta")
                summary_table.add_column("Metric", style="cyan", no_wrap=True)
                summary_table.add_column("Value", style="green")

                summary_table.add_row("Symbol", symbol)
                summary_table.add_row("Analysis Time", f"{total_time:.2f}s")
                summary_table.add_row("Trade Opportunities", str(len(final_result['trade_opportunities'])))
                overall_confidence = final_result.get('overall_confidence', 0)
                if isinstance(overall_confidence, (int, float)):
                    confidence_str = f"{overall_confidence:.2%}"
                else:
                    confidence_str = str(overall_confidence)
                summary_table.add_row("Overall Confidence", confidence_str)

                current_price = final_result.get('current_price', 0)
                if isinstance(current_price, (int, float)):
                    price_str = f"${current_price:.2f}"
                else:
                    price_str = str(current_price)
                summary_table.add_row("Current Price", price_str)

                summary_table.add_row("Market Structure", final_result.get('market_structure', {}).get('overall_bias', 'unknown').upper())

                # Create opportunities panel
                opportunities_text = Text()
                opportunities_text.append("Trade Opportunities Found:\n", style="bold yellow")
                for i, opp in enumerate(final_result['trade_opportunities'][:3], 1):  # Show top 3
                    confidence = opp.get('confidence', 0)
                    if isinstance(confidence, (int, float)):
                        confidence_str = f"{confidence:.1%}"
                    else:
                        confidence_str = str(confidence)
                    opportunities_text.append(f"{i}. {opp.get('direction', 'N/A').upper()} @ {confidence_str} confidence\n", style="white")

                opportunities_panel = Panel(opportunities_text, title="🎯 Trade Opportunities", border_style="blue")

                # Create key levels panel
                key_levels = final_result.get('key_levels', {})
                levels_text = Text()
                levels_text.append("Key Price Levels:\n", style="bold yellow")
                if key_levels.get('support'):
                    support = key_levels['support']
                    if isinstance(support, (int, float)):
                        support_str = f"${support:.2f}"
                    else:
                        support_str = str(support)
                    levels_text.append(f"Support: {support_str}\n", style="green")
                if key_levels.get('resistance'):
                    resistance = key_levels['resistance']
                    if isinstance(resistance, (int, float)):
                        resistance_str = f"${resistance:.2f}"
                    else:
                        resistance_str = str(resistance)
                    levels_text.append(f"Resistance: {resistance_str}\n", style="red")

                levels_panel = Panel(levels_text, title="📊 Key Levels", border_style="green")

                # Print everything to console
                console.print()
                console.print(Panel.fit("✅ Market Analysis Complete!", border_style="green"))
                console.print(summary_table)
                console.print()
                console.print(opportunities_panel)
                console.print()
                console.print(levels_panel)
                console.print()

                # Log final metrics
                MetricsLogger.log_metrics(
                    "Analysis Summary",
                    {
                        'Total Duration': f"{total_time:.2f}s",
                        'Trade Opportunities': len(final_result['trade_opportunities']),
                        'Overall Confidence': f"{overall_confidence:.2%}" if isinstance(overall_confidence, (int, float)) else str(overall_confidence),
                        'Current Price': price_str if isinstance(current_price, (int, float)) else str(current_price),
                        'Market Structure': final_result.get('market_structure', {}).get('overall_bias', 'unknown').upper()
                    },
                    phase='analysis',
                    agent='analysis_agent'
                )

                plog.success(
                    f"Analysis complete: {len(final_result['trade_opportunities'])} opportunities found",
                    agent="analysis_agent"
                )
                
                await self.publish_activity(
                    action="analysis_complete",
                    message=f"Analysis complete: Found {len(final_result['trade_opportunities'])} opportunities",
                    phase="analysis",
                    severity="success",
                    metadata={
                        "opportunities": len(final_result['trade_opportunities']),
                        "confidence": final_result.get('overall_confidence', 0),
                        "regime": final_result.get('market_regime', {}).get('type', 'unknown')
                    }
                )


                # Cache result
                self.last_analysis[symbol] = final_result
                self.analysis_count += 1

                return final_result

            except Exception as e:
                plog.error(f"Error in market analysis: {e}", exception=e, agent="analysis_agent", phase="analysis")

                # Fallback to computational analysis only
                return await self._fallback_analysis(symbol, computational_results)

    async def _run_computational_analysis(
        self,
        candles: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        Run all computational analysis modules in parallel across ALL timeframes
        """

        # Convert candles to DataFrames
        dataframes = {}
        for tf, candle_list in candles.items():
            df = pd.DataFrame(candle_list)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            dataframes[tf] = df

        # Run analysis modules in parallel
        tasks = []

        # Indicators for each timeframe
        indicator_tasks = {
            tf: asyncio.create_task(self._calculate_indicators_async(df))
            for tf, df in dataframes.items()
        }

        # SMC analysis for ALL timeframes
        smc_tasks = {
            tf: asyncio.create_task(self._run_smc_async(df))
            for tf, df in dataframes.items()
            if len(df) > 50  # Only run if enough data
        }

        # ICT analysis for ALL timeframes
        ict_tasks = {
            tf: asyncio.create_task(self._run_ict_async(df))
            for tf, df in dataframes.items()
            if len(df) > 50
        }

        # Pattern recognition for ALL timeframes
        pattern_tasks = {
            tf: asyncio.create_task(self._run_patterns_async(df))
            for tf, df in dataframes.items()
            if len(df) > 30
        }

        # Wait for all to complete
        indicators = {}
        for tf, task in indicator_tasks.items():
            indicators[tf] = await task

        smc_results = {}
        for tf, task in smc_tasks.items():
            result = await task
            # Inject timeframe into results
            if result:
                self._inject_timeframe(result, tf)
            smc_results[tf] = result

        ict_results = {}
        for tf, task in ict_tasks.items():
            result = await task
            # Inject timeframe into results
            if result:
                self._inject_timeframe(result, tf)
            ict_results[tf] = result

        patterns = {}
        for tf, task in pattern_tasks.items():
            result = await task
            if result:
                self._inject_timeframe(result, tf)
            patterns[tf] = result

        # Multi-timeframe analysis
        mtf_analysis = self.mtf_analyzer.analyze(dataframes, indicators)

        return {
            'indicators': indicators,
            'smc': smc_results,
            'ict': ict_results,
            'patterns': patterns,
            'mtf_analysis': mtf_analysis
        }

    def _inject_timeframe(self, result: Dict[str, Any], tf: str):
        """Helper to inject timeframe into analysis results"""
        # SMC
        if 'order_blocks' in result:
            for item in result['order_blocks']:
                item['timeframe'] = tf
        if 'fair_value_gaps' in result:
            for item in result['fair_value_gaps']:
                item['timeframe'] = tf
        if 'break_of_structure' in result:
            result['break_of_structure']['timeframe'] = tf
            
        # ICT
        if 'liquidity_sweeps' in result:
            for item in result['liquidity_sweeps']:
                item['timeframe'] = tf
        if 'ote_zones' in result:
            result['ote_zones']['timeframe'] = tf
            
        # Patterns
        if 'patterns' in result:
            for item in result['patterns']:
                item['timeframe'] = tf

    async def _calculate_indicators_async(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate indicators (async wrapper)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.indicators_calc.calculate_all,
            df
        )

    async def _run_smc_async(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run SMC analysis (async wrapper)"""
        if df is None or len(df) < 50:
            return {}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.smc_detector.analyze,
            df
        )

    async def _run_ict_async(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run ICT analysis (async wrapper)"""
        if df is None or len(df) < 50:
            return {}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.ict_detector.analyze,
            df
        )
    
    async def _run_patterns_async(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run pattern recognition (async wrapper)"""
        if df is None or len(df) < 30:
            return {}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.pattern_recognizer.analyze,
            df
        )
    
    async def _run_regime_adaptive_analysis(
        self,
        candles: Dict[str, List[Dict]],
        computational_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run regime-adaptive analysis to enhance LLM context
        
        This provides professional quant trader insights:
        1. Market regime detection (trending/ranging/volatile)
        2. Optimal timeframe selection
        3. Confluence scoring across SMC/ICT/indicators
        4. Top-down analysis structure
        
        Returns:
            Enhanced analysis for LLM context
        """
        if not REGIME_ADAPTIVE_AVAILABLE or not self.regime_detector:
            plog.debug("Regime-adaptive framework not available, skipping", agent="analysis_agent")
            return {}
        
        try:
            # Safety check for empty candles
            if not candles:
                plog.warning("No candles provided for regime analysis", agent="analysis_agent")
                return {}
                
            # Use 1H timeframe for regime detection
            tf = '1h' if '1h' in candles else list(candles.keys())[0]
            
            # Convert to DataFrame
            df = pd.DataFrame(candles[tf])
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            
            # Get indicators for this timeframe
            indicators = computational_results['indicators'].get(tf, {})
            
            # 1. Detect Market Regime
            regime = self.regime_detector.detect(df, indicators)
            
            # 2. Select Optimal Timeframes
            tf_strategy = self.timeframe_selector.select_timeframes(regime, trading_style='swing')
            
            # 3. Determine HTF Bias (with MSS detection)
            htf_bias = self._determine_htf_bias(
                candles, 
                computational_results['indicators'], 
                tf_strategy.primary_timeframes,
                computational_results['smc']  # Pass SMC results for MSS detection
            )
            
            # Determine direction based on HTF bias and Regime
            direction = 'NEUTRAL'
            if htf_bias == 'BULLISH':
                direction = 'LONG'
            elif htf_bias == 'BEARISH':
                direction = 'SHORT'
            elif regime.regime == 'TRENDING_BULLISH':
                direction = 'LONG'
            elif regime.regime == 'TRENDING_BEARISH':
                direction = 'SHORT'

            # 4. Score Confluences
            # Flatten results for scorer (it expects lists of all OBs, etc.)
            flat_smc = self._flatten_results(computational_results['smc'])
            flat_ict = self._flatten_results(computational_results['ict'])
            flat_patterns = self._flatten_results(computational_results['patterns'])
            
            # Use indicators from the primary timeframe for scoring
            primary_tf = tf_strategy.primary_timeframes[0] if tf_strategy.primary_timeframes else tf
            scoring_indicators = computational_results['indicators'].get(primary_tf, indicators)

            confluence_score = self.confluence_scorer.score_setup(
                smc_analysis=flat_smc,
                ict_analysis=flat_ict,
                indicators=scoring_indicators,
                patterns=flat_patterns,
                market_structure={'htf_trend': htf_bias.lower(), 'mtf_trend': htf_bias.lower()},
                direction=direction,
                minimum_required=3
            )
            
            # Build enhanced analysis
            regime_analysis = {
                'regime': {
                    'type': regime.regime,
                    'confidence': regime.confidence,
                    'trend_strength': regime.trend_strength,
                    'volatility_level': regime.volatility_level,
                    'reasoning': regime.reasoning
                },
                'timeframe_strategy': {
                    'primary': tf_strategy.primary_timeframes,
                    'secondary': tf_strategy.secondary_timeframes,
                    'avoid': tf_strategy.avoid_timeframes,
                    'reasoning': tf_strategy.reasoning
                },
                'htf_bias': htf_bias,
                'confluence': {
                    'count': confluence_score.confluence_count,
                    'total_score': confluence_score.total_score,
                    'quality_rating': confluence_score.quality_rating,
                    'meets_minimum': confluence_score.meets_minimum,
                    'by_category': confluence_score.by_category,
                    'details': [
                        {
                            'factor': c.factor,
                            'category': c.category,
                            'weight': c.weight,
                            'description': c.description
                        }
                        for c in confluence_score.confluences
                    ]
                },
                'professional_insights': {
                    'top_down_approach': f"HTF Bias: {htf_bias} → Focus on {', '.join(tf_strategy.primary_timeframes)} for structure",
                    'risk_assessment': f"Regime: {regime.regime} requires {confluence_score.confluence_count} confluences (minimum: 3)",
                    'recommended_action': 'ANALYZE' if confluence_score.meets_minimum else 'WAIT_FOR_BETTER_SETUP'
                }
            }
            
            plog.info(
                f"Regime-adaptive analysis: {regime.regime} ({confluence_score.confluence_count} confluences)",
                agent="analysis_agent"
            )
            
            return regime_analysis
            
        except Exception as e:
            plog.error(f"Error in regime-adaptive analysis: {e}", exception=e, agent="analysis_agent")
            return {}

    def _flatten_results(self, nested_results: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten nested timeframe results into single lists for scoring"""
        flat = {
            'order_blocks': [],
            'fair_value_gaps': [],
            'break_of_structure': {'detected': False},
            'liquidity_sweeps': [],
            'ote_zones': {'in_zone': False},
            'patterns': []
        }
        
        for tf, result in nested_results.items():
            if not result:
                continue
                
            # SMC
            if 'order_blocks' in result:
                flat['order_blocks'].extend(result['order_blocks'])
            if 'fair_value_gaps' in result:
                flat['fair_value_gaps'].extend(result['fair_value_gaps'])
            if 'break_of_structure' in result:
                # If any TF has BOS, mark as detected (simplified)
                if result['break_of_structure'].get('bos'):
                    flat['break_of_structure'] = result['break_of_structure']
                    flat['break_of_structure']['detected'] = True
            
            # ICT
            if 'liquidity_sweeps' in result:
                flat['liquidity_sweeps'].extend(result['liquidity_sweeps'])
            if 'ote_zones' in result:
                if result['ote_zones'].get('in_ote_zone'):
                    flat['ote_zones'] = result['ote_zones']
                    flat['ote_zones']['in_zone'] = True
            if 'killzone' in result:
                # Use the most relevant killzone info (usually from 1H or 15M)
                if result['killzone'].get('current_killzone') != 'none':
                    flat['killzone'] = result['killzone']
            
            # Patterns
            if 'patterns' in result:
                flat['patterns'].extend(result['patterns'])
                
        return flat
    
    def _determine_htf_bias(
        self,
        candles: Dict[str, List[Dict]],
        indicators: Dict[str, Dict[str, Any]],
        htf_timeframes: List[str],
        smc_results: Dict[str, Any] = None
    ) -> str:
        """
        Determine higher timeframe bias with Market Structure Shift (MSS) priority
        
        Professional Enhancement:
        1. Check for MSS (Break of Structure) first - early trend change detection
        2. Fall back to EMA alignment if no MSS detected
        
        MSS Logic:
        - Bullish BOS (price breaks major swing high) → BULLISH bias immediately
        - Bearish BOS (price breaks major swing low) → BEARISH bias immediately
        """
        
        # PRIORITY 1: Check for Market Structure Shift (MSS)
        if smc_results:
            for tf in htf_timeframes:
                if tf in smc_results and smc_results[tf]:
                    bos_data = smc_results[tf].get('break_of_structure', {})
                    
                    # Check for Bullish BOS
                    bos_list = bos_data.get('bos', [])
                    if bos_list:
                        for bos in bos_list:
                            if bos.get('type') == 'bullish_bos':
                                plog.info(
                                    f"MSS detected: Bullish BOS on {tf} at {bos.get('level')} - Overriding EMA bias",
                                    agent="analysis_agent"
                                )
                                return 'BULLISH'
                            elif bos.get('type') == 'bearish_bos':
                                plog.info(
                                    f"MSS detected: Bearish BOS on {tf} at {bos.get('level')} - Overriding EMA bias",
                                    agent="analysis_agent"
                                )
                                return 'BEARISH'
                    
                    # Check CHoCH (Change of Character) as secondary MSS signal
                    choch_list = bos_data.get('choch', [])
                    if choch_list:
                        for choch in choch_list:
                            if choch.get('type') == 'bullish_choch':
                                plog.info(
                                    f"MSS detected: Bullish CHoCH on {tf} - Potential trend reversal to BULLISH",
                                    agent="analysis_agent"
                                )
                                return 'BULLISH'
                            elif choch.get('type') == 'bearish_choch':
                                plog.info(
                                    f"MSS detected: Bearish CHoCH on {tf} - Potential trend reversal to BEARISH",
                                    agent="analysis_agent"
                                )
                                return 'BEARISH'
        
        # PRIORITY 2: Fall back to EMA alignment (original logic)
        for tf in htf_timeframes:
            if tf in candles and tf in indicators:
                inds = indicators[tf]
                current_price = candles[tf][-1]['close']
                
                # Get EMA values - handle both scalar and Series
                ema_21 = inds.get('ema_21')
                ema_50 = inds.get('ema_50')
                ema_200 = inds.get('ema_200')
                
                # Extract scalar values if Series
                if hasattr(ema_21, 'iloc'):
                    ema_21 = ema_21.iloc[-1] if len(ema_21) > 0 else None
                if hasattr(ema_50, 'iloc'):
                    ema_50 = ema_50.iloc[-1] if len(ema_50) > 0 else None
                if hasattr(ema_200, 'iloc'):
                    ema_200 = ema_200.iloc[-1] if len(ema_200) > 0 else None
                
                if ema_21 is not None and ema_50 is not None and ema_200 is not None:
                    # Bullish: price > EMA21 > EMA50 > EMA200
                    if current_price > ema_21 > ema_50 > ema_200:
                        return 'BULLISH'
                    # Bearish: price < EMA21 < EMA50 < EMA200
                    elif current_price < ema_21 < ema_50 < ema_200:
                        return 'BEARISH'
        
        return 'NEUTRAL'


    async def _handle_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle direct analysis request"""
        try:
            symbol = payload['symbol']

            plog.debug(f"Processing direct analysis request for {symbol}", agent="analysis_agent")
            
            # Get latest data from state
            candles = await self._fetch_latest_candles(symbol)

            analysis_result = await self.analyze_market(
                symbol=symbol,
                candles=candles
            )

            return {"status": "success", "analysis": analysis_result}

        except Exception as e:
            plog.error(f"Error in analysis request: {e}", exception=e, agent="analysis_agent")
            return {"status": "error", "message": str(e)}

    async def _call_llm_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call LLM for deep analysis with intelligent caching
        
        Uses cache to avoid redundant API calls for similar market conditions.
        This can save ~60% of LLM costs by caching responses for 5 minutes.
        
        Includes retry logic and error handling with fallback sequence:
        OpenRouter DeepSeek -> Claude Sonnet 4.5 -> Groq Llama
        """
        
        # CRITICAL FIX: Use cache to avoid redundant LLM calls
        async def _perform_llm_call(ctx: Dict[str, Any]) -> Dict[str, Any]:
            """Inner function that performs the actual LLM call"""
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    # Policy: best PREMIUM model first (Claude), then the OpenRouter
                    # open-source fallback (DeepSeek, free), then Groq. Runs on an
                    # OpenRouter key alone; upgrades to Claude when its key is added.
                    # Single source of truth: src/utils/llm_router.py.
                    if self.config.llm.anthropic_api_key:
                        plog.info("Using Claude for LLM analysis (premium)", agent="analysis_agent", phase="llm_analysis")
                        return await self._call_claude_analysis(ctx)

                    # Fallback to OpenRouter open-source model
                    elif self.openrouter_client:
                        plog.info("Using OpenRouter open-source model for LLM analysis (fallback)", agent="analysis_agent", phase="llm_analysis")
                        return await self._call_openrouter_analysis(ctx)

                    # Final fallback to Groq
                    elif self.groq_client:
                        plog.warning("Using Groq Llama for LLM analysis (fallback)", agent="analysis_agent")
                        return await self._call_groq_analysis(ctx)

                    else:
                        raise Exception("No LLM API keys configured")

                except Exception as e:
                    plog.error(f"LLM API error (attempt {retry_count + 1}/{max_retries}): {e}", 
                              exception=e, agent="analysis_agent", phase="llm_analysis")
                    retry_count += 1

                    if retry_count < max_retries:
                        # Try fallback sequence: OpenRouter -> Claude -> Groq
                        if self.openrouter_client and self.config.llm.anthropic_api_key:
                            plog.warning("Attempting fallback to Claude Sonnet 4.5", agent="analysis_agent")
                            try:
                                return await self._call_claude_analysis(ctx)
                            except Exception as fallback_e:
                                plog.error(f"Claude fallback failed: {fallback_e}", exception=fallback_e, agent="analysis_agent")
                                if self.groq_client:
                                    plog.warning("Attempting final fallback to Groq Llama", agent="analysis_agent")
                                    try:
                                        return await self._call_groq_analysis(ctx)
                                    except Exception as groq_e:
                                        plog.error(f"Groq fallback failed: {groq_e}", exception=groq_e, agent="analysis_agent")
                                        await asyncio.sleep(2 ** retry_count)
                                else:
                                    await asyncio.sleep(2 ** retry_count)
                        elif self.openrouter_client and self.groq_client:
                            plog.warning("Attempting fallback to Groq Llama", agent="analysis_agent")
                            try:
                                return await self._call_groq_analysis(ctx)
                            except Exception as groq_e:
                                plog.error(f"Groq fallback failed: {groq_e}", exception=groq_e, agent="analysis_agent")
                                await asyncio.sleep(2 ** retry_count)
                        elif self.config.llm.anthropic_api_key and self.groq_client:
                            logger.warning("Trying Groq Llama fallback after Claude failed")
                            try:
                                return await self._call_groq_analysis(ctx)
                            except Exception as groq_e:
                                logger.error(f"Groq fallback failed: {groq_e}")
                                await asyncio.sleep(2 ** retry_count)
                        else:
                            await asyncio.sleep(2 ** retry_count)
                    else:
                        raise Exception("Max retries exceeded for LLM analysis")

            raise Exception("Max retries exceeded for LLM analysis")
        
        # Use cache - this will either return cached response or call _perform_llm_call
        return await analysis_llm_cache.get_or_compute(context, _perform_llm_call)


    def _make_serializable(self, obj):
        """Convert NumPy and Pandas types to native Python types for JSON serialization"""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return int(obj)  # Convert numpy bool to int (0 or 1) for JSON safety
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.Series):
            return obj.replace({np.nan: None}).tolist()
        elif isinstance(obj, pd.DataFrame):
            return obj.replace({np.nan: None}).to_dict(orient='records')
        elif isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        else:
            return obj

    async def _call_claude_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call Claude Sonnet 4.5 for analysis"""
        plog.method_entry("_call_claude_analysis", agent="analysis_agent")
        
        # Prepare messages
        system_prompt = context['system_prompt']

        # Convert NumPy types to native Python types
        safe_context = self._make_serializable(context)

        # Safe JSON encoder that handles edge cases
        class SafeJSONEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, (np.bool_, bool)):
                    return str(o)
                elif isinstance(o, (np.integer, np.floating)):
                    return float(o)
                return str(o)

        user_message = f"""
Analyze the following market data:

## Current Market Data
{json.dumps(safe_context['current_data'], indent=2, cls=SafeJSONEncoder)}

## Technical Indicators
{json.dumps(safe_context['indicators'], indent=2, cls=SafeJSONEncoder)}

## Smart Money Concepts Analysis
{json.dumps(safe_context['smc_analysis'], indent=2, cls=SafeJSONEncoder)}

## ICT Methodology Analysis
{json.dumps(safe_context['ict_analysis'], indent=2, cls=SafeJSONEncoder)}

## Chart Patterns
{json.dumps(safe_context['patterns'], indent=2, cls=SafeJSONEncoder)}

## Historical Context
{json.dumps(safe_context['historical_context'], indent=2, cls=SafeJSONEncoder)}

{safe_context['task_instructions']}
"""

        # Log the context being sent to LLM
        plog.debug(
            f"Sending context to Claude (context_size: {len(user_message)} chars, system_prompt: {len(system_prompt)} chars)",
            agent="analysis_agent",
            phase="llm_analysis"
        )

        try:
            response = await self.llm_client.messages.create(
                model=self.config.llm.claude_model,
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3  # Low temperature for analytical consistency
            )

            # Extract response
            response_text = response.content[0].text

            plog.debug(
                f"Received response from Claude (length: {len(response_text)} chars)",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Parse JSON response
            analysis = self._parse_llm_response(response_text)

            # Log token usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            plog.info(
                f"Claude Sonnet 4.5 - {input_tokens:,} input + {output_tokens:,} output tokens",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Track costs
            await self._track_llm_cost(input_tokens, output_tokens, provider="claude")

            plog.method_exit("_call_claude_analysis", result=f"Parsed {len(analysis)} response fields")
            return analysis
            
        except Exception as e:
            plog.error(f"Claude API call failed: {e}", exception=e, agent="analysis_agent", phase="llm_analysis")
            plog.method_exit("_call_claude_analysis", result=f"FAILED: {str(e)}")
            raise

    async def _call_openrouter_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call OpenRouter DeepSeek for analysis (fallback)"""
        plog.method_entry("_call_openrouter_analysis", agent="analysis_agent")
        
        # Prepare messages
        system_prompt = context['system_prompt']

        # Convert NumPy types to native Python types
        safe_context = self._make_serializable(context)

        # Safe JSON encoder that handles edge cases
        class SafeJSONEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, (np.bool_, bool)):
                    return str(o)
                elif isinstance(o, (np.integer, np.floating)):
                    return float(o)
                return str(o)

        user_message = f"""
Analyze the following market data:

## Current Market Data
{json.dumps(safe_context['current_data'], indent=2, cls=SafeJSONEncoder)}

## Technical Indicators
{json.dumps(safe_context['indicators'], indent=2, cls=SafeJSONEncoder)}

## Smart Money Concepts Analysis
{json.dumps(safe_context['smc_analysis'], indent=2, cls=SafeJSONEncoder)}

## ICT Methodology Analysis
{json.dumps(safe_context['ict_analysis'], indent=2, cls=SafeJSONEncoder)}

## Chart Patterns
{json.dumps(safe_context['patterns'], indent=2, cls=SafeJSONEncoder)}

## Historical Context
{json.dumps(safe_context['historical_context'], indent=2, cls=SafeJSONEncoder)}

{safe_context['task_instructions']}
"""

        plog.debug(
            f"Sending context to OpenRouter DeepSeek (context_size: {len(user_message)} chars)",
            agent="analysis_agent",
            phase="llm_analysis"
        )

        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.config.llm.deepseek_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=20000,
                temperature=0.3
            )

            # Extract response
            response_text = response.choices[0].message.content

            plog.debug(
                f"Received response from OpenRouter DeepSeek (length: {len(response_text)} chars)",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Parse JSON response
            analysis = self._parse_llm_response(response_text)

            # Log token usage (approximate)
            input_tokens = len(user_message.split()) + len(system_prompt.split())
            output_tokens = len(response_text.split())
            plog.info(
                f"OpenRouter DeepSeek - ~{input_tokens:,} input + ~{output_tokens:,} output tokens",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Track costs (DeepSeek is free tier, minimal cost)
            await self._track_llm_cost(input_tokens, output_tokens, provider="openrouter")

            plog.method_exit("_call_openrouter_analysis", result=f"Parsed {len(analysis)} response fields")
            return analysis
            
        except Exception as e:
            plog.error(f"OpenRouter API call failed: {e}", exception=e, agent="analysis_agent", phase="llm_analysis")
            plog.method_exit("_call_openrouter_analysis", result=f"FAILED: {str(e)}")
            raise

    async def _call_groq_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call Groq Llama for analysis (final fallback)"""
        plog.method_entry("_call_groq_analysis", agent="analysis_agent")
        
        # Prepare messages
        system_prompt = context['system_prompt']

        # Convert NumPy types to native Python types.
        # FIX: previously called self._convert_numpy_types(), which does not exist,
        # so the Groq "final fallback" always raised AttributeError before making a
        # request - collapsing the intended 3-tier chain (OpenRouter -> Claude ->
        # Groq) into effectively 2 tiers. Use the same serializer as the other tiers.
        safe_context = self._make_serializable(context)

        # Safe JSON encoder that handles edge cases
        class SafeJSONEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, (np.bool_, bool)):
                    return str(o)
                elif isinstance(o, (np.integer, np.floating)):
                    return float(o)
                return str(o)

        user_message = f"""
Analyze the following market data:

## Current Market Data
{json.dumps(safe_context['current_data'], indent=2, cls=SafeJSONEncoder)}

## Technical Indicators
{json.dumps(safe_context['indicators'], indent=2, cls=SafeJSONEncoder)}

## Smart Money Concepts Analysis
{json.dumps(safe_context['smc_analysis'], indent=2, cls=SafeJSONEncoder)}

## ICT Methodology Analysis
{json.dumps(safe_context['ict_analysis'], indent=2, cls=SafeJSONEncoder)}

## Chart Patterns
{json.dumps(safe_context['patterns'], indent=2, cls=SafeJSONEncoder)}

## Historical Context
{json.dumps(safe_context['historical_context'], indent=2, cls=SafeJSONEncoder)}

{safe_context['task_instructions']}
"""

        plog.debug(
            f"Sending context to Groq Llama (context_size: {len(user_message)} chars)",
            agent="analysis_agent",
            phase="llm_analysis"
        )

        try:
            response = self.groq_client.chat.completions.create(
                model=self.config.llm.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=4000,
                temperature=0.3
            )

            # Extract response
            response_text = response.choices[0].message.content

            plog.debug(
                f"Received response from Groq Llama (length: {len(response_text)} chars)",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Parse JSON response
            analysis = self._parse_llm_response(response_text)

            # Log token usage (approximate)
            input_tokens = len(user_message.split()) + len(system_prompt.split())
            output_tokens = len(response_text.split())
            plog.info(
                f"Groq Llama - ~{input_tokens:,} input + ~{output_tokens:,} output tokens",
                agent="analysis_agent",
                phase="llm_analysis"
            )

            # Track costs (free tier)
            await self._track_llm_cost(input_tokens, output_tokens, provider="groq")

            plog.method_exit("_call_groq_analysis", result=f"Parsed {len(analysis)} response fields")
            return analysis
            
        except Exception as e:
            plog.error(f"Groq API call failed: {e}", exception=e, agent="analysis_agent", phase="llm_analysis")
            plog.method_exit("_call_groq_analysis", result=f"FAILED: {str(e)}")
            raise

    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate LLM response"""
        plog.debug(f"Parsing LLM response (length: {len(response_text)} chars)", agent="analysis_agent", phase="llm_analysis")

        # Try to extract JSON from response.
        # Sometimes the LLM wraps JSON in markdown code blocks, and sometimes the
        # closing fence is missing (truncated/streamed tails). find() returns -1 when
        # the closing ``` is absent; slicing response_text[start:-1] would silently
        # drop the final char and guarantee a JSONDecodeError. Guard json_end == -1
        # and take the remainder instead (mirrors strategy_agent._parse_llm_response).
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            if json_end != -1:
                json_str = response_text[json_start:json_end].strip()
            else:
                json_str = response_text[json_start:].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            if json_end != -1:
                json_str = response_text[json_start:json_end].strip()
            else:
                json_str = response_text[json_start:].strip()
        else:
            json_str = response_text.strip()

        plog.debug(f"Extracted JSON string (length: {len(json_str)} chars)", agent="analysis_agent")

        # Parse JSON
        try:
            analysis = json.loads(json_str)
            plog.debug(f"Successfully parsed JSON with {len(analysis)} fields", agent="analysis_agent")
        except json.JSONDecodeError as e:
            plog.error(f"Failed to parse JSON: {e}", exception=e, agent="analysis_agent", phase="llm_analysis")
            raise

        # Sanitize the response to ensure correct data types
        analysis = self._sanitize_llm_response(analysis)

        # Validate required fields
        required_fields = [
            'market_structure',
            'key_levels',
            'smc_confluences',
            'ict_setup',
            'trade_opportunities',
            'reasoning'
        ]

        missing_fields = []
        for field in required_fields:
            if field not in analysis:
                missing_fields.append(field)
                analysis[field] = {}

        if missing_fields:
            plog.warning(f"Missing fields in LLM response: {', '.join(missing_fields)}", agent="analysis_agent")

        return analysis

    def _sanitize_llm_response(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize LLM response to ensure proper data types and prevent formatting errors"""
        sanitized = {}

        for key, value in analysis.items():
            if isinstance(value, dict):
                sanitized[key] = self._sanitize_llm_response(value)
            elif isinstance(value, list):
                # Ensure list items are properly sanitized
                sanitized[key] = [self._sanitize_value(item) for item in value]
            else:
                sanitized[key] = self._sanitize_value(value)

        return sanitized

    def _sanitize_value(self, value):
        """Sanitize individual values to prevent formatting errors"""
        if isinstance(value, (int, float)):
            return value
        elif isinstance(value, str):
            return value
        elif isinstance(value, bool):
            return value
        elif value is None:
            return None
        elif isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        else:
            # Convert any other type to string to prevent formatting issues
            return str(value)

    def _synthesize_results(
        self,
        symbol: str,
        computational: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        order_book: Optional[Dict],
        funding_rate: Optional[Dict],
        candles: Dict[str, List[Dict]],
        regime_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Synthesize computational and LLM results into final analysis
        """
        plog.method_entry("_synthesize_results", agent="analysis_agent")
        plog.debug(f"Synthesizing results for {symbol}", agent="analysis_agent")

        # Get current price from latest available candle.
        # NEVER substitute a hardcoded constant: a BTC-scale default (e.g. 43000)
        # applied to an arbitrary symbol (SOL, DOGE, ...) would fabricate a wildly
        # wrong price and could drive real (testnet) order sizing/SL/TP. If no
        # candle price is available, fail the cycle with a neutral no-setup result.
        current_price = None
        for tf in ('5m', '1h', '15m', '1m', '4h', '1d'):
            tf_candles = candles.get(tf)
            if tf_candles and len(tf_candles) > 0:
                last_close = tf_candles[-1].get('close')
                if isinstance(last_close, (int, float)) and last_close > 0:
                    current_price = float(last_close)
                    break

        if current_price is None:
            plog.error(
                f"No valid current price found for {symbol} in any timeframe; "
                f"returning neutral no-setup result instead of fabricating a price.",
                agent="analysis_agent",
                phase="results_compilation"
            )
            return {
                'symbol': symbol,
                'timestamp': datetime.utcnow().isoformat(),
                'analysis_id': f"{symbol}_nosetup_{int(datetime.utcnow().timestamp())}",
                'current_price': None,
                'market_regime': {
                    'type': 'UNKNOWN',
                    'confidence': 0.0,
                    'trend_strength': 0.0,
                    'volatility_level': 'medium',
                    'reasoning': 'No price data available'
                },
                'market_structure': {'overall_bias': 'unknown'},
                'key_levels': {},
                'smc_analysis': {},
                'ict_analysis': {},
                'patterns': {},
                'mtf_analysis': {},
                'trade_opportunities': [],
                'overall_confidence': 0.0,
                'reasoning': 'No valid price data available - skipping cycle',
                'is_fallback': True
            }

        plog.debug(f"Current price: ${current_price:.2f}", agent="analysis_agent")

        # Sanitize computational results for JSON serialization
        computational = self._make_serializable(computational)

        # Extract market_regime from regime_analysis (required by Pydantic model)
        market_regime = {}
        if regime_analysis and 'regime' in regime_analysis:
            market_regime = regime_analysis['regime']
        else:
            # Provide default market_regime structure
            market_regime = {
                'type': 'UNKNOWN',
                'confidence': 0.0,
                'trend_strength': 0.0,
                'volatility_level': 'medium',
                'reasoning': 'Regime detection not available'
            }

        result = {
            'symbol': symbol,
            'timestamp': datetime.utcnow().isoformat(),
            'analysis_id': f"{symbol}_{int(datetime.utcnow().timestamp())}",
            'current_price': current_price,
            
            # Market regime (required by Pydantic model)
            'market_regime': market_regime,
            
            # Regime-adaptive analysis (full analysis for reference)
            'regime_adaptive_analysis': regime_analysis,

            # Market structure from LLM
            'market_structure': llm_analysis.get('market_structure', {}),

            # Key levels
            'key_levels': llm_analysis.get('key_levels', {}),

            # SMC analysis (computational + LLM interpretation)
            'smc_analysis': {
                'computational': computational['smc'],
                'llm_interpretation': llm_analysis.get('smc_confluences', [])
            },

            # ICT analysis
            'ict_analysis': {
                'computational': computational['ict'],
                'llm_interpretation': llm_analysis.get('ict_setup', {})
            },

            # Patterns
            'patterns': computational['patterns'],

            # Multi-timeframe analysis
            'mtf_analysis': computational['mtf_analysis'],

            # Trade opportunities (from LLM)
            'trade_opportunities': llm_analysis.get('trade_opportunities', []),

            # Overall confidence
            'overall_confidence': self._calculate_overall_confidence(llm_analysis),

            # Additional context
            'order_book_snapshot': order_book,
            'funding_rate': funding_rate,

            # Reasoning
            'reasoning': llm_analysis.get('reasoning', ''),

            # Raw data for reference
            '_raw_llm': llm_analysis,
            '_raw_computational': computational
        }

        plog.method_exit("_synthesize_results", result=f"{len(result['trade_opportunities'])} opportunities")
        return result

    def _calculate_overall_confidence(self, llm_analysis: Dict[str, Any]) -> float:
        """Calculate overall confidence from LLM analysis"""
        opportunities = llm_analysis.get('trade_opportunities', [])

        if not opportunities:
            return 0.0

        # Average confidence of all opportunities
        confidences = []
        for opp in opportunities:
            confidence = opp.get('confidence', 0)
            if isinstance(confidence, (int, float)):
                confidences.append(confidence)
            else:
                # Try to convert string to float if possible
                try:
                    confidences.append(float(confidence))
                except (ValueError, TypeError):
                    confidences.append(0.0)

        return sum(confidences) / len(confidences) if confidences else 0.0

    def _build_cache_discriminator(
        self,
        computational_results: Dict[str, Any],
        candles: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        Build the `computational_analysis` sub-tree that LLMResponseCache reads to
        derive its cache key. Shapes real values into the exact nested structure the
        cache reader expects so that identical market snapshots produce identical keys
        (cache hit) while distinct symbols/timeframes/candle windows produce different
        keys (no collision).

        The last-candle timestamps are folded into the `mtf_analysis.overall_bias`
        discriminator so a new candle (same structural counts) still invalidates the
        cache within the TTL window.
        """
        smc = computational_results.get('smc', {}) or {}
        ict = computational_results.get('ict', {}) or {}
        indicators = computational_results.get('indicators', {}) or {}
        mtf = computational_results.get('mtf_analysis', {}) or {}

        # Aggregate structural counts across all timeframes.
        order_blocks = sum(
            len((tf_data or {}).get('order_blocks', []))
            for tf_data in smc.values() if isinstance(tf_data, dict)
        )
        fvgs = sum(
            len((tf_data or {}).get('fair_value_gaps', []))
            for tf_data in smc.values() if isinstance(tf_data, dict)
        )
        bos_count = sum(
            1 for tf_data in smc.values()
            if isinstance(tf_data, dict)
            and (tf_data.get('break_of_structure', {}) or {}).get('bos', False)
        )
        in_killzone = any(
            (tf_data or {}).get('killzone', {}).get('current_killzone', 'none') != 'none'
            for tf_data in ict.values() if isinstance(tf_data, dict)
        )
        sweep_detected = any(
            len((tf_data or {}).get('liquidity_sweeps', [])) > 0
            for tf_data in ict.values() if isinstance(tf_data, dict)
        )

        # Fold per-timeframe last-candle timestamps into the bias discriminator so the
        # key changes when the candle window advances.
        last_ts = {}
        for tf, candle_list in candles.items():
            if isinstance(candle_list, list) and candle_list:
                last = candle_list[-1]
                if isinstance(last, dict):
                    last_ts[tf] = last.get('timestamp')
        overall_bias = f"{mtf.get('overall_bias', 'neutral')}|{sorted(last_ts.items())}"

        # RSI/trend from the primary (first) timeframe's indicators, if present.
        primary_inds = {}
        if isinstance(indicators, dict):
            for tf_inds in indicators.values():
                if isinstance(tf_inds, dict):
                    primary_inds = tf_inds
                    break
        rsi = primary_inds.get('rsi_14', 0)
        if hasattr(rsi, 'iloc'):
            rsi = rsi.iloc[-1] if len(rsi) > 0 else 0
        try:
            rsi = float(rsi)
        except (ValueError, TypeError):
            rsi = 0.0

        return {
            'mtf_analysis': {'overall_bias': overall_bias},
            'smc_analysis': {
                'order_blocks': [None] * order_blocks,      # len() is what the reader uses
                'fair_value_gaps': [None] * fvgs,
                'bos_count': bos_count,
            },
            'ict_analysis': {
                'in_killzone': in_killzone,
                'sweep_detected': sweep_detected,
            },
            'indicators': {
                'rsi_14': rsi,
                'trend': primary_inds.get('trend', 'neutral'),
            },
        }

    async def _fallback_analysis(
        self,
        symbol: str,
        computational_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback analysis using only computational results
        (when LLM fails)
        """
        plog.warning("Falling back to computational analysis only (LLM unavailable)", agent="analysis_agent", phase="analysis")

        return {
            'symbol': symbol,
            'timestamp': datetime.utcnow().isoformat(),
            'analysis_id': f"{symbol}_fallback_{int(datetime.utcnow().timestamp())}",
            'market_structure': {'overall_bias': 'unknown'},
            'key_levels': {},
            'smc_analysis': computational_results.get('smc', {}),
            'ict_analysis': computational_results.get('ict', {}),
            'patterns': computational_results.get('patterns', {}),
            'mtf_analysis': computational_results.get('mtf_analysis', {}),
            'trade_opportunities': [],
            'overall_confidence': 0.0,
            'reasoning': 'Fallback analysis - LLM unavailable',
            'is_fallback': True
        }

    async def _get_historical_trades(self, symbol: str, limit: int = 20) -> List[Dict]:
        """
        PHASE 3 FIX: Fetch historical trades for context from Memory Agent
        
        This provides the LLM with recent trading history to improve analysis quality.
        Includes similar setups, win rates, and lessons learned.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            limit: Maximum number of trades to retrieve
            
        Returns:
            List of historical trade records with outcomes
        """
        try:
            plog.debug(
                f"Fetching {limit} historical trades for {symbol} from Memory Agent",
                agent="analysis_agent"
            )
            
            # Try to get from state manager first (cached)
            cache_key = f"historical_trades:{symbol}:{limit}"
            cached_trades = await self.state_manager.get(cache_key)
            
            if cached_trades:
                plog.debug(
                    f"Using cached historical trades ({len(cached_trades)} trades)",
                    agent="analysis_agent"
                )
                return cached_trades
            
            # Query Memory Agent via message bus
            try:
                response_received = asyncio.Event()
                response_data = {}
                
                async def response_handler(message: Dict[str, Any]):
                    nonlocal response_data
                    response_data = message
                    response_received.set()
                
                # Subscribe to memory agent response channel temporarily
                response_channel = "analysis_agent_memory_response"
                await self.message_bus.subscribe(response_channel, response_handler)
                
                # Send request to Memory Agent
                await self.send_message(
                    receiver="memory_agent",
                    message_type="get_recent_trades",
                    payload={
                        "symbol": symbol,
                        "limit": limit,
                        "response_channel": response_channel
                    },
                    priority=7
                )
                
                # Wait for response with timeout
                try:
                    await asyncio.wait_for(response_received.wait(), timeout=5.0)
                    
                    # Unsubscribe from response channel
                    await self.message_bus.unsubscribe(response_channel, response_handler)
                    
                    if response_data.get('success'):
                        trades = response_data.get('trades', [])
                        
                        # Cache for 60 seconds
                        await self.state_manager.set(cache_key, trades, ttl=60)
                        
                        plog.success(
                            f"Retrieved {len(trades)} historical trades from Memory Agent",
                            agent="analysis_agent"
                        )
                        return trades
                    else:
                        plog.warning(
                            f"Memory Agent returned no trades: {response_data.get('message')}",
                            agent="analysis_agent"
                        )
                        return []
                        
                except asyncio.TimeoutError:
                    plog.warning(
                        "Timeout waiting for Memory Agent response - proceeding without historical context",
                        agent="analysis_agent"
                    )
                    await self.message_bus.unsubscribe(response_channel, response_handler)
                    return []
                    
            except Exception as e:
                plog.error(
                    f"Error querying Memory Agent: {e}",
                    exception=e,
                    agent="analysis_agent"
                )
                return []
                
        except Exception as e:
            plog.error(
                f"Error in _get_historical_trades: {e}",
                exception=e,
                agent="analysis_agent"
            )
            return []

    async def _fetch_latest_candles(self, symbol: str) -> Dict[str, List[Dict]]:
        """Fetch latest candles from state/cache"""
        # Implementation depends on your state management
        return {}

    async def _track_llm_cost(self, input_tokens: int, output_tokens: int, provider: str = "claude"):
        """Track LLM API costs"""
        if provider == "claude":
            # Claude Sonnet 4.5 pricing (as of 2024)
            input_cost = (input_tokens / 1000) * 0.003
            output_cost = (output_tokens / 1000) * 0.015
            total_cost = input_cost + output_cost
        elif provider == "openrouter":
            # DeepSeek free tier - minimal cost
            total_cost = 0.0
        elif provider == "groq":
            # Groq free tier - no cost
            total_cost = 0.0
        else:
            total_cost = 0.0

        # Store in state for monitoring
        daily_cost = await self.state_manager.get('daily_llm_cost') or 0.0
        await self.state_manager.set('daily_llm_cost', daily_cost + total_cost)

        plog.debug(
            f"{provider.upper()} cost: ${total_cost:.4f} (daily total: ${daily_cost + total_cost:.2f})",
            agent="analysis_agent",
            phase="llm_analysis"
        )

    async def process_message(self, message: AgentMessage) -> Dict[str, Any]:
        """
        Process incoming messages
        
        PHASE 2 FIX: Now sends responses back to orchestrator for sequential execution
        """
        # CRITICAL FIX: Log all incoming messages
        plog.info(
            f"📨 Analysis Agent received message: type='{message.type}', sender='{message.sender}'",
            agent="analysis_agent"
        )
        plog.debug(
            f"📨 Available handlers: {list(self.handlers.keys())}",
            agent="analysis_agent"
        )
        
        # Extract correlation_id from message
        correlation_id = getattr(message, 'correlation_id', None) or message.payload.get('correlation_id')
        
        handler = self.handlers.get(message.type)
        if handler:
            plog.info(
                f"✅ Found handler for '{message.type}', executing...",
                agent="analysis_agent"
            )
            result = await handler(message.payload)
            
            # PHASE 2 FIX: Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                await self.send_response(result, correlation_id=correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={correlation_id})",
                    agent="analysis_agent"
                )
            
            return result
        else:
            plog.warning(f"❌ No handler for message type: {message.type}", agent="analysis_agent")
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                await self.send_response(error_response, correlation_id=correlation_id)
            
            return error_response