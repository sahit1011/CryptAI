"""
LangGraph Orchestrator
Master coordinator for multi-agent trading system using LangGraph
"""
from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime, timedelta
import asyncio
from enum import Enum

from langgraph.graph import StateGraph, END
# Removed ToolExecutor import - not needed for our implementation
from loguru import logger

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class WorkflowPhase(Enum):
    """Workflow execution phases"""
    IDLE = "idle"
    DATA_COLLECTION = "data_collection"
    MARKET_ANALYSIS = "market_analysis"
    REGIME_DETECTION = "regime_detection"
    STRATEGY_GENERATION = "strategy_generation"
    RISK_VALIDATION = "risk_validation"
    EXECUTION = "execution"
    MEMORY_LOGGING = "memory_logging"
    COMPLETE = "complete"
    ERROR = "error"


class TradingState(TypedDict):
    """State schema for trading workflow"""
    # Cycle metadata
    cycle_id: str
    cycle_start: datetime
    cycle_number: int
    phase: str
    
    # Market data
    symbol: str
    market_data: Optional[Dict[str, Any]]
    candles: Optional[List[Dict]]
    
    # Analysis results
    analysis_result: Optional[Dict[str, Any]]
    regime: Optional[Dict[str, Any]]
    
    # Strategy outputs
    opportunities: List[Dict[str, Any]]
    selected_setup: Optional[Dict[str, Any]]
    
    # Risk validation
    risk_validation: Optional[Dict[str, Any]]
    approved_for_execution: bool
    
    # Execution
    execution_result: Optional[Dict[str, Any]]
    trade_id: Optional[str]
    
    # Error handling
    errors: List[str]
    retry_count: int
    
    # Workflow control
    should_continue: bool
    next_phase: Optional[str]


class TradingOrchestrator:
    """
    LangGraph-based Trading Orchestrator
    
    Coordinates all agents in a structured 3-minute trading cycle:
    1. Data Collection (Data Agent)
    2. Market Analysis (Analysis Agent)
    3. Regime Detection (Memory Agent)
    4. Strategy Generation (Strategy Agent)
    5. Risk Validation (Risk Agent)
    6. Execution (Execution Agent)
    7. Memory Logging (Memory Agent)
    
    Uses LangGraph for workflow state management and Message Bus for agent communication.
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        symbol: str = "BTCUSDT",
        cycle_interval: int = 180,  # 3 minutes in seconds
        max_retries: int = 3
    ):
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.symbol = symbol
        self.cycle_interval = cycle_interval
        self.max_retries = max_retries
        
        # Workflow state
        self.running = False
        self.current_cycle = 0
        self.total_cycles_completed = 0
        self.total_trades_executed = 0
        
        # Build LangGraph workflow
        self.workflow = self._build_workflow()
        self.app = self.workflow.compile()
        
        plog.info(
            f"Trading Orchestrator initialized | symbol={symbol} | cycle={cycle_interval}s",
            agent="orchestrator",
            phase="initialization"
        )
    
    def _build_workflow(self) -> StateGraph:
        """Build LangGraph workflow"""
        
        # Create state graph
        workflow = StateGraph(TradingState)
        
        # Add nodes for each phase
        workflow.add_node("collect_data", self._collect_data_node)
        workflow.add_node("analyze_market", self._analyze_market_node)
        workflow.add_node("detect_regime", self._detect_regime_node)
        workflow.add_node("generate_strategies", self._generate_strategies_node)
        workflow.add_node("validate_risk", self._validate_risk_node)
        workflow.add_node("execute_trade", self._execute_trade_node)
        workflow.add_node("log_memory", self._log_memory_node)
        workflow.add_node("handle_error", self._handle_error_node)
        
        # Set entry point
        workflow.set_entry_point("collect_data")

        # Add edges (transitions). Every node that can populate state['errors']
        # short-circuits to handle_error instead of feeding garbage (e.g. a failed
        # data fetch) into the expensive downstream LLM nodes. This also makes
        # handle_error reachable, which is required for the graph to compile.
        workflow.add_conditional_edges(
            "collect_data",
            self._error_gate,
            {
                "error": "handle_error",
                "ok": "analyze_market"
            }
        )
        workflow.add_conditional_edges(
            "analyze_market",
            self._error_gate,
            {
                "error": "handle_error",
                "ok": "detect_regime"
            }
        )

        # Conditional edge after regime detection
        workflow.add_conditional_edges(
            "detect_regime",
            self._should_generate_strategies,
            {
                "error": "handle_error",
                "generate": "generate_strategies",
                "skip": END
            }
        )

        # Conditional edge after strategy generation
        workflow.add_conditional_edges(
            "generate_strategies",
            self._has_opportunities,
            {
                "error": "handle_error",
                "validate": "validate_risk",
                "skip": END
            }
        )
        
        # Conditional edge after risk validation
        workflow.add_conditional_edges(
            "validate_risk",
            self._is_approved,
            {
                "execute": "execute_trade",
                "reject": "log_memory"
            }
        )
        
        workflow.add_edge("execute_trade", "log_memory")
        workflow.add_edge("log_memory", END)
        
        # Error handling edges
        workflow.add_conditional_edges(
            "handle_error",
            self._should_retry,
            {
                "retry": "collect_data",
                "abort": END
            }
        )
        
        return workflow
    
    async def _collect_data_node(self, state: TradingState) -> TradingState:
        """Node: Collect market data from Data Agent"""
        plog.info(
            f"📊 [Cycle {state['cycle_number']}] Collecting market data",
            agent="orchestrator",
            phase="data_collection"
        )
        
        try:
            # Request data from Data Agent via message bus
            correlation_id = state['cycle_id']
            message_id = await self.message_bus.publish(
                "data_agent_inbox",
                {
                    "id": f"data_req_{state['cycle_id']}",
                    "correlation_id": correlation_id,
                    "sender": "orchestrator",
                    "receiver": "data_agent",
                    "type": "get_market_data",
                    "payload": {
                        "symbol": state['symbol'],
                        "limit": 100
                    },
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Wait for response (with timeout and correlation ID)
            response = await self._wait_for_response("data_agent", timeout=30, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['market_data'] = response.get('data')
                state['candles'] = response.get('candles', [])
                
                # Debug logging
                candles_data = state['candles']
                if isinstance(candles_data, dict):
                    candle_counts = {k: len(v) for k, v in candles_data.items()}
                    plog.info(f"🔍 Received candles: {candle_counts}", agent="orchestrator")
                else:
                    plog.warning(f"⚠️ Received candles is not a dict: {type(candles_data)}", agent="orchestrator")
                
                state['phase'] = WorkflowPhase.DATA_COLLECTION.value
                plog.info("✅ Market data collected successfully", agent="orchestrator")
            else:
                raise Exception("Failed to collect market data")
                
        except Exception as e:
            plog.error(f"❌ Data collection error: {e}", agent="orchestrator")
            state['errors'].append(f"Data collection: {str(e)}")
            state['phase'] = WorkflowPhase.ERROR.value
        
        return state
    
    async def _analyze_market_node(self, state: TradingState) -> TradingState:
        """Node: Analyze market with Analysis Agent"""
        plog.info(
            f"🔍 [Cycle {state['cycle_number']}] Analyzing market",
            agent="orchestrator",
            phase="market_analysis"
        )
        
        try:
            # CRITICAL FIX: Log what we're about to send
            candles_to_send = state['candles']
            if isinstance(candles_to_send, dict):
                candle_counts = {tf: len(v) if isinstance(v, list) else 0 
                                for tf, v in candles_to_send.items()}
                plog.info(
                    f"📤 Orchestrator sending candles to analysis agent: {candle_counts}",
                    agent="orchestrator"
                )
                
                # DEBUGGING: Log sample candle structure
                for tf, candle_list in candles_to_send.items():
                    if candle_list and len(candle_list) > 0:
                        sample_candle = candle_list[0]
                        plog.debug(
                            f"📤 Sample {tf} candle keys: {list(sample_candle.keys()) if isinstance(sample_candle, dict) else 'N/A'}",
                            agent="orchestrator"
                        )
                        if isinstance(sample_candle, dict) and 'timestamp' in sample_candle:
                            plog.debug(
                                f"📤 Sample {tf} timestamp type: {type(sample_candle['timestamp'])}",
                                agent="orchestrator"
                            )
                        break  # Only log one sample
            else:
                plog.warning(
                    f"⚠️ Candles in state is not a dict! Type: {type(candles_to_send)}",
                    agent="orchestrator"
                )
            
            # DEBUGGING: Create payload and log its structure
            payload_to_send = {
                "symbol": state['symbol'],
                "candles": state['candles'],
                "market_data": state['market_data']
            }
            
            plog.debug(
                f"📤 Payload keys: {list(payload_to_send.keys())}",
                agent="orchestrator"
            )
            plog.debug(
                f"📤 Payload.candles type: {type(payload_to_send['candles'])}",
                agent="orchestrator"
            )
            
            # Send to Analysis Agent
            correlation_id = state['cycle_id']
            message_to_publish = {
                "id": f"analysis_req_{state['cycle_id']}",
                "correlation_id": correlation_id,
                "sender": "orchestrator",
                "receiver": "analysis_agent",
                "type": "analyze_market",
                "payload": payload_to_send,
                "timestamp": datetime.now().isoformat()
            }
            
            plog.debug(
                f"📤 Message keys before publish: {list(message_to_publish.keys())}",
                agent="orchestrator"
            )
            plog.debug(
                f"📤 Message.payload.candles type: {type(message_to_publish['payload']['candles'])}",
                agent="orchestrator"
            )
            
            await self.message_bus.publish(
                "analysis_agent_inbox",
                message_to_publish
            )
            
            # CRITICAL FIX: Analysis Agent uses LLM which can take 60-90s, increase timeout
            response = await self._wait_for_response("analysis_agent", timeout=120, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['analysis_result'] = response.get('analysis')
                state['phase'] = WorkflowPhase.MARKET_ANALYSIS.value
                plog.info("✅ Market analysis complete", agent="orchestrator")
            else:
                raise Exception("Market analysis failed")
                
        except Exception as e:
            plog.error(f"❌ Analysis error: {e}", agent="orchestrator")
            state['errors'].append(f"Market analysis: {str(e)}")
            state['phase'] = WorkflowPhase.ERROR.value
        
        return state
    
    async def _detect_regime_node(self, state: TradingState) -> TradingState:
        """Node: Detect market regime with Memory Agent"""
        plog.info(
            f"🎯 [Cycle {state['cycle_number']}] Detecting market regime",
            agent="orchestrator",
            phase="regime_detection"
        )
        
        try:
            # CRITICAL FIX: Regime detection is optional - Analysis Agent already provides regime
            # Try Memory Agent for enhanced regime analysis, but don't fail if it times out
            
            # Send to Memory Agent
            correlation_id = state['cycle_id']
            await self.message_bus.publish(
                "memory_agent_inbox",
                {
                    "id": f"regime_req_{state['cycle_id']}",
                    "correlation_id": correlation_id,
                    "sender": "orchestrator",
                    "receiver": "memory_agent",
                    "type": "get_regime_analysis",
                    "payload": {
                        "candles": state['candles'],
                        "symbol": state['symbol']
                    },
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            response = await self._wait_for_response("memory_agent", timeout=30, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['regime'] = response.get('regime')
                state['phase'] = WorkflowPhase.REGIME_DETECTION.value
                plog.info(
                    f"✅ Regime detected from Memory Agent: {state['regime'].get('regime')}",
                    agent="orchestrator"
                )
            else:
                # FALLBACK: Use regime from Analysis Agent
                plog.warning(
                    "Memory Agent timeout - using regime from Analysis Agent",
                    agent="orchestrator"
                )
                # FIX: TradingState only defines 'analysis_result' (set by the
                # analyze_market node). The old code read a non-existent
                # 'analysis' key, so this fallback never populated the regime.
                if state.get('analysis_result') and state['analysis_result'].get('market_regime'):
                    state['regime'] = state['analysis_result']['market_regime']
                    state['phase'] = WorkflowPhase.REGIME_DETECTION.value
                    plog.info(
                        f"✅ Regime: {state['regime'].get('type', 'UNKNOWN')} (using fallback - Analysis Agent provides actual regime)",
                        agent="orchestrator"
                    )
                else:
                    # Use default regime if Analysis Agent didn't provide one
                    state['regime'] = {
                        'type': 'UNKNOWN',
                        'confidence': 0.0,
                        'trend_strength': 0.0,
                        'volatility_level': 'medium',
                        'reasoning': 'Regime detection not available'
                    }
                    state['phase'] = WorkflowPhase.REGIME_DETECTION.value
                    plog.info(
                        f"✅ Regime: UNKNOWN (using fallback - Analysis Agent provides actual regime)",
                        agent="orchestrator"
                    )
                
        except Exception as e:
            # CRITICAL FIX: Don't fail the cycle - use fallback regime
            plog.warning(f"Regime detection error: {e}, using fallback", agent="orchestrator")
            # FIX: read 'analysis_result' (the real state key), not 'analysis'.
            if state.get('analysis_result') and state['analysis_result'].get('market_regime'):
                state['regime'] = state['analysis_result']['market_regime']
            else:
                state['regime'] = {
                    'type': 'UNKNOWN',
                    'confidence': 0.0,
                    'trend_strength': 0.0,
                    'volatility_level': 'medium',
                    'reasoning': 'Regime detection failed'
                }
            state['phase'] = WorkflowPhase.REGIME_DETECTION.value
        
        return state
    
    async def _generate_strategies_node(self, state: TradingState) -> TradingState:
        """Node: Generate trade strategies with Strategy Agent"""
        plog.info(
            f"💡 [Cycle {state['cycle_number']}] Generating strategies",
            agent="orchestrator",
            phase="strategy_generation"
        )
        
        try:
            # Send to Strategy Agent
            correlation_id = state['cycle_id']
            
            # Extract candles for Strategy Agent (15m for swing trading entry confirmation)
            candles_for_strategy = {}
            if isinstance(state.get('candles'), dict):
                # Pass 15m candles for swing trading entries (primary)
                if '15m' in state['candles']:
                    candles_for_strategy['15m'] = state['candles']['15m']
                # Also pass 5m for precision entries and 1h for trend context
                if '5m' in state['candles']:
                    candles_for_strategy['5m'] = state['candles']['5m']
                if '1h' in state['candles']:
                    candles_for_strategy['1h'] = state['candles']['1h']
            
            await self.message_bus.publish(
                "strategy_agent_inbox",
                {
                    "id": f"strategy_req_{state['cycle_id']}",
                    "correlation_id": correlation_id,
                    "sender": "orchestrator",
                    "receiver": "strategy_agent",
                    "type": "generate_setups",
                    "payload": {
                        "symbol": state['symbol'],
                        "analysis": state['analysis_result'],
                        "regime": state['regime'],
                        "market_data": state['market_data'],
                        "candles": candles_for_strategy  # Add candles for LLM context
                    },
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # CRITICAL FIX: Strategy Agent uses LLM for refinement which can take 30-60s, increase timeout
            response = await self._wait_for_response("strategy_agent", timeout=90, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['opportunities'] = response.get('setups', [])
                if state['opportunities']:
                    state['selected_setup'] = state['opportunities'][0]  # Take best setup
                state['phase'] = WorkflowPhase.STRATEGY_GENERATION.value
                plog.info(
                    f"✅ Generated {len(state['opportunities'])} opportunities",
                    agent="orchestrator"
                )
            else:
                state['opportunities'] = []
                plog.info("ℹ️ No opportunities found", agent="orchestrator")
                
        except Exception as e:
            plog.error(f"❌ Strategy generation error: {e}", agent="orchestrator")
            state['errors'].append(f"Strategy generation: {str(e)}")
            state['phase'] = WorkflowPhase.ERROR.value
        
        return state
    
    async def _validate_risk_node(self, state: TradingState) -> TradingState:
        """Node: Validate trade with Risk Agent"""
        plog.info(
            f"🛡️ [Cycle {state['cycle_number']}] Validating risk",
            agent="orchestrator",
            phase="risk_validation"
        )
        
        try:
            # CRITICAL FIX: Check if selected_setup exists before validating
            if not state.get('selected_setup'):
                plog.warning(
                    "⚠️ No setup selected for risk validation (likely filtered out due to low RR or confidence)",
                    agent="orchestrator"
                )
                state['approved_for_execution'] = False
                state['risk_validation'] = {
                    'approved': False,
                    'reason': 'No valid setup to validate'
                }
                state['phase'] = WorkflowPhase.RISK_VALIDATION.value
                return state
            
            # Send to Risk Agent
            correlation_id = state['cycle_id']
            await self.message_bus.publish(
                "risk_agent_inbox",
                {
                    "id": f"risk_req_{state['cycle_id']}",
                    "correlation_id": correlation_id,
                    "sender": "orchestrator",
                    "receiver": "risk_agent",
                    "type": "validate_trade",
                    "payload": state['selected_setup'],
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            response = await self._wait_for_response("risk_agent", timeout=30, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['risk_validation'] = response.get('result')
                state['approved_for_execution'] = response.get('approved', False)
                state['phase'] = WorkflowPhase.RISK_VALIDATION.value
                
                if state['approved_for_execution']:
                    plog.info("✅ Trade approved by risk management", agent="orchestrator")
                else:
                    plog.warning("⚠️ Trade rejected by risk management", agent="orchestrator")
            else:
                raise Exception("Risk validation failed")
                
        except Exception as e:
            plog.error(f"❌ Risk validation error: {e}", agent="orchestrator")
            state['errors'].append(f"Risk validation: {str(e)}")
            state['phase'] = WorkflowPhase.ERROR.value
            state['approved_for_execution'] = False
        
        return state
    
    async def _execute_trade_node(self, state: TradingState) -> TradingState:
        """Node: Execute trade with Execution Agent"""
        plog.info(
            f"⚡ [Cycle {state['cycle_number']}] Executing trade",
            agent="orchestrator",
            phase="execution"
        )
        
        try:
            # Send to Execution Agent
            correlation_id = state['cycle_id']
            await self.message_bus.publish(
                "execution_agent_inbox",
                {
                    "id": f"execution_req_{state['cycle_id']}",
                    "correlation_id": correlation_id,
                    "sender": "orchestrator",
                    "receiver": "execution_agent",
                    "type": "execute_trade",
                    "payload": state['selected_setup'],
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            response = await self._wait_for_response("execution_agent", timeout=60, correlation_id=correlation_id)
            
            if response and response.get('success'):
                state['execution_result'] = response
                state['trade_id'] = response.get('execution_id', f"trade_{state['cycle_id']}")
                state['phase'] = WorkflowPhase.EXECUTION.value
                
                self.total_trades_executed += 1
                
                plog.success(
                    f"✅ Trade execution successful: {state['trade_id']}",
                    agent="orchestrator"
                )
            else:
                error_msg = response.get('error', 'Unknown error') if response else 'No response from execution agent'
                raise Exception(f"Execution failed: {error_msg}")
                
        except Exception as e:
            plog.error(f"❌ Execution error: {e}", agent="orchestrator")
            state['errors'].append(f"Execution: {str(e)}")
            state['phase'] = WorkflowPhase.ERROR.value
        
        return state
    
    async def _log_memory_node(self, state: TradingState) -> TradingState:
        """Node: Log results to Memory Agent"""
        plog.info(
            f"💾 [Cycle {state['cycle_number']}] Logging to memory",
            agent="orchestrator",
            phase="memory_logging"
        )
        
        try:
            # Log trade if executed
            if state.get('trade_id') and state.get('approved_for_execution'):
                # CRITICAL FIX: Add correlation_id for proper response matching
                correlation_id = f"log_{state['cycle_id']}"
                await self.message_bus.publish(
                    "memory_agent_inbox",
                    {
                        "id": f"log_req_{state['cycle_id']}",
                        "correlation_id": correlation_id,  # CRITICAL FIX: Added correlation_id
                        "sender": "orchestrator",
                        "receiver": "memory_agent",
                        "type": "log_trade",
                        "payload": {
                            **state['selected_setup'],
                            'trade_id': state['trade_id'],
                            'entry_time': datetime.now().isoformat()
                        },
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                # CRITICAL FIX: Wait for response from memory agent
                response = await self._wait_for_response("memory_agent", timeout=10, correlation_id=correlation_id)
                
                if response and response.get('success'):
                    plog.info("✅ Trade logged to memory", agent="orchestrator")
                else:
                    plog.warning("⚠️ Memory logging timeout (non-critical)", agent="orchestrator")
            
            state['phase'] = WorkflowPhase.COMPLETE.value
            plog.info("✅ Cycle complete", agent="orchestrator")
            
        except Exception as e:
            plog.error(f"❌ Memory logging error: {e}", agent="orchestrator")
            state['errors'].append(f"Memory logging: {str(e)}")
        
        return state
    
    async def _handle_error_node(self, state: TradingState) -> TradingState:
        """Node: Handle errors and decide retry strategy"""
        plog.error(
            f"❌ [Cycle {state['cycle_number']}] Error handling",
            agent="orchestrator",
            phase="error_handling"
        )
        
        state['retry_count'] += 1

        if state['retry_count'] < self.max_retries:
            plog.info(f"🔄 Retrying cycle (attempt {state['retry_count']})", agent="orchestrator")
            state['should_continue'] = True
            # Clear the recorded errors so the retried run starts clean; otherwise
            # the error gate would immediately route back here and burn every retry.
            state['errors'] = []
        else:
            plog.error("❌ Max retries reached, aborting cycle", agent="orchestrator")
            state['should_continue'] = False

        return state
    
    # Conditional edge functions

    def _error_gate(self, state: TradingState) -> str:
        """Route to the error handler when a node has recorded an error."""
        return "error" if state.get('errors') else "ok"

    def _should_generate_strategies(self, state: TradingState) -> str:
        """Decide if we should generate strategies based on regime"""
        if state.get('errors'):
            return "error"

        regime = state.get('regime', {}) or {}
        # Regime dicts come from two sources with different key names:
        #   - Memory Agent (MarketRegimeDetector): {'regime': 'volatile', ...}
        #   - Analysis Agent fallback:             {'type': 'volatile', ...}
        # Check both so the volatile skip fires regardless of source.
        regime_type = str(regime.get('regime') or regime.get('type') or '')

        # Skip if regime is unfavorable (e.g., highly volatile)
        if 'volatile' in regime_type.lower():
            plog.info("ℹ️ Skipping strategy generation due to volatile regime", agent="orchestrator")
            return "skip"

        return "generate"
    
    def _has_opportunities(self, state: TradingState) -> str:
        """Check if any opportunities were found"""
        if state.get('errors'):
            return "error"

        if state.get('opportunities') and len(state['opportunities']) > 0:
            return "validate"
        
        plog.info("ℹ️ No opportunities found, skipping validation", agent="orchestrator")
        return "skip"
    
    def _is_approved(self, state: TradingState) -> str:
        """Check if trade was approved by risk management"""
        if state.get('approved_for_execution'):
            return "execute"
        return "reject"
    
    def _should_retry(self, state: TradingState) -> str:
        """Decide if we should retry after error"""
        if state.get('should_continue') and state.get('retry_count', 0) < self.max_retries:
            return "retry"
        return "abort"
    
    # Helper methods
    
    async def _wait_for_response(self, agent_name: str, timeout: int = 30, correlation_id: str = None) -> Optional[Dict]:
        """
        Wait for response from an agent via message bus using event-based approach.
        
        CRITICAL FIX: Replaced blocking polling with asyncio.Event for efficient waiting.
        This eliminates the double-waiting issue (0.5s poll + 0.1s sleep) and reduces
        CPU usage while maintaining responsiveness.
        
        Args:
            agent_name: Name of the agent to wait for response from
            timeout: Maximum seconds to wait for response
            correlation_id: Optional correlation ID to match request/response
            
        Returns:
            Response dict from agent, or None if timeout
        """
        try:
            # Response channel format: {agent_name}_response
            response_channel = f"{agent_name}_response"
            
            plog.debug(
                f"Waiting for response from {agent_name} (timeout={timeout}s, correlation_id={correlation_id})",
                agent="orchestrator"
            )
            
            # Use event-based waiting instead of polling
            response_event = asyncio.Event()
            response_data = {}
            
            async def response_handler(message):
                """Handler for incoming responses"""
                # If correlation_id is provided, only accept matching responses
                if correlation_id and message.get('correlation_id') != correlation_id:
                    plog.debug(
                        f"Ignoring response with mismatched correlation_id: {message.get('correlation_id')} != {correlation_id}",
                        agent="orchestrator"
                    )
                    return
                
                response_data.update(message)
                response_event.set()
            
            # Subscribe to response channel
            await self.message_bus.subscribe(response_channel, response_handler)
            
            try:
                # Wait for event with timeout
                await asyncio.wait_for(response_event.wait(), timeout=timeout)
                
                plog.success(
                    f"Received response from {agent_name}",
                    agent="orchestrator"
                )
                return response_data
                
            except asyncio.TimeoutError:
                plog.warning(
                    f"Timeout waiting for response from {agent_name} after {timeout}s",
                    agent="orchestrator"
                )
                return None
                
            finally:
                # Remove only THIS waiter's handler so concurrent waiters on the same
                # response channel keep listening.
                await self.message_bus.unsubscribe(response_channel, response_handler)
            
        except Exception as e:
            plog.error(
                f"Error waiting for response from {agent_name}: {e}",
                exception=e,
                agent="orchestrator"
            )
            return None
    
    async def start(self):
        """Start the orchestrator"""
        if self.running:
            plog.warning("Orchestrator already running", agent="orchestrator")
            return
        
        self.running = True
        plog.info("🚀 Trading Orchestrator started", agent="orchestrator", phase="startup")
        
        # Start cycle loop
        asyncio.create_task(self._cycle_loop())
    
    async def stop(self):
        """Stop the orchestrator"""
        self.running = False
        plog.info("🛑 Trading Orchestrator stopped", agent="orchestrator", phase="shutdown")
    
    async def run_cycle(self) -> TradingState:
        """
        Run a single trading cycle
        
        Returns:
            Final state of the cycle
        """
        try:
            # Step 0: Check for active trades before starting cycle
            # We don't want to open new trades if one is already running
            active_check = await self._wait_for_response("execution_agent", timeout=5, correlation_id=f"check_{self.current_cycle}")
            
            # If we can't get status, we assume it's safe to proceed (or we could be conservative and skip)
            # But we need to send the request first.
            # Actually, let's send the request first.
            
            check_id = f"check_{self.current_cycle}_{int(datetime.now().timestamp())}"
            await self.message_bus.publish(
                "execution_agent_inbox",
                {
                    "id": check_id,
                    "correlation_id": check_id,
                    "sender": "orchestrator",
                    "receiver": "execution_agent",
                    "type": "get_status",
                    "payload": {},
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            status_response = await self._wait_for_response("execution_agent", timeout=5, correlation_id=check_id)
            
            if status_response and status_response.get('success'):
                agent_status = status_response.get('agent_status', {})
                active_positions = agent_status.get('active_positions', 0)
                
                if active_positions > 0:
                    plog.info(
                        f"⏸️ Active trade in progress ({active_positions} positions). Skipping cycle to wait for completion.",
                        agent="orchestrator",
                        phase="cycle_skipped"
                    )
                    return {
                        "phase": "skipped",
                        "reason": "active_trade",
                        "active_positions": active_positions
                    }
            
            self.current_cycle += 1
            
            # Create initial state
            initial_state: TradingState = {
                "cycle_id": f"cycle_{self.current_cycle}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "cycle_start": datetime.now(),
                "cycle_number": self.current_cycle,
                "phase": WorkflowPhase.IDLE.value,
                "symbol": self.symbol,
                "market_data": None,
                "candles": None,
                "analysis_result": None,
                "regime": None,
                "opportunities": [],
                "selected_setup": None,
                "risk_validation": None,
                "approved_for_execution": False,
                "execution_result": None,
                "trade_id": None,
                "errors": [],
                "retry_count": 0,
                "should_continue": True,
                "next_phase": None
            }
            
            plog.info(
                f"🔄 Starting cycle {self.current_cycle}",
                agent="orchestrator",
                phase="cycle_start"
            )
            
            # Execute workflow
            final_state = await self.app.ainvoke(initial_state)
            
            # Log cycle completion
            cycle_duration = (datetime.now() - initial_state['cycle_start']).total_seconds()
            
            plog.info(
                f"✅ Cycle {self.current_cycle} complete | duration={cycle_duration:.1f}s | phase={final_state.get('phase')}",
                agent="orchestrator",
                phase="cycle_complete"
            )
            
            self.total_cycles_completed += 1
            
            return final_state
            
        except Exception as e:
            plog.error(
                f"❌ Cycle {self.current_cycle} failed: {e}",
                agent="orchestrator",
                phase="cycle_error"
            )
            raise e

    async def _cycle_loop(self):
        """Main cycle execution loop"""
        while self.running:
            try:
                await self.run_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(self.cycle_interval)
                
            except Exception as e:
                plog.error(f"Error in cycle loop: {e}", agent="orchestrator")
                await asyncio.sleep(self.cycle_interval)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            "running": self.running,
            "current_cycle": self.current_cycle,
            "total_cycles_completed": self.total_cycles_completed,
            "total_trades_executed": self.total_trades_executed,
            "symbol": self.symbol,
            "cycle_interval": self.cycle_interval
        }
