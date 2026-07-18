"""
Strategy Generation Agent
Generates precise trade setups from market analysis
"""
import asyncio
import json
import copy
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from loguru import logger
from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import pandas as pd
import numpy as np

console = Console()

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.strategy.trade_setup_builder import EnhancedTradeSetupBuilder, TradeSetup
from src.strategy.risk_reward_calculator import RiskRewardCalculator
from src.strategy.position_sizer import PositionSizer
from src.strategy.confluence_scorer import ConfluenceScorer
from src.strategy.llm_strategy_prompter import LLMStrategyPrompter
from src.utils.config import get_config
from src.utils.enhanced_logging import PhaseLogger, StepLogger, MetricsLogger
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()

class StrategyGenerationAgent(BaseAgent):
    """
    Strategy Generation Agent

    Responsibilities:
    1. Receive analysis from Market Analysis Agent
    2. Build computational trade setup
    3. Call LLM for refinement and validation (OpenRouter primary, fallback chain available)
    4. Calculate position sizing
    5. Score confluence and confidence
    6. Send to Risk Management Agent
    """

    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager
    ):
        super().__init__("strategy_agent", message_bus, state_manager)

        self.config = get_config()

        # Initialize strategy modules
        self.setup_builder = EnhancedTradeSetupBuilder()
        self.rr_calculator = RiskRewardCalculator()
        self.position_sizer = PositionSizer()
        self.confluence_scorer = ConfluenceScorer()
        self.llm_prompter = LLMStrategyPrompter()

        # Initialize LLM clients (OpenRouter primary, Groq fallback, OpenAI final fallback)
        # CRITICAL FIX: Use sync OpenAI client for OpenRouter (AsyncOpenAI doesn't work with OpenRouter)
        # Bounded timeout on every LLM client (config.llm.timeout, default 60s) — SDK
        # defaults run to several minutes and a hung call stalls the cycle.
        _llm_timeout = float(self.config.llm.timeout or 60)
        self.openrouter_client = None
        if self.config.llm.openrouter_api_key:
            from openai import OpenAI  # Import sync client
            self.openrouter_client = OpenAI(
                api_key=self.config.llm.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=_llm_timeout,
            )

        # Groq client for fallback
        self.groq_client = None
        if self.config.llm.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.config.llm.groq_api_key, timeout=_llm_timeout)
            except ImportError:
                plog.warning("Groq package not installed, skipping Groq client initialization", agent="strategy_agent", phase="setup")

        # OpenAI client for final fallback
        self.llm_client = None
        if self.config.llm.openai_api_key:
            self.llm_client = AsyncOpenAI(api_key=self.config.llm.openai_api_key, timeout=_llm_timeout)

        # Log LLM configuration.
        # This reflects the ACTUAL decision-path chain in _call_llm_strategy_creator:
        # OpenRouter (free-tier DeepSeek, primary) → Groq → OpenAI (final).
        # (The old log claimed a Claude-primary chain that no longer runs — see the
        # dead _call_llm_strategy method annotation below.)
        _free_list = self.config.llm.openrouter_free_models or [self.config.llm.deepseek_model]
        plog.info(
            f"Strategy Agent initialized with LLM chain: OpenRouter free-tier rotation "
            f"[{len(_free_list)} models, primary={_free_list[0]}] "
            f"→ Groq/{self.config.llm.groq_model} (fallback) → OpenAI/{self.config.llm.gpt_model} (final)",
            agent="strategy_agent", phase="setup"
        )
        plog.info(f"LLM Clients - OpenAI: {self.llm_client is not None}, OpenRouter: {self.openrouter_client is not None}, Groq: {self.groq_client is not None}", agent="strategy_agent", phase="setup")
        plog.debug(f"OpenAI API Key configured: {bool(self.config.llm.openai_api_key)}", agent="strategy_agent")
        plog.debug(f"OpenRouter API Key configured: {bool(self.config.llm.openrouter_api_key)}", agent="strategy_agent")
        plog.debug(f"Groq API Key configured: {bool(self.config.llm.groq_api_key)}", agent="strategy_agent")
        plog.debug(f"GPT-4o model: {self.config.llm.gpt_model}", agent="strategy_agent")
        plog.debug(f"Groq model: {self.config.llm.groq_model}", agent="strategy_agent")

        # Strategy cache
        self.last_strategy = {}
        self.strategy_count = 0

    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("analysis_complete", self._handle_analysis_complete)
        self.register_handler("request_strategy", self._handle_strategy_request)
        self.register_handler("generate_setups", self._handle_strategy_request)  # For orchestrator

    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """
        Process incoming messages
        
        PHASE 2 FIX: Now sends responses back to orchestrator for sequential execution
        """
        # Extract correlation_id from message
        correlation_id = getattr(message, 'correlation_id', None) or message.payload.get('correlation_id')
        
        handler = self.handlers.get(message.type)
        if handler:
            result = await handler(message.payload)
            
            # PHASE 2 FIX: Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                # Ensure result has success flag
                if isinstance(result, dict) and 'success' not in result:
                    result['success'] = result.get('status') == 'success'
                
                # For strategy generation, expose the trade setup as `setups` — but
                # ONLY when it's a real, well-formed setup. The LLM path can return
                # success with trade_setup=None (no valid setup this cycle); wrapping
                # that as [None] used to flow a null downstream (crashed per-tenant
                # booking with "NoneType not subscriptable"). Emit [] instead → an
                # honest "0 setups" cycle.
                if message.type == "generate_setups" and result.get('success'):
                    strat = result.get('strategy') if isinstance(result.get('strategy'), dict) else None
                    ts = strat.get('trade_setup') if strat else None
                    result['setups'] = [ts] if (isinstance(ts, dict) and ts.get('symbol')) else []
                    if not result['setups']:
                        # success but no actual setup → report it as no-opportunity
                        result['success'] = bool(result.get('setups'))
                
                await self.send_response(result, correlation_id=correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={correlation_id})",
                    agent="strategy_agent"
                )
            
            return result
        else:
            plog.warning(f"No handler for message type: {message.type}", agent="strategy_agent", phase="message_processing")
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                await self.send_response(error_response, correlation_id=correlation_id)
                
            return error_response

    async def _handle_analysis_complete(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle analysis completion from Market Analysis Agent
        Generate trade strategy if opportunities exist
        """
        try:
            symbol = payload.get('symbol', 'UNKNOWN')
            plog.info(f"Received analysis for {symbol}", agent="strategy_agent", phase="analysis_handling")

            # Check if there are trade opportunities
            opportunities = payload.get('trade_opportunities', [])

            if not opportunities:
                plog.warning("No trade opportunities in analysis, skipping strategy generation", agent="strategy_agent", phase="analysis_handling")
                return {"status": "no_opportunities"}

            # Generate strategy
            strategy_result = await self.generate_strategy(
                symbol=symbol,
                analysis=payload
            )

            if strategy_result.get('trade_setup'):
                trade_setup_dict = strategy_result['trade_setup']
                
                # Validate required fields before sending
                required_fields = ['symbol', 'direction', 'entry_price', 'stop_loss']
                missing_fields = [f for f in required_fields if not trade_setup_dict.get(f)]
                
                if missing_fields:
                    plog.error(f"Trade setup missing required fields: {missing_fields}", agent="strategy_agent", phase="analysis_handling")
                    return {"status": "error", "message": f"Incomplete trade setup: {missing_fields}"}
                
                plog.debug(
                    f"Sending trade setup to Risk Agent: {trade_setup_dict.get('symbol')} {trade_setup_dict.get('direction')} @ ${trade_setup_dict.get('entry_price', 0):.2f}",
                    agent="strategy_agent",
                    phase="analysis_handling"
                )
                
                # Send to Risk Management Agent with full payload (flatten for easier access)
                await self.send_message(
                    receiver="risk_agent",
                    message_type="validate_trade",
                    payload={
                        'trade_setup': trade_setup_dict,
                        **trade_setup_dict  # Flatten for easier access in Risk Agent
                    },
                    priority=9
                )
                plog.success(f"Strategy generated and sent to Risk Agent", agent="strategy_agent", phase="analysis_handling")
            else:
                plog.warning(f"No valid strategy generated: {strategy_result.get('reason')}", agent="strategy_agent", phase="analysis_handling")
                plog.info("System will wait for next analysis cycle or market conditions to improve", agent="strategy_agent", phase="analysis_handling")

            return {"status": "success"}

        except Exception as e:
            plog.error(f"Error handling analysis: {e}", exception=e, agent="strategy_agent", phase="analysis_handling")
            return {"status": "error", "message": str(e)}

    async def _handle_strategy_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle direct strategy request"""
        try:
            symbol = payload.get('symbol')
            analysis = payload.get('analysis')
            candles = payload.get('candles', {})  # Extract candles from payload
            
            if not symbol or not analysis:
                plog.error("Missing symbol or analysis in strategy request", agent="strategy_agent", phase="strategy_generation")
                return {"status": "error", "message": "Missing symbol or analysis"}
            
            # Log candles received
            if candles:
                candle_counts = {tf: len(c) for tf, c in candles.items() if isinstance(c, list)}
                plog.info(f"Received candles from orchestrator: {candle_counts}", agent="strategy_agent")
            else:
                plog.warning("No candles received from orchestrator", agent="strategy_agent")
            
            plog.debug(f"Direct strategy request for {symbol}", agent="strategy_agent", phase="strategy_generation")
            
            # Publish activity
            await self.publish_activity(
                action="strategy_request_received",
                message=f"Received strategy generation request for {symbol}",
                phase="strategy_generation",
                severity="info"
            )


            strategy_result = await self.generate_strategy(symbol, analysis, candles)

            return {"status": "success", "strategy": strategy_result}

        except Exception as e:
            plog.error(f"Error in strategy request: {e}", exception=e, agent="strategy_agent", phase="strategy_generation")
            return {"status": "error", "message": str(e)}

    async def generate_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        candles: Dict[str, List[Dict[str, Any]]] = None
        ) -> Dict[str, Any]:
        """
        LLM-FIRST Strategy Generation Pipeline
        
        NEW APPROACH:
        1. Gather ALL computational data (no rejection)
        2. Pass everything to LLM for optimal setup creation
        3. Apply relaxed safety validation
        4. Calculate position sizing
        5. Return validated setup
        
        This allows LLM to create setups even when computational rules are too strict.
        
        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            analysis: Market analysis from Analysis Agent
            candles: Optional candles dict with timeframes (5m, 15m, 1h) from orchestrator
        """
        start_time = datetime.now()
        plog.method_entry("generate_strategy", agent="strategy_agent", phase="strategy_generation")
        
        # Publish activity
        await self.publish_activity(
            action="generating_strategies",
            message=f"Generating trading strategies for {symbol}",
            phase="strategy_generation",
            severity="info"
        )


        try:
            # Validate analysis data
            if not isinstance(analysis, dict):
                plog.error(f"Invalid analysis type: {type(analysis)}, expected dict", agent="strategy_agent")
                return {"trade_setup": None, "reason": "Invalid analysis data structure"}
            
            if not analysis.get('trade_opportunities'):
                plog.warning(f"No trade opportunities in analysis", agent="strategy_agent")
                return {"trade_setup": None, "reason": "No trade opportunities found"}
            
            # Use candles from payload if provided, otherwise empty dict
            if candles is None:
                candles = {}
                plog.warning("No candles provided to generate_strategy", agent="strategy_agent")
            
            async with PhaseLogger("strategy_generation", f"Strategy Generation for {symbol}", agent="strategy_agent"):
                # ========================================
                # PHASE 1: GATHER COMPUTATIONAL DATA (NO REJECTION)
                # ========================================
                step = StepLogger("1.1", "Gathering computational market data", agent="strategy_agent")
                step.start()
                
                await self.publish_activity(
                    action="computational_setup",
                    message="Building computational trade setup from analysis data",
                    phase="strategy_generation",
                    severity="info"
                )

                
                # Get market data
                current_price = await self._get_current_price(symbol, analysis)
                atr = await self._get_atr(symbol, analysis, candles)
                account_balance = await self._get_account_balance()

                # HARD GATE: without a real price and ATR every downstream number
                # (entry zones, stops, targets, position size, RR) is garbage.
                # Abort with a no-setup result rather than trading on fabricated data.
                if current_price is None or atr is None:
                    plog.error(
                        f"Missing market data for {symbol} (price={current_price}, atr={atr}); skipping setup generation",
                        agent="strategy_agent"
                    )
                    return {"trade_setup": None, "reason": "Missing market data (price/ATR unavailable)"}

                # Use candles from payload (already provided by orchestrator)
                candles_5m = candles.get('5m', [])
                candles_15m = candles.get('15m', [])
                candles_1h = candles.get('1h', [])
                
                # Extract trade opportunities
                opportunities = analysis.get('trade_opportunities', [])
                best_opportunity = max(opportunities, key=lambda x: (x.get('confluence_count', 0), x.get('confidence', 0))) if opportunities else None
                
                if not best_opportunity:
                    plog.warning("No valid opportunity found", agent="strategy_agent")
                    return {"trade_setup": None, "reason": "No valid opportunities"}
                
                direction = best_opportunity['direction']
                
                # Extract SMC/ICT data
                smc_data = analysis.get('smc_analysis', {})
                ict_data = analysis.get('ict_analysis', {})
                mtf_data = analysis.get('mtf_analysis', {})
                indicators = analysis.get('_raw_computational', {}).get('indicators', {})
                
                # Calculate entry zones (no rejection, just gather data)
                entry_zones = self._extract_entry_zones(direction, smc_data, ict_data, current_price)
                
                # Find support/resistance levels
                support_levels = self._extract_support_levels(analysis, current_price)
                resistance_levels = self._extract_resistance_levels(analysis, current_price)
                
                # Calculate volatility metrics
                volatility = self._calculate_volatility_level(atr, current_price)
                
                # Identify all confluences (no minimum requirement)
                all_confluences = self._identify_all_confluences(direction, smc_data, ict_data, indicators, mtf_data)
                
                # Build computational context for LLM
                computational_context = {
                    'symbol': symbol,
                    'direction': direction,
                    'current_price': current_price,
                    'atr': atr,
                    'volatility_level': volatility,
                    'entry_zones': entry_zones,
                    'support_levels': support_levels,
                    'resistance_levels': resistance_levels,
                    'confluences': all_confluences,
                    'market_structure': {
                        'htf_trend': mtf_data.get('htf_trend', 'UNKNOWN'),
                        'mtf_trend': mtf_data.get('mtf_trend', 'UNKNOWN'),
                        'overall_bias': mtf_data.get('overall_bias', 'NEUTRAL')
                    },
                    'opportunity_confidence': best_opportunity.get('confidence', 0.5),
                    'opportunity_confluences': best_opportunity.get('confluence_count', 0),
                    'account_balance': account_balance
                }
                
                step.complete(
                    success=True,
                    details=f"Gathered data: {len(entry_zones)} entry zones, {len(support_levels)} supports, {len(resistance_levels)} resistances, {len(all_confluences)} confluences",
                    metrics={
                        'current_price': current_price,
                        'atr': atr,
                        'volatility': volatility,
                        'confluences_found': len(all_confluences)
                    }
                )
                
                # ========================================
                # PHASE 2: LLM CREATES OPTIMAL SETUP
                # ========================================
                step = StepLogger("2.1", "Calling LLM to create optimal trade setup", agent="strategy_agent")
                step.start()
                
                await self.publish_activity(
                    action="llm_refinement",
                    message="Refining strategy with LLM for optimal entry/exit",
                    phase="strategy_generation",
                    severity="info"
                )

                
                plog.info(
                    f"🤖 Requesting LLM to create setup with context: {len(all_confluences)} confluences, "
                    f"{len(entry_zones)} entry zones, {volatility} volatility",
                    agent="strategy_agent"
                )
                
                llm_setup = await self._call_llm_strategy_creator(
                    symbol=symbol,
                    computational_context=computational_context,
                    analysis=analysis,
                    target_rr=2.0  # Guide LLM to aim for this
                )
                
                if not llm_setup or not llm_setup.get('trade_setup'):
                    plog.warning("LLM failed to create setup, no valid strategy", agent="strategy_agent")
                    step.complete(success=False, details="LLM setup creation failed")
                    return {"trade_setup": None, "reason": "LLM failed to create valid setup"}
                
                llm_trade_setup = llm_setup['trade_setup']
                
                step.complete(
                    success=True,
                    details=f"LLM created setup: RR {llm_trade_setup.get('risk_reward_ratio', 0):.2f}, Confidence {llm_trade_setup.get('confidence_score', 0):.2f}",
                    metrics={
                        'llm_rr': llm_trade_setup.get('risk_reward_ratio', 0),
                        'llm_confidence': llm_trade_setup.get('confidence_score', 0)
                    }
                )
                
                # ========================================
                # PHASE 3: SAFETY VALIDATION (RELAXED)
                # ========================================
                step = StepLogger("3.1", "Validating LLM setup for safety", agent="strategy_agent")
                step.start()
                
                is_safe, validation_errors = self._validate_setup_safety(
                    llm_trade_setup,
                    computational_context
                )
                
                if not is_safe:
                    plog.warning(f"LLM setup failed safety validation: {validation_errors}", agent="strategy_agent")
                    step.complete(success=False, details=f"Safety validation failed: {', '.join(validation_errors)}")
                    return {"trade_setup": None, "reason": f"Setup unsafe: {', '.join(validation_errors)}"}
                
                step.complete(
                    success=True,
                    details="Safety validation passed",
                    metrics={'validation_checks': len(validation_errors) == 0}
                )
                
                # ========================================
                # PHASE 4: POSITION SIZING
                # ========================================
                step = StepLogger("4.1", "Calculating position sizing", agent="strategy_agent")
                step.start()
                
                sizing_result = self.position_sizer.calculate_size(
                    account_balance=account_balance,
                    entry_price=llm_trade_setup['entry_price'],
                    stop_loss=llm_trade_setup['stop_loss'],
                    atr=atr,
                    method='volatility_adjusted'
                )
                
                # Update setup with position sizing
                llm_trade_setup['recommended_position_size'] = sizing_result.recommended_size
                llm_trade_setup['max_position_size'] = sizing_result.max_size
                llm_trade_setup['risk_amount'] = sizing_result.risk_amount
                
                step.complete(
                    success=True,
                    details=f"Position: {sizing_result.recommended_size:.6f} BTC (risk: ${sizing_result.risk_amount:.2f})",
                    metrics={
                        'position_size': sizing_result.recommended_size,
                        'risk_amount': sizing_result.risk_amount
                    }
                )
                
                total_time = (datetime.now() - start_time).total_seconds()
                
                # Build final result
                result = {
                    'trade_setup': llm_trade_setup,
                    'computational_context': computational_context,
                    'sizing_analysis': sizing_result.to_dict(),
                    'metadata': {
                        'symbol': symbol,
                        'timestamp': datetime.utcnow().isoformat(),
                        'strategy_id': f"{symbol}_{int(datetime.utcnow().timestamp())}",
                        'generated_by': 'llm_first_with_computational_context'
                    },
                    'performance_metrics': {
                        'total_time_seconds': round(total_time, 2)
                    }
                }
                
                plog.success(
                    f"✅ LLM-First strategy complete: {direction} @ ${llm_trade_setup['entry_price']:.2f}, "
                    f"RR {llm_trade_setup['risk_reward_ratio']:.2f}, "
                    f"Confidence {llm_trade_setup['confidence_score']:.2f}",
                    agent="strategy_agent"
                )
                
                await self.publish_activity(
                    action="strategy_generated",
                    message=f"Strategy generated: {direction} {symbol} @ ${llm_trade_setup['entry_price']:.2f}",
                    phase="strategy_generation",
                    severity="success",
                    metadata={
                        "direction": direction,
                        "entry": llm_trade_setup['entry_price'],
                        "confidence": llm_trade_setup['confidence_score'],
                        "rr": llm_trade_setup['risk_reward_ratio']
                    }
                )


                
                return result
                
        except Exception as e:
            plog.error(
                f"Error generating strategy: {type(e).__name__}: {str(e)}",
                exception=e,
                agent="strategy_agent",
                phase="strategy_generation"
            )
            return {"trade_setup": None, "reason": f"Error: {str(e)}"}

    async def _call_llm_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        computational_setup: TradeSetup,
        current_price: float,
        atr: float,
        account_balance: float,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        DEAD CODE / NOT WIRED UP — kept for reference only.

        This Claude-primary refinement chain (Claude → OpenRouter → Groq → OpenAI)
        has no callers: the live decision path is the LLM-first
        _call_llm_strategy_creator, which uses OpenRouter → Groq → OpenAI and does
        NOT use Claude. The Anthropic key is optional and this path never runs on
        the free-tier setup, so requiring it would be wrong. Do not re-enable this
        without also updating the init log and confirming the Claude models here.

        Original intent:
        Primary: Claude (config.llm.claude_model)
        Fallback 1: OpenRouter DeepSeek
        Fallback 2: OpenAI GPT-4o
        Fallback 3: Groq Llama
        """

        # Initialize Claude client if not already done
        if not hasattr(self, 'claude_client') or self.claude_client is None:
            api_key = self.config.llm.anthropic_api_key
            if api_key and len(api_key) >= 20:
                try:
                    from anthropic import AsyncAnthropic
                    self.claude_client = AsyncAnthropic(
                        api_key=api_key, timeout=float(self.config.llm.timeout or 60)
                    )
                    plog.debug(f"Claude client initialized successfully", agent="strategy_agent", phase="setup")
                except Exception as e:
                    plog.warning(f"Failed to initialize Claude client: {e}", agent="strategy_agent", phase="setup")
                    self.claude_client = None
            else:
                plog.warning(f"Anthropic API key missing or too short (length: {len(api_key) if api_key else 0})", agent="strategy_agent", phase="setup")
                self.claude_client = None

        # 1. Try Claude (best for complex structured JSON) - PRIMARY
        if self.claude_client:
            try:
                plog.info("🤖 Attempting Claude Sonnet 4.5 for strategy refinement", agent="strategy_agent", phase="llm_refinement")
                return await self._call_claude_strategy(
                    symbol, analysis, computational_setup, current_price, atr, account_balance, entry_confirmation
                )
            except Exception as e:
                plog.warning(f"Claude Sonnet 4.5 failed: {type(e).__name__}: {str(e)}, trying OpenRouter fallback", agent="strategy_agent", phase="llm_refinement", exception=e)
        else:
            plog.info("Claude client not initialized, skipping to OpenRouter", agent="strategy_agent", phase="llm_refinement")

        # 2. Try OpenRouter (DeepSeek) - FALLBACK 1
        if self.openrouter_client:
            try:
                plog.info("🤖 Attempting OpenRouter DeepSeek for strategy refinement", agent="strategy_agent", phase="llm_refinement")
                return await self._call_openrouter_strategy(
                    symbol, analysis, computational_setup, current_price, atr, account_balance, entry_confirmation
                )
            except Exception as e:
                plog.warning(f"OpenRouter DeepSeek failed: {type(e).__name__}: {str(e)}, trying Groq fallback", agent="strategy_agent", phase="llm_refinement", exception=e)
        else:
            plog.info("OpenRouter client not initialized, skipping to Groq", agent="strategy_agent", phase="llm_refinement")

        # 3. Try Groq (Llama) - FALLBACK 2
        if self.groq_client:
            try:
                plog.info("🤖 Attempting Groq Llama for strategy refinement", agent="strategy_agent", phase="llm_refinement")
                return await self._call_groq_strategy(
                    symbol, analysis, computational_setup, current_price, atr, account_balance, entry_confirmation
                )
            except Exception as e:
                plog.warning(f"Groq Llama failed: {type(e).__name__}: {str(e)}, trying OpenAI fallback", agent="strategy_agent", phase="llm_refinement", exception=e)
        else:
            plog.info("Groq client not initialized, skipping to OpenAI", agent="strategy_agent", phase="llm_refinement")

        # 4. Try OpenAI (GPT-4o) - FINAL FALLBACK
        if self.llm_client:
            try:
                plog.info("🤖 Attempting OpenAI GPT-4o for strategy refinement", agent="strategy_agent", phase="llm_refinement")
                return await self._call_openai_strategy(
                    symbol, analysis, computational_setup, current_price, atr, account_balance, entry_confirmation
                )
            except Exception as e:
                plog.error(f"OpenAI GPT-4o failed: {type(e).__name__}: {str(e)}", agent="strategy_agent", phase="llm_refinement", exception=e)
        else:
            plog.info("OpenAI client not initialized", agent="strategy_agent", phase="llm_refinement")

        plog.error("❌ All LLM strategy refinement attempts exhausted (Claude, OpenRouter, Groq, OpenAI all failed or unavailable)", agent="strategy_agent", phase="llm_refinement")
        return None

    async def _call_openai_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        computational_setup: TradeSetup,
        current_price: float,
        atr: float,
        account_balance: float,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call OpenAI GPT-4o for strategy refinement"""

        # Build prompt
        prompt_data = self.llm_prompter.build_strategy_prompt(
            symbol=symbol,
            analysis=analysis,
            current_price=current_price,
            atr=atr,
            account_balance=account_balance,
            entry_confirmation=entry_confirmation
        )

        # Call GPT-4o
        response = await self.llm_client.chat.completions.create(
            model=self.config.llm.gpt4o_model,
            messages=[
                {"role": "system", "content": prompt_data['system_prompt']},
                {"role": "user", "content": prompt_data['user_message']}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        # Extract and parse response
        response_text = response.choices[0].message.content
        plog.debug(f"OpenRouter raw response (first 500 chars): {response_text[:500]}...", agent="strategy_agent", phase="llm_refinement")
        strategy = self._parse_llm_response(response_text)
        
        if not strategy:
            plog.warning("OpenAI returned unparseable response", agent="strategy_agent", phase="llm_refinement")
            return None
        
        # Log usage
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        await self._track_llm_cost(input_tokens, output_tokens, provider="openai")
        
        return strategy

    async def _call_claude_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        computational_setup: TradeSetup,
        current_price: float,
        atr: float,
        account_balance: float,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call Claude Sonnet 4.5 for strategy refinement (primary)"""

        # Build prompt
        prompt_data = self.llm_prompter.build_strategy_prompt(
            symbol=symbol,
            analysis=analysis,
            current_price=current_price,
            atr=atr,
            account_balance=account_balance,
            entry_confirmation=entry_confirmation
        )

        # Call Claude
        response = await self.claude_client.messages.create(
            model=self.config.llm.claude_model,
            max_tokens=4000,
            system=prompt_data['system_prompt'],
            messages=[
                {"role": "user", "content": prompt_data['user_message']}
            ],
            temperature=0.3
        )

        # Extract response
        response_text = response.content[0].text

        plog.debug(
            f"Received response from Claude (length: {len(response_text)} chars)",
            agent="strategy_agent",
            phase="llm_refinement"
        )

        # Parse JSON response
        strategy = self._parse_llm_response(response_text)

        if not strategy:
            plog.warning("Claude returned unparseable response", agent="strategy_agent", phase="llm_refinement")
            return None

        # Log usage
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        plog.info(
            f"Claude Sonnet 4.5 - {input_tokens:,} input + {output_tokens:,} output tokens",
            agent="strategy_agent",
            phase="llm_refinement"
        )

        # Track costs
        await self._track_llm_cost(input_tokens, output_tokens, provider="claude")

        return strategy

    async def _call_openrouter_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        computational_setup: TradeSetup,
        current_price: float,
        atr: float,
        account_balance: float,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call OpenRouter DeepSeek for strategy refinement (fallback)"""

        # Build prompt
        prompt_data = self.llm_prompter.build_strategy_prompt(
            symbol=symbol,
            analysis=analysis,
            current_price=current_price,
            atr=atr,
            account_balance=account_balance,
            entry_confirmation=entry_confirmation
        )

        # Call OpenRouter using sync client in executor (OpenRouter doesn't support AsyncOpenAI)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.openrouter_client.chat.completions.create(
                model=self.config.llm.deepseek_model,
                messages=[
                    {"role": "system", "content": prompt_data['system_prompt']},
                    {"role": "user", "content": prompt_data['user_message']}
                ],
                temperature=0.3,
                max_tokens=20000
            )
        )

        # Extract and parse response
        response_text = response.choices[0].message.content
        plog.debug(f"Groq raw response (first 500 chars): {response_text[:500]}...", agent="strategy_agent", phase="llm_refinement")
        strategy = self._parse_llm_response(response_text)
        
        if not strategy:
            plog.warning("OpenRouter returned unparseable response", agent="strategy_agent", phase="llm_refinement")
            return None
        
        # Log usage (approximate)
        input_tokens = len(prompt_data['user_message'].split()) + len(prompt_data['system_prompt'].split())
        output_tokens = len(response_text.split())
        await self._track_llm_cost(input_tokens, output_tokens, provider="openrouter")

        return strategy

    async def _call_groq_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        computational_setup: TradeSetup,
        current_price: float,
        atr: float,
        account_balance: float,
        entry_confirmation: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call Groq Llama for strategy refinement (final fallback)"""

        # Build prompt
        prompt_data = self.llm_prompter.build_strategy_prompt(
            symbol=symbol,
            analysis=analysis,
            current_price=current_price,
            atr=atr,
            account_balance=account_balance,
            entry_confirmation=entry_confirmation
        )

        # Call Groq (using sync client in executor since Groq doesn't have async client)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.groq_client.chat.completions.create(
                model=self.config.llm.groq_model,
                messages=[
                    {"role": "system", "content": prompt_data['system_prompt']},
                    {"role": "user", "content": prompt_data['user_message']}
                ],
                temperature=0.3,
                max_tokens=2000
            )
        )

        # Extract and parse response
        response_text = response.choices[0].message.content
        plog.debug(f"Groq raw response (first 500 chars): {response_text[:500]}...", agent="strategy_agent", phase="llm_refinement")
        strategy = self._parse_llm_response(response_text)
        
        if not strategy:
            plog.warning("Groq returned unparseable response", agent="strategy_agent", phase="llm_refinement")
            return None
        
        # Log usage (approximate)
        input_tokens = len(prompt_data['user_message'].split()) + len(prompt_data['system_prompt'].split())
        output_tokens = len(response_text.split())
        await self._track_llm_cost(input_tokens, output_tokens, provider="groq")

        return strategy

    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate LLM response"""
        try:
            # Clean up potential markdown code blocks
            # Clean up potential markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                if json_end != -1:
                    json_str = response_text[json_start:json_end].strip()
                else:
                    # If no closing backticks, take the rest of the string
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

            plog.debug(f"Attempting to parse JSON response ({len(json_str)} chars)", agent="strategy_agent", phase="llm_refinement")

            strategy = json.loads(json_str)

            if not isinstance(strategy, dict):
                raise ValueError(f"LLM response is not a dict: {type(strategy)}")

            # Check if this is the schema itself (LLM returned schema instead of data)
            if 'properties' in strategy and strategy.get('type') == 'object':
                plog.warning("LLM returned schema instead of data", agent="strategy_agent", phase="llm_refinement")
                return None

            # Check for error field (safer approach)
            if strategy.get('error'):
                error_info = strategy.get('error')
                if isinstance(error_info, dict):
                    error_type = error_info.get('type', 'unknown')
                    error_msg = error_info.get('message', 'Unknown error')
                    plog.warning(f"LLM returned error response: {error_type} - {error_msg}", agent="strategy_agent", phase="llm_refinement")
                else:
                    error_msg = str(error_info)
                    plog.warning(f"LLM returned error response: {error_msg}", agent="strategy_agent", phase="llm_refinement")
                return None

            # Check for error type field
            if strategy.get('type') == 'error':
                error_msg = strategy.get('message', 'Unknown error')
                plog.warning(f"LLM returned error type response: {error_msg}", agent="strategy_agent", phase="llm_refinement")
                return None

            return strategy

        except json.JSONDecodeError as e:
            # Don't include raw response in error message as it may contain unescaped braces
            plog.error(f"JSON parsing error: {str(e)}", exception=e, agent="strategy_agent", phase="llm_refinement")
            return None  # Return None to trigger fallback
        except Exception as e:
            plog.error(f"Unexpected error parsing LLM response: {str(e)}", exception=e, agent="strategy_agent", phase="llm_refinement")
            return None  # Return None to trigger fallback


    def _merge_llm_refinements(
        self,
        computational: TradeSetup,
        llm_setup: Dict[str, Any]
    ) -> TradeSetup:
        """
        Merge LLM refinements with computational setup
        LLM can adjust entry, SL, TPs within reasonable bounds
        """
        plog.method_entry("_merge_llm_refinements", agent="strategy_agent")

        # Validate LLM setup structure
        if not isinstance(llm_setup, dict):
            plog.warning(f"LLM setup is not a dict, type: {type(llm_setup)}", agent="strategy_agent")
            return computational

        # Start with computational (deep copy to avoid modifying original)
        merged = copy.deepcopy(computational)

        # Adjust entry if LLM suggests and it's within 1% of computational
        llm_entry = llm_setup.get('entry_price', computational.entry_price)
        if isinstance(llm_entry, (int, float)) and abs(llm_entry - computational.entry_price) / computational.entry_price < 0.01:
            merged.entry_price = llm_entry
            plog.debug(f"Merged LLM entry price: ${llm_entry:.2f}", agent="strategy_agent")

        # Adjust SL if reasonable
        llm_sl = llm_setup.get('stop_loss', computational.stop_loss)
        if isinstance(llm_sl, (int, float)) and abs(llm_sl - computational.stop_loss) / computational.stop_loss < 0.02:
            merged.stop_loss = llm_sl
            plog.debug(f"Merged LLM stop loss: ${llm_sl:.2f}", agent="strategy_agent")

        # Use LLM confidence if higher quality
        llm_confidence = llm_setup.get('confidence_score', computational.confidence_score)
        if isinstance(llm_confidence, (int, float)) and 0.65 <= llm_confidence <= 0.95:
            plog.debug(f"Updating confidence from {computational.confidence_score:.2f} to {llm_confidence:.2f} (LLM)", agent="strategy_agent")
            merged.confidence_score = llm_confidence
        else:
            plog.debug(f"Keeping computational confidence {computational.confidence_score:.2f}", agent="strategy_agent")

        # Merge reasoning (safely handle missing or malformed reasoning)
        try:
            if 'reasoning' in llm_setup and llm_setup.get('reasoning'):
                reasoning = llm_setup.get('reasoning')
                if isinstance(reasoning, dict):
                    entry_rationale = reasoning.get('entry_rationale', '')
                elif isinstance(reasoning, str):
                    entry_rationale = reasoning
                else:
                    entry_rationale = str(reasoning)
                merged.setup_reasoning = f"{computational.setup_reasoning}\n\nLLM Refinement:\n{entry_rationale}"
            else:
                # No reasoning provided, keep computational reasoning
                merged.setup_reasoning = computational.setup_reasoning
        except (KeyError, TypeError, AttributeError) as e:
            plog.warning(f"Failed to merge reasoning from LLM response: {str(e)}", agent="strategy_agent", phase="llm_refinement")
            merged.setup_reasoning = computational.setup_reasoning

        plog.method_exit("_merge_llm_refinements", result=f"Merged setup with confidence {merged.confidence_score:.2f}")
        return merged

    async def _fallback_computational_strategy(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float,
        atr: float,
        account_balance: float
    ) -> Dict[str, Any]:
        """
        Fallback to computational-only strategy (no LLM)
        """
        plog.warning("Using fallback computational-only strategy", agent="strategy_agent", phase="strategy_generation")
        plog.method_entry("_fallback_computational_strategy", agent="strategy_agent")

        # Get minimal candle data for fallback
        candles_5m = await self._get_candles_5m(symbol)
        candles_15m = await self._get_candles_15m(symbol)
        candles_1h = await self._get_candles_1h(symbol)

        computational_setup = self.setup_builder.build_setup_with_confirmation(
            symbol=symbol,
            analysis=analysis,
            current_price=current_price,
            atr=atr,
            candles_5m=candles_5m,
            candles_15m=candles_15m,
            candles_1h=candles_1h
        )

        if not computational_setup:
            plog.warning("Fallback computational setup also failed", agent="strategy_agent", phase="strategy_generation")
            plog.warning("System will wait for next analysis cycle when market conditions improve", agent="strategy_agent")
            plog.method_exit("_fallback_computational_strategy", result="Failed - no setup")
            return {
                'trade_setup': None,
                'reason': 'Computational setup failed - waiting for improved market conditions',
                'is_fallback': True
            }

        # Calculate position sizing
        sizing_result = self.position_sizer.calculate_size(
            account_balance=account_balance,
            entry_price=computational_setup.entry_price,
            stop_loss=computational_setup.stop_loss,
            atr=atr
        )

        computational_setup.recommended_position_size = sizing_result.recommended_size
        computational_setup.risk_amount = sizing_result.risk_amount

        plog.method_exit("_fallback_computational_strategy", result=f"Fallback setup created for {symbol}")
        return {
            'trade_setup': computational_setup.to_dict(),
            'sizing_analysis': sizing_result.to_dict(),
            'is_fallback': True,
            'reason': 'LLM unavailable, using computational only'
        }

    async def _get_current_price(self, symbol: str, analysis: Dict[str, Any] = None) -> Optional[float]:
        """Get current market price from analysis or state manager (None if unavailable)"""
        # First try to get from analysis (most accurate)
        if analysis:
            # Try different possible locations in analysis
            price = None
            
            # Check market_data in analysis
            if 'market_data' in analysis:
                price = analysis['market_data'].get('price') or analysis['market_data'].get('current_price')
            
            # Check top-level
            if not price:
                price = analysis.get('current_price') or analysis.get('price')
            
            # Check indicators
            if not price and 'indicators' in analysis:
                price = analysis['indicators'].get('current_price')
            
            if price:
                plog.debug(f"Current price from analysis: ${float(price):.2f}", agent="strategy_agent")
                return float(price)
        
        # Fallback to state manager
        price = await self.state_manager.get(f"price:{symbol}")
        
        if price:
            plog.debug(f"Current price from state manager: ${float(price):.2f}", agent="strategy_agent")
            return float(price)

        # HARD FAILURE: a missing price must never be replaced with a hardcoded
        # literal. A mock price (previously $43000, a BTC-shaped number) produces
        # garbage setups for any other symbol. Return None so the caller aborts
        # setup generation instead of trading on fabricated data.
        plog.error(f"No price found for {symbol} in analysis or state manager; aborting setup", agent="strategy_agent")
        return None

    async def _get_atr(self, symbol: str, analysis: Dict[str, Any] = None, candles: Dict[str, List[Dict[str, Any]]] = None) -> Optional[float]:
        """Get current ATR from analysis, state manager, or calculate from candles (None if unavailable)"""
        # First try to get from analysis (most accurate)
        if analysis:
            atr = None
            
            # Check indicators
            if 'indicators' in analysis:
                indicators = analysis['indicators']
                atr = indicators.get('atr') or indicators.get('ATR')
            
            # Check computational section
            if not atr and 'computational' in analysis:
                atr = analysis['computational'].get('atr')
            
            # Check top-level
            if not atr:
                atr = analysis.get('atr') or analysis.get('ATR')
            
            if atr:
                plog.debug(f"ATR from analysis: ${float(atr):.2f}", agent="strategy_agent")
                return float(atr)
        
        # Try to calculate from candles if provided
        if candles:
            # Prefer 1h, then 15m, then 5m
            for tf in ['1h', '15m', '5m']:
                if tf in candles and candles[tf]:
                    calculated_atr = self._calculate_atr_from_candles(candles[tf])
                    if calculated_atr:
                        plog.debug(f"Calculated ATR from {tf} candles: ${calculated_atr:.2f}", agent="strategy_agent")
                        return calculated_atr
        
        # Fallback to state manager
        atr = await self.state_manager.get(f"atr:{symbol}")
        
        if atr:
            plog.debug(f"ATR from state manager: ${float(atr):.2f}", agent="strategy_agent")
            return float(atr)

        # HARD FAILURE: ATR drives stop-loss/target distances. A hardcoded literal
        # (previously $150, a BTC-shaped number) yields nonsensical risk geometry
        # for any other symbol. Return None so the caller aborts setup generation.
        plog.error(f"No ATR found for {symbol} (analysis, candles, or state manager); aborting setup", agent="strategy_agent")
        return None

    def _calculate_atr_from_candles(self, candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
        """Calculate ATR from candle data"""
        try:
            if not candles or len(candles) < period + 1:
                return None
                
            df = pd.DataFrame(candles)
            
            # Ensure numeric columns
            for col in ['high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col])
                
            high = df['high']
            low = df['low']
            close = df['close']
            
            # Calculate TR
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Calculate ATR
            atr = tr.rolling(window=period).mean().iloc[-1]
            
            return float(atr)
        except Exception as e:
            plog.error(f"Error calculating ATR: {e}", agent="strategy_agent")
            return None

    async def _get_account_balance(self) -> float:
        """Get account balance (falls back to configured paper-mode starting capital)"""
        portfolio = await self.state_manager.get_portfolio_state()
        balance = portfolio.get('account_balance') if portfolio else None
        if balance is not None:
            plog.debug(f"Account balance: ${float(balance):.2f}", agent="strategy_agent")
            return float(balance)

        # No live portfolio balance yet (paper mode / cold start). Source the
        # default from config instead of a hardcoded literal so it tracks the
        # configured starting capital rather than an arbitrary $10k.
        default_balance = float(self.config.trading.initial_capital)
        plog.debug(f"No portfolio balance; using configured initial_capital ${default_balance:.2f}", agent="strategy_agent")
        return default_balance

    async def _get_candles_5m(self, symbol: str) -> List[Dict[str, Any]]:
        """Get 5M candles for entry confirmation"""
        candles = await self.state_manager.get(f"candles_5m:{symbol}")
        if not candles:
            plog.warning(f"No 5M candles found for {symbol}, using empty list", agent="strategy_agent")
            return []
        plog.debug(f"Retrieved {len(candles)} 5M candles for {symbol}", agent="strategy_agent")
        return candles[-50:]  # Last 50 candles for analysis

    async def _get_candles_15m(self, symbol: str) -> List[Dict[str, Any]]:
        """Get 15M candles for momentum context"""
        candles = await self.state_manager.get(f"candles_15m:{symbol}")
        if not candles:
            plog.warning(f"No 15M candles found for {symbol}, using empty list", agent="strategy_agent")
            return []
        plog.debug(f"Retrieved {len(candles)} 15M candles for {symbol}", agent="strategy_agent")
        return candles[-20:]  # Last 20 candles for context

    async def _get_candles_1h(self, symbol: str) -> List[Dict[str, Any]]:
        """Get 1H candles for trend context"""
        candles = await self.state_manager.get(f"candles_1h:{symbol}")
        if not candles:
            plog.warning(f"No 1H candles found for {symbol}, using empty list", agent="strategy_agent")
            return []
        plog.debug(f"Retrieved {len(candles)} 1H candles for {symbol}", agent="strategy_agent")
        return candles[-20:]  # Last 20 candles for trend

    async def _get_all_state_data(self) -> Dict[str, Any]:
        """Get all state manager data for debugging"""
        try:
            # Get all keys from Redis (this is a simplified approach)
            # In a real implementation, you'd need to scan all keys with "state:" prefix
            # For now, we'll get some common keys
            state_data = {}

            # Common keys that might exist
            common_keys = [
                f"price:BTCUSDT",
                f"atr:BTCUSDT",
                "account_balance",
                "candles_5m:BTCUSDT",
                "candles_15m:BTCUSDT",
                "candles_1h:BTCUSDT",
                "order_book:BTCUSDT",
                "funding_rate:BTCUSDT",
                "daily_llm_cost",
                "daily_strategy_llm_cost"
            ]

            for key in common_keys:
                try:
                    value = await self.state_manager.get(key)
                    if value is not None:
                        state_data[key] = value
                except Exception as e:
                    plog.debug(f"Could not get state key {key}: {e}", agent="strategy_agent")

            return state_data
        except Exception as e:
            plog.error(f"Error getting all state data: {e}", exception=e, agent="strategy_agent")
            return {}

    async def _track_llm_cost(self, input_tokens: int, output_tokens: int, provider: str = "openai"):
        """Track LLM API costs"""
        if provider == "openai":
            # GPT-4o pricing (as of 2024)
            input_cost = (input_tokens / 1000) * 0.0025
            output_cost = (output_tokens / 1000) * 0.01
            total_cost = input_cost + output_cost
        elif provider == "openrouter":
            # DeepSeek free tier - minimal cost
            total_cost = 0.0
        elif provider == "groq":
            # Groq free tier - no cost
            total_cost = 0.0
        else:
            total_cost = 0.0


        # Store in state
        daily_cost = await self.state_manager.get('daily_strategy_llm_cost') or 0.0
        await self.state_manager.set('daily_strategy_llm_cost', daily_cost + total_cost)

        plog.debug(f"{provider.upper()} Cost: ${total_cost:.4f} (Daily: ${daily_cost + total_cost:.2f})", agent="strategy_agent", phase="llm_refinement")

    # ========================================
    # LLM-FIRST HELPER METHODS
    # ========================================
    
    def _extract_entry_zones(
        self,
        direction: str,
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        current_price: float
    ) -> List[Dict[str, float]]:
        """Extract entry zones from SMC/ICT data without strict validation"""
        entry_zones = []
        
        # Extract from SMC Order Blocks
        smc_comp = smc_data.get('computational', smc_data)
        order_blocks = smc_comp.get('order_blocks', [])
        
        for ob in order_blocks:
            if (direction == 'LONG' and ob.get('type') == 'bullish') or \
               (direction == 'SHORT' and ob.get('type') == 'bearish'):
                zone = ob.get('zone', {})
                if isinstance(zone, dict) and 'low' in zone and 'high' in zone:
                    entry_zones.append({
                        'low': float(zone['low']),
                        'high': float(zone['high']),
                        'type': 'order_block',
                        'timeframe': ob.get('timeframe', 'unknown')
                    })
        
        # Extract from Fair Value Gaps
        fvgs = smc_comp.get('fair_value_gaps', [])
        for fvg in fvgs:
            if (direction == 'LONG' and fvg.get('type') == 'bullish') or \
               (direction == 'SHORT' and fvg.get('type') == 'bearish'):
                gap = fvg.get('gap', {})
                if isinstance(gap, dict) and 'low' in gap and 'high' in gap:
                    entry_zones.append({
                        'low': float(gap['low']),
                        'high': float(gap['high']),
                        'type': 'fvg',
                        'timeframe': fvg.get('timeframe', 'unknown')
                    })
        
        # Extract from ICT OTE zones
        ict_comp = ict_data.get('computational', ict_data)
        ote_zones = ict_comp.get('ote_zones', {})
        if ote_zones.get('in_zone') or ote_zones.get('in_ote_zone'):
            zone_low = ote_zones.get('zone_low', current_price * 0.995)
            zone_high = ote_zones.get('zone_high', current_price * 1.005)
            entry_zones.append({
                'low': float(zone_low),
                'high': float(zone_high),
                'type': 'ote',
                'timeframe': ote_zones.get('timeframe', 'unknown')
            })
        
        # If no zones found, create a default zone around current price
        if not entry_zones:
            buffer = current_price * 0.005  # 0.5% buffer
            entry_zones.append({
                'low': current_price - buffer,
                'high': current_price + buffer,
                'type': 'default',
                'timeframe': 'current'
            })
        
        return entry_zones
    
    def _extract_support_levels(
        self,
        analysis: Dict[str, Any],
        current_price: float
    ) -> List[float]:
        """Extract support levels from analysis"""
        support_levels = []
        
        # From key levels
        key_levels = analysis.get('key_levels', {})
        supports = key_levels.get('support', [])
        
        for level in supports:
            if isinstance(level, (int, float)):
                support_levels.append(float(level))
            elif isinstance(level, str):
                try:
                    support_levels.append(float(level))
                except ValueError:
                    continue
        
        # From SMC analysis
        smc_data = analysis.get('smc_analysis', {})
        smc_comp = smc_data.get('computational', smc_data)
        
        # Order blocks as support
        for ob in smc_comp.get('order_blocks', []):
            if ob.get('type') == 'bullish':
                zone = ob.get('zone', {})
                if isinstance(zone, dict) and 'low' in zone:
                    support_levels.append(float(zone['low']))
        
        # Remove duplicates and sort
        support_levels = sorted(list(set(support_levels)))
        
        # Filter to levels below current price
        support_levels = [s for s in support_levels if s < current_price]
        
        return support_levels[-5:] if len(support_levels) > 5 else support_levels  # Return top 5
    
    def _extract_resistance_levels(
        self,
        analysis: Dict[str, Any],
        current_price: float
    ) -> List[float]:
        """Extract resistance levels from analysis"""
        resistance_levels = []
        
        # From key levels
        key_levels = analysis.get('key_levels', {})
        resistances = key_levels.get('resistance', [])
        
        for level in resistances:
            if isinstance(level, (int, float)):
                resistance_levels.append(float(level))
            elif isinstance(level, str):
                try:
                    resistance_levels.append(float(level))
                except ValueError:
                    continue
        
        # From SMC analysis
        smc_data = analysis.get('smc_analysis', {})
        smc_comp = smc_data.get('computational', smc_data)
        
        # Order blocks as resistance
        for ob in smc_comp.get('order_blocks', []):
            if ob.get('type') == 'bearish':
                zone = ob.get('zone', {})
                if isinstance(zone, dict) and 'high' in zone:
                    resistance_levels.append(float(zone['high']))
        
        # Remove duplicates and sort
        resistance_levels = sorted(list(set(resistance_levels)))
        
        # Filter to levels above current price
        resistance_levels = [r for r in resistance_levels if r > current_price]
        
        return resistance_levels[:5] if len(resistance_levels) > 5 else resistance_levels  # Return top 5
    
    def _calculate_volatility_level(
        self,
        atr: float,
        current_price: float
    ) -> str:
        """Calculate volatility level as a string"""
        atr_percentage = (atr / current_price) * 100
        
        if atr_percentage < 1.0:
            return 'low'
        elif atr_percentage < 2.5:
            return 'medium'
        elif atr_percentage < 4.0:
            return 'high'
        else:
            return 'very_high'
    
    def _identify_all_confluences(
        self,
        direction: str,
        smc_data: Dict[str, Any],
        ict_data: Dict[str, Any],
        indicators: Dict[str, Any],
        mtf_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify all confluence factors without minimum requirements"""
        confluences = []
        
        smc_comp = smc_data.get('computational', smc_data)
        ict_comp = ict_data.get('computational', ict_data)
        
        # SMC Confluences
        for ob in smc_comp.get('order_blocks', []):
            if (direction == 'LONG' and ob.get('type') == 'bullish') or \
               (direction == 'SHORT' and ob.get('type') == 'bearish'):
                confluences.append({
                    'factor': f"{ob.get('type', '').title()} Order Block",
                    'category': 'SMC',
                    'weight': 1.0,
                    'timeframe': ob.get('timeframe', 'unknown')
                })
        
        for fvg in smc_comp.get('fair_value_gaps', []):
            if (direction == 'LONG' and fvg.get('type') == 'bullish') or \
               (direction == 'SHORT' and fvg.get('type') == 'bearish'):
                confluences.append({
                    'factor': f"{fvg.get('type', '').title()} FVG",
                    'category': 'SMC',
                    'weight': 0.9,
                    'timeframe': fvg.get('timeframe', 'unknown')
                })
        
        # ICT Confluences
        killzone = ict_comp.get('killzone', {})
        if killzone.get('active') or killzone.get('current_killzone') in ['london', 'new_york']:
            confluences.append({
                'factor': 'ICT Killzone Active',
                'category': 'ICT',
                'weight': 0.8,
                'timeframe': 'time-based'
            })
        
        # Market Structure
        htf_trend = mtf_data.get('htf_trend', '').lower()
        if (direction == 'LONG' and htf_trend == 'bullish') or \
           (direction == 'SHORT' and htf_trend == 'bearish'):
            confluences.append({
                'factor': f'HTF {htf_trend.title()} Trend',
                'category': 'STRUCTURE',
                'weight': 1.0,
                'timeframe': 'HTF'
            })
        
        mtf_trend = mtf_data.get('mtf_trend', '').lower()
        if (direction == 'LONG' and mtf_trend == 'bullish') or \
           (direction == 'SHORT' and mtf_trend == 'bearish'):
            confluences.append({
                'factor': f'MTF {mtf_trend.title()} Alignment',
                'category': 'STRUCTURE',
                'weight': 0.9,
                'timeframe': 'MTF'
            })
        
        return confluences
    
    async def _call_llm_strategy_creator(
        self,
        symbol: str,
        computational_context: Dict[str, Any],
        analysis: Dict[str, Any],
        target_rr: float = 2.0
    ) -> Optional[Dict[str, Any]]:
        """
        Call LLM to CREATE optimal trade setup (not just refine)
        
        This is the new LLM-First approach where LLM has full creative control
        """
        try:
            # Build comprehensive prompt for setup creation
            prompt = self._build_llm_creator_prompt(
                symbol=symbol,
                computational_context=computational_context,
                analysis=analysis,
                target_rr=target_rr
            )
            
            # Try OpenRouter free tier first (primary). Rotate through the free-model
            # list rather than pinning ONE model: any single ':free' model can be
            # pulled or 429'd at any moment, so try each in order and use the first
            # that returns a JSON-shaped reply. See src/utils/openrouter_rotation.py.
            if self.openrouter_client and self.config.llm.openrouter_api_key:
                try:
                    from src.utils.openrouter_rotation import complete_with_rotation, looks_like_json_object
                    plog.info("🤖 Attempting OpenRouter free-tier rotation for strategy creation", agent="strategy_agent")

                    # Sync client → run the (rotating) call off the event loop.
                    loop = asyncio.get_event_loop()
                    content, used_model = await loop.run_in_executor(
                        None,
                        lambda: complete_with_rotation(
                            self.openrouter_client,
                            self.config.llm.openrouter_free_models,
                            [
                                {"role": "system", "content": "You are an expert crypto trader who creates optimal trade setups."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=2000,
                            validate=looks_like_json_object,
                            on_attempt=lambda m, s: plog.debug(f"OpenRouter[{m}]: {s}", agent="strategy_agent"),
                        )
                    )

                    result = self._parse_llm_creator_response(content)
                    if result:
                        plog.success(f"✅ OpenRouter {used_model} created setup successfully", agent="strategy_agent")
                        return result
                    plog.warning(f"OpenRouter {used_model} response unparseable after rotation", agent="strategy_agent")

                except Exception as e:
                    plog.warning(f"OpenRouter free-tier rotation failed: {e}", agent="strategy_agent")
            
            # Fallback to Groq if available
            if self.groq_client and self.config.llm.groq_api_key:
                try:
                    plog.info("🤖 Attempting Groq Llama for strategy creation", agent="strategy_agent")
                    
                    # Groq client is SYNC, use executor
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.groq_client.chat.completions.create(
                            model=self.config.llm.groq_model,  # config-driven, not hardcoded
                            messages=[
                                {"role": "system", "content": "You are an expert crypto trader who creates optimal trade setups."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=2000
                        )
                    )
                    
                    if response and response.choices and len(response.choices) > 0:
                        content = response.choices[0].message.content
                        if content and content.strip():
                            result = self._parse_llm_creator_response(content)
                            if result:
                                plog.success("✅ Groq Llama created setup successfully", agent="strategy_agent")
                                return result
                        else:
                            plog.warning("Groq Llama returned empty response", agent="strategy_agent")
                    else:
                        plog.warning("Groq Llama returned no choices", agent="strategy_agent")
                        
                except Exception as e:
                    plog.warning(f"Groq Llama failed: {e}", agent="strategy_agent")
            
            # Fallback to OpenAI GPT-4o if available (use self.llm_client, not self.openai_client)
            if self.llm_client and self.config.llm.openai_api_key:
                # Check if key is valid/not placeholder
                if "your_ope" in self.config.llm.openai_api_key or "*" in self.config.llm.openai_api_key:
                    plog.warning("OpenAI API key appears to be invalid/placeholder. Skipping.", agent="strategy_agent")
                else:
                    try:
                        plog.info("🤖 Attempting OpenAI GPT-4o for strategy creation", agent="strategy_agent")
                        
                        response = await self.llm_client.chat.completions.create(
                            model=self.config.llm.gpt_model,  # config-driven, not hardcoded
                            messages=[
                                {"role": "system", "content": "You are an expert crypto trader who creates optimal trade setups."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=2000
                        )
                        
                        if response and response.choices and len(response.choices) > 0:
                            content = response.choices[0].message.content
                            if content and content.strip():
                                result = self._parse_llm_creator_response(content)
                                if result:
                                    plog.success("✅ OpenAI GPT-4o created setup successfully", agent="strategy_agent")
                                    return result
                            else:
                                plog.warning("OpenAI GPT-4o returned empty response", agent="strategy_agent")
                        else:
                            plog.warning("OpenAI GPT-4o returned no choices", agent="strategy_agent")
                            
                    except Exception as e:
                        plog.warning(f"OpenAI GPT-4o failed: {e}", agent="strategy_agent")
            
            plog.error("All LLM providers failed for strategy creation", agent="strategy_agent")
            return None
            
        except Exception as e:
            plog.error(f"Error in LLM strategy creator: {e}", exception=e, agent="strategy_agent")
            return None
    
    def _build_llm_creator_prompt(
        self,
        symbol: str,
        computational_context: Dict[str, Any],
        analysis: Dict[str, Any],
        target_rr: float
    ) -> str:
        """Build comprehensive prompt for LLM to create trade setup"""
        
        direction = computational_context['direction']
        current_price = computational_context['current_price']
        atr = computational_context['atr']
        volatility = computational_context['volatility_level']
        entry_zones = computational_context['entry_zones']
        support_levels = computational_context['support_levels']
        resistance_levels = computational_context['resistance_levels']
        confluences = computational_context['confluences']
        market_structure = computational_context['market_structure']
        
        # Format entry zones
        entry_zones_str = "\n".join([
            f"  - {zone['type'].upper()}: ${zone['low']:.2f} - ${zone['high']:.2f} ({zone['timeframe']})"
            for zone in entry_zones
        ])
        
        # Format support/resistance
        support_str = ", ".join([f"${s:.2f}" for s in support_levels]) if support_levels else "None identified"
        resistance_str = ", ".join([f"${r:.2f}" for r in resistance_levels]) if resistance_levels else "None identified"
        
        # Format confluences
        confluences_str = "\n".join([
            f"  - {c['factor']} ({c['category']}, weight: {c['weight']}, {c['timeframe']})"
            for c in confluences
        ]) if confluences else "  - No strong confluences identified"

        # Build the OUTPUT FORMAT example dynamically so its geometry matches the
        # requested direction. A static SHORT example (SL above entry, descending
        # TPs) gets copied verbatim by small models and produces invalid LONG
        # setups. Anchor the illustrative numbers to the actual price and ATR.
        ex_entry = current_price
        ex_risk = atr  # ~1 ATR stop distance for the illustration
        if direction == 'LONG':
            ex_stop = ex_entry - ex_risk          # stop below entry
            ex_tp1 = ex_entry + ex_risk * 1.5     # targets above entry (ascending)
            ex_tp2 = ex_entry + ex_risk * 2.5
            ex_tp3 = ex_entry + ex_risk * 3.5
        else:  # SHORT
            ex_stop = ex_entry + ex_risk          # stop above entry
            ex_tp1 = ex_entry - ex_risk * 1.5     # targets below entry (descending)
            ex_tp2 = ex_entry - ex_risk * 2.5
            ex_tp3 = ex_entry - ex_risk * 3.5

        prompt = f"""You are an expert crypto trader. Create the OPTIMAL trade setup for {symbol} based on the comprehensive market analysis below.

MARKET CONTEXT:
- Direction: {direction}
- Current Price: ${current_price:.2f}
- ATR (volatility): ${atr:.2f} ({volatility} volatility)
- HTF Trend: {market_structure['htf_trend']}
- MTF Trend: {market_structure['mtf_trend']}
- Overall Bias: {market_structure['overall_bias']}

IDENTIFIED ENTRY ZONES:
{entry_zones_str}

KEY LEVELS:
- Support Levels: {support_str}
- Resistance Levels: {resistance_str}

CONFLUENCES FOUND ({len(confluences)} total):
{confluences_str}

YOUR TASK:
Create the BEST possible trade setup with the following requirements:

1. **Entry Price**: Choose optimal entry within the identified zones (or slightly adjusted if better alignment exists)
2. **Stop Loss**: Place beyond key structure levels with ATR buffer for {volatility} volatility
3. **Take Profit Levels**: Set 3 targets at logical liquidity zones
4. **Risk-Reward Ratio**: MUST be ≥ {target_rr:.1f}
5. **Confidence Score**: Rate 0.0-1.0 based on setup quality

GUIDELINES:
- For {direction} trades:
  - Entry should be near {entry_zones[0]['low']:.2f} - {entry_zones[0]['high']:.2f}
  - Stop loss should be {"below" if direction == "LONG" else "above"} entry with ATR buffer
  - Take profits at next major support/resistance zones
  
- Account for {volatility} volatility:
  - {"Tighter" if volatility == "low" else "Wider"} stops recommended
  - {"Smaller" if volatility == "high" else "Larger"} position size appropriate

OUTPUT FORMAT (JSON only, no markdown) — example geometry for a {direction} trade
(stop {"below" if direction == "LONG" else "above"} entry, targets {"ascending" if direction == "LONG" else "descending"}):
{{
  "trade_setup": {{
    "entry_price": {ex_entry:.2f},
    "stop_loss": {ex_stop:.2f},
    "take_profit_levels": [
      {{"price": {ex_tp1:.2f}, "percentage": 33.33}},
      {{"price": {ex_tp2:.2f}, "percentage": 33.33}},
      {{"price": {ex_tp3:.2f}, "percentage": 33.34}}
    ],
    "risk_reward_ratio": 2.5,
    "confidence_score": 0.78,
    "setup_reasoning": "Concise rationale referencing the confluences above",
    "confluences": ["<confluence 1>", "<confluence 2>"],
    "direction": "{direction}",
    "symbol": "{symbol}"
  }}
}}

CRITICAL: Return ONLY the JSON object above. Do NOT include any explanations, reasoning, or conversational text. Start your response with {{ and end with }}. No markdown, no code blocks, just pure JSON. Ensure all strings are properly quoted and no trailing commas. Do not use comments // in the JSON."""

        return prompt
    
    def _clean_json_string(self, json_str: str) -> str:
        """Clean JSON string from LLM"""
        import re
        # Remove markdown code blocks if present (already handled in parse, but good to be safe)
        if "```" in json_str:
            json_str = re.sub(r'```json', '', json_str)
            json_str = re.sub(r'```', '', json_str)
            
        # Remove comments (// ...)
        json_str = re.sub(r'//.*', '', json_str)
        # Remove multi-line comments (/* ... */)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # Remove trailing commas before closing braces/brackets
        # This regex finds a comma followed by whitespace and a closing brace/bracket, and removes the comma
        json_str = re.sub(r',(\s*[\}\]])', r'\1', json_str)
        
        return json_str.strip()

    def _parse_llm_creator_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response for created trade setup - handles conversational responses from DeepSeek R1"""
        try:
            # Log raw content for debugging
            plog.debug(f"LLM response content (first 200 chars): {content[:200] if content else 'EMPTY'}", agent="strategy_agent")
            
            if not content or not content.strip():
                plog.error("LLM returned empty content", agent="strategy_agent")
                return None
            
            # DeepSeek R1 often adds conversational text before JSON
            # Try to extract JSON from the response
            
            # Method 1: Look for JSON object in markdown code blocks
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
                plog.debug("Extracted JSON from markdown code block", agent="strategy_agent")
            else:
                # Method 2: Look for JSON object anywhere in the text
                # Improved regex to capture nested braces
                json_match = re.search(r'(\{[\s\S]*\})', content)
                if json_match:
                    # Try to find the outermost valid JSON object
                    # This is a simple heuristic: find the first { and the last }
                    first_brace = content.find('{')
                    last_brace = content.rfind('}')
                    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                        content = content[first_brace:last_brace+1]
                        plog.debug("Extracted JSON from conversational text (heuristic)", agent="strategy_agent")
            
            # Clean up the content
            content = self._clean_json_string(content)
            
            # Parse JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try one more aggressive cleanup if simple load fails
                # Sometimes quotes are "smart quotes" or other issues
                content = content.replace('“', '"').replace('”', '"')
                result = json.loads(content)
            
            # Validate structure
            if 'trade_setup' not in result:
                plog.error("LLM response missing 'trade_setup' key", agent="strategy_agent")
                plog.debug(f"LLM response keys: {list(result.keys())}", agent="strategy_agent")
                return None
            
            setup = result['trade_setup']
            required_fields = ['entry_price', 'stop_loss', 'take_profit_levels', 'risk_reward_ratio', 'confidence_score']
            
            for field in required_fields:
                if field not in setup:
                    plog.error(f"LLM setup missing required field: {field}", agent="strategy_agent")
                    return None
            
            # Validate types
            setup['entry_price'] = float(setup['entry_price'])
            setup['stop_loss'] = float(setup['stop_loss'])
            setup['risk_reward_ratio'] = float(setup['risk_reward_ratio'])
            setup['confidence_score'] = float(setup['confidence_score'])
            
            # Validate TP levels
            if not isinstance(setup['take_profit_levels'], list) or len(setup['take_profit_levels']) == 0:
                plog.error("Invalid take_profit_levels in LLM setup", agent="strategy_agent")
                return None
            
            for tp in setup['take_profit_levels']:
                tp['price'] = float(tp['price'])
                tp['percentage'] = float(tp.get('percentage', 33.33))
            
            plog.debug(f"LLM setup parsed successfully: Entry ${setup['entry_price']:.2f}, RR {setup['risk_reward_ratio']:.2f}", agent="strategy_agent")
            
            return result
            
        except json.JSONDecodeError as e:
            plog.error(f"Failed to parse LLM JSON response: {e}", agent="strategy_agent")
            plog.debug(f"LLM response content (full): {content[:1000] if content else 'EMPTY'}", agent="strategy_agent")
            return None
        except Exception as e:
            plog.error(f"Error parsing LLM creator response: {e}", exception=e, agent="strategy_agent")
            return None
    
    def _validate_setup_safety(
        self,
        setup: Dict[str, Any],
        computational_context: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate LLM-created setup for SAFETY (not perfection)
        
        Relaxed validation - only check if setup is safe to execute
        """
        errors = []
        
        try:
            entry_price = float(setup['entry_price'])
            stop_loss = float(setup['stop_loss'])
            rr_ratio = float(setup['risk_reward_ratio'])
            confidence = float(setup['confidence_score'])
            direction = setup.get('direction', computational_context['direction'])
            tp_levels = setup['take_profit_levels']
            
            current_price = computational_context['current_price']
            entry_zones = computational_context['entry_zones']
            
            # 1. Entry is reasonable (within ±10% of identified zones)
            if entry_zones:
                zone_low = min(z['low'] for z in entry_zones)
                zone_high = max(z['high'] for z in entry_zones)
                buffer = current_price * 0.10  # 10% buffer
                
                if not (zone_low - buffer <= entry_price <= zone_high + buffer):
                    errors.append(f"Entry ${entry_price:.2f} too far from zones ${zone_low:.2f}-${zone_high:.2f}")
            
            # 2. Stop loss is logical
            if direction == 'SHORT':
                if stop_loss <= entry_price:
                    errors.append(f"SHORT stop loss ${stop_loss:.2f} must be above entry ${entry_price:.2f}")
            else:  # LONG
                if stop_loss >= entry_price:
                    errors.append(f"LONG stop loss ${stop_loss:.2f} must be below entry ${entry_price:.2f}")
            
            # 3. RR is acceptable (relaxed to 1.5)
            # Do NOT trust the LLM's self-reported risk_reward_ratio: recompute it
            # from entry/SL and the percentage-weighted take-profits, then reject if
            # the claimed value materially disagrees or the true RR is below floor.
            RR_FLOOR = 1.5
            risk = abs(entry_price - stop_loss)
            computed_rr = None
            if risk > 0 and tp_levels:
                weighted_reward = 0.0
                total_weight = 0.0
                for tp in tp_levels:
                    tp_price = float(tp['price'])
                    # weight by allocation percentage; default to equal weight if absent
                    weight = float(tp.get('percentage', 100.0 / len(tp_levels)))
                    # reward is signed by direction so wrong-side TPs reduce RR
                    if direction == 'SHORT':
                        reward = entry_price - tp_price
                    else:  # LONG
                        reward = tp_price - entry_price
                    weighted_reward += reward * weight
                    total_weight += weight
                if total_weight > 0:
                    computed_rr = (weighted_reward / total_weight) / risk

            if computed_rr is None:
                errors.append("Cannot compute RR (zero risk distance or no TPs)")
            else:
                # Judge safety on the recomputed RR, not the claimed one.
                if computed_rr < RR_FLOOR:
                    errors.append(f"Recomputed RR {computed_rr:.2f} below minimum {RR_FLOOR:.1f}")
                # Flag a materially inflated self-reported RR (LLM claiming a better
                # ratio than the geometry supports). Tolerance: 20% relative or 0.3 absolute.
                if abs(rr_ratio - computed_rr) > max(0.3, 0.20 * computed_rr):
                    errors.append(
                        f"Claimed RR {rr_ratio:.2f} disagrees with computed RR {computed_rr:.2f}"
                    )
            # Keep the original floor check on the claimed value as a cheap sanity gate.
            if rr_ratio < RR_FLOOR:
                errors.append(f"Claimed RR ratio {rr_ratio:.2f} below minimum {RR_FLOOR:.1f}")
            
            # 4. Confidence is reasonable
            if confidence < 0.3 or confidence > 1.0:
                errors.append(f"Confidence {confidence:.2f} out of range [0.3, 1.0]")
            
            # 5. TPs are achievable
            if not tp_levels or len(tp_levels) == 0:
                errors.append("No take profit levels defined")
            else:
                for i, tp in enumerate(tp_levels):
                    tp_price = float(tp['price'])
                    
                    if direction == 'SHORT':
                        if tp_price >= entry_price:
                            errors.append(f"SHORT TP{i+1} ${tp_price:.2f} must be below entry ${entry_price:.2f}")
                    else:  # LONG
                        if tp_price <= entry_price:
                            errors.append(f"LONG TP{i+1} ${tp_price:.2f} must be above entry ${entry_price:.2f}")
            
            # 6. Risk distance is not too small (avoid over-leverage)
            risk_distance = abs(entry_price - stop_loss)
            min_risk = current_price * 0.001  # Minimum 0.1% risk distance (lowered from 0.5% to allow scalps)
            
            if risk_distance < min_risk:
                errors.append(f"Risk distance ${risk_distance:.2f} too small (min ${min_risk:.2f})")
            
            is_safe = len(errors) == 0
            
            if is_safe:
                plog.debug("✅ LLM setup passed all safety checks", agent="strategy_agent")
            else:
                plog.warning(f"❌ LLM setup failed safety checks: {errors}", agent="strategy_agent")
            
            return is_safe, errors
            
        except Exception as e:
            plog.error(f"Error validating setup safety: {e}", exception=e, agent="strategy_agent")
            return False, [f"Validation error: {str(e)}"]
