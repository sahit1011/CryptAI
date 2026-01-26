"""
Risk Management Agent
Main agent that orchestrates all risk components and validates trades
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import os

from src.agents.base_agent import BaseAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager
from src.risk.portfolio_state_tracker import PortfolioStateTracker
from src.risk.risk_rules_engine import RiskRulesEngine, RiskParameters
from src.risk.llm_risk_advisor import LLMRiskAdvisor
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


class RiskManagementAgent(BaseAgent):
    """
    Risk Management Agent - Guardian of Capital
    
    Responsibilities:
    - Validate trade setups against risk parameters
    - Monitor portfolio exposure and heat
    - Enforce per-trade and portfolio risk limits
    - Track and limit drawdowns
    - Analyze correlation risk
    - Provide circuit breaker functionality
    - Generate risk reports and alerts
    
    Message Handlers:
    - validate_trade: Validate incoming trade setup
    - get_risk_status: Return current risk state
    - update_position: Update position state
    - close_position: Handle position closure
    - get_risk_report: Generate risk report
    - trigger_circuit_breaker: Manual circuit breaker trigger
    - reset_circuit_breaker: Reset circuit breaker
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        state_manager: StateManager,
        initial_balance: float = 10000.0,
        risk_params: Optional[RiskParameters] = None,
        enable_llm: bool = True,
        llm_api_key: Optional[str] = None
    ):
        super().__init__(
            name="risk_agent",
            message_bus=message_bus,
            state_manager=state_manager
        )
        
        # Initialize portfolio tracker
        self.portfolio_tracker = PortfolioStateTracker(
            initial_balance=initial_balance,
            state_manager=state_manager,
            snapshot_dir="data/snapshots"
        )
        
        # Initialize risk rules engine
        self.risk_engine = RiskRulesEngine(
            portfolio_tracker=self.portfolio_tracker,
            risk_params=risk_params,
            enable_circuit_breaker=True
        )
        
        # Initialize LLM advisor
        api_key = llm_api_key or os.getenv("OPENAI_API_KEY")
        self.llm_advisor = LLMRiskAdvisor(
            api_key=api_key,
            model="gpt-4o-mini",
            enabled=enable_llm
        )
        
        # Statistics
        self.trades_validated = 0
        self.trades_approved = 0
        self.trades_rejected = 0
        self.llm_consultations = 0
        
        plog.info(
            f"Risk Management Agent initialized | balance=${initial_balance:,.2f}",
            agent="risk_agent",
            phase="initialization"
        )
    
    def _setup_handlers(self):
        """Setup message handlers"""
        self.register_handler("validate_trade", self._handle_validate_trade)
        self.register_handler("get_risk_status", self._handle_get_risk_status)
        self.register_handler("update_position", self._handle_update_position)
        self.register_handler("close_position", self._handle_close_position)
        self.register_handler("get_risk_report", self._handle_get_risk_report)
        self.register_handler("trigger_circuit_breaker", self._handle_trigger_circuit_breaker)
        self.register_handler("reset_circuit_breaker", self._handle_reset_circuit_breaker)
        self.register_handler("get_portfolio_snapshot", self._handle_get_portfolio_snapshot)
    
    async def process_message(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """
        Process incoming message
        
        PHASE 2 FIX: Now sends responses back to orchestrator for sequential execution
        """
        handler = self.handlers.get(message.type)
        
        if handler:
            result = await handler(message.payload)
            # PHASE 2 FIX: Send response to orchestrator if sender is orchestrator
            if message.sender == "orchestrator":
                # Ensure result has success flag
                if isinstance(result, dict) and 'success' not in result:
                    # 'success' means the message was processed successfully, NOT that the trade was approved
                    result['success'] = True
                
                # CRITICAL FIX: Pass correlation_id so orchestrator can match response to request
                await self.send_response(result, correlation_id=message.correlation_id)
                plog.debug(
                    f"Sent response to orchestrator for {message.type} (correlation_id={message.correlation_id})",
                    agent="risk_agent"
                )
            
            return result
        else:
            plog.warning(
                f"No handler for message type: {message.type}",
                agent="risk_agent",
                phase="message_processing"
            )
            error_response = {"status": "no_handler", "success": False}
            
            # Send error response to orchestrator if needed
            if message.sender == "orchestrator":
                # CRITICAL FIX: Pass correlation_id for error responses too
                await self.send_response(error_response, correlation_id=message.correlation_id)
                
            return None
    
    async def validate_trade(self, setup: Dict[str, Any]) -> Dict[str, Any]:
        """
        Public method to validate a trade setup (wraps _handle_validate_trade)
        
        Args:
            setup: Trade setup dictionary
            
        Returns:
            Validation result
        """
        return await self._handle_validate_trade(setup)

    async def _handle_validate_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate trade setup
        
        Payload:
            symbol, direction, entry_price, stop_loss, take_profit_levels,
            recommended_position_size, risk_amount, confidence_score, market_regime
        """
        self.trades_validated += 1
        
        # Extract from either flat payload or nested trade_setup
        trade_setup = payload.get('trade_setup', payload)
        
        # Try to get symbol and direction from both locations
        symbol = trade_setup.get('symbol') or payload.get('symbol')
        direction = trade_setup.get('direction') or payload.get('direction')
        
        plog.info(
            f"📨 Received trade validation request: {symbol} {direction}",
            agent="risk_agent",
            phase="trade_validation"
        )
        
        # Publish activity
        await self.publish_activity(
            action="validating_trade",
            message=f"Validating {direction} trade for {symbol}",
            phase="risk_assessment",
            severity="info",
            metadata={
                "symbol": symbol,
                "direction": direction,
                "entry": trade_setup.get('entry_price', 0)
            }
        )

        
        # Validate we have minimum required data
        if not symbol or not direction:
            plog.error(
                f"Missing required fields - symbol: {symbol}, direction: {direction}",
                agent="risk_agent",
                phase="trade_validation"
            )
            return {
                'validated': False,
                'approved': False,
                'error': 'Missing required fields: symbol or direction',
                'timestamp': datetime.now().isoformat()
            }
        
        plog.info(
            f"🔍 Validating trade: {symbol} {direction} @ ${trade_setup.get('entry_price', 0):.2f}",
            agent="risk_agent",
            phase="trade_validation"
        )
        
        # Extract parameters with fallback to both locations
        entry_price = float(trade_setup.get('entry_price') or payload.get('entry_price', 0))
        stop_loss = float(trade_setup.get('stop_loss') or payload.get('stop_loss', 0))
        
        # Handle take_profit_levels
        tp_levels = trade_setup.get('take_profit_levels') or payload.get('take_profit_levels', [])
        take_profit_levels = [float(tp['price']) if isinstance(tp, dict) else float(tp) for tp in tp_levels]
        
        recommended_position_size = float(trade_setup.get('recommended_position_size') or payload.get('recommended_position_size', 0))
        risk_amount = float(trade_setup.get('risk_amount') or payload.get('risk_amount', 0))
        confidence_score = float(trade_setup.get('confidence_score') or payload.get('confidence_score', 0.75))
        market_regime = trade_setup.get('market_regime') or payload.get('market_regime')
        
        # Validate through risk engine
        result = await self.risk_engine.validate_trade(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            recommended_position_size=recommended_position_size,
            risk_amount=risk_amount,
            confidence_score=confidence_score,
            market_regime=market_regime
        )
        
        # Check if LLM consultation needed for edge cases
        should_consult_llm = self._should_consult_llm(result, payload)
        
        if should_consult_llm and self.llm_advisor.is_available():
            self.llm_consultations += 1
            
            plog.info(
                "🤖 Edge case detected - consulting LLM advisor",
                agent="risk_agent",
                phase="trade_validation"
            )
            
            await self.publish_activity(
                action="consulting_risk_llm",
                message="Consulting LLM for edge case risk analysis",
                phase="risk_assessment",
                severity="warning"
            )

            
            # Get portfolio state
            snapshot = await self.portfolio_tracker.get_current_snapshot()
            
            # Consult LLM
            llm_advice = await self.llm_advisor.analyze_edge_case(
                trade_setup=payload,
                portfolio_state=snapshot.to_dict(),
                edge_case_context=self._build_edge_case_context(result, payload)
            )
            
            if llm_advice:
                # Apply LLM recommendations
                if llm_advice.recommendation == 'REJECT':
                    result.approved = False
                    result.add_rejection(f"LLM recommendation: {llm_advice.reasoning}")
                elif llm_advice.recommendation == 'ADJUST':
                    result.add_warning(f"LLM suggests adjustments: {llm_advice.reasoning}")
                    # Apply suggested adjustments
                    if 'position_size_multiplier' in llm_advice.suggested_adjustments:
                        multiplier = llm_advice.suggested_adjustments['position_size_multiplier']
                        result.adjusted_position_size = recommended_position_size * multiplier
                        result.add_recommendation(
                            f"LLM recommends {multiplier:.0%} position size"
                        )
        
        # Update statistics
        if result.approved:
            self.trades_approved += 1
            plog.info(
                f"✅ Risk validation PASSED - Trade approved for execution",
                agent="risk_agent",
                phase="trade_validation"
            )
            
            await self.publish_activity(
                action="trade_approved",
                message=f"Trade approved: {symbol} {direction} (Risk Score: {result.risk_score:.2f})",
                phase="risk_assessment",
                severity="success",
                metadata={
                    "risk_score": result.risk_score,
                    "position_size": result.adjusted_position_size or recommended_position_size
                }
            )

        else:
            self.trades_rejected += 1
            plog.warning(
                f"❌ Risk validation FAILED - Trade rejected: {', '.join(result.rejection_reasons[:2])}",
                agent="risk_agent",
                phase="trade_validation"
            )
            
            await self.publish_activity(
                action="trade_rejected",
                message=f"Trade rejected: {result.rejection_reasons[0] if result.rejection_reasons else 'Risk check failed'}",
                phase="risk_assessment",
                severity="error",
                metadata={
                    "reasons": result.rejection_reasons
                }
            )

        
        # Sync portfolio state with StateManager
        await self.portfolio_tracker.sync_with_state_manager()
        
        # NOTE: Orchestrator will handle execution coordination
        # We just return the validation result
        
        return {
            'validated': True,
            'approved': result.approved,
            'result': result.to_dict(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def _handle_get_risk_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get current risk status"""
        snapshot = await self.portfolio_tracker.get_current_snapshot()
        stats = await self.risk_engine.get_validation_statistics()
        llm_stats = await self.llm_advisor.get_usage_stats()
        
        return {
            'portfolio': snapshot.to_dict(),
            'validation_stats': stats,
            'llm_stats': llm_stats,
            'agent_stats': {
                'trades_validated': self.trades_validated,
                'trades_approved': self.trades_approved,
                'trades_rejected': self.trades_rejected,
                'llm_consultations': self.llm_consultations,
                'approval_rate': round(
                    self.trades_approved / max(self.trades_validated, 1) * 100, 1
                ),
                'llm_usage_rate': round(
                    self.llm_consultations / max(self.trades_validated, 1) * 100, 1
                )
            },
            'timestamp': datetime.now().isoformat()
        }
    
    async def _handle_update_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update position with current price"""
        position_id = payload.get('position_id')
        current_price = float(payload.get('current_price', 0))
        
        await self.portfolio_tracker.update_position_price(position_id, current_price)
        
        return {'updated': True, 'position_id': position_id}
    
    async def _handle_close_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle position closure"""
        position_id = payload.get('position_id')
        exit_price = float(payload.get('exit_price', 0))
        reason = payload.get('reason', 'manual')
        
        result = await self.portfolio_tracker.close_position(
            position_id=position_id,
            exit_price=exit_price,
            reason=reason
        )
        
        # Sync with StateManager
        await self.portfolio_tracker.sync_with_state_manager()
        
        return result
    
    async def _handle_get_risk_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive risk report"""
        snapshot = await self.portfolio_tracker.get_current_snapshot()
        risk_summary = await self.portfolio_tracker.get_risk_summary()
        validation_stats = await self.risk_engine.get_validation_statistics()
        violations = await self.risk_engine.get_rule_violations(limit=20)
        
        return {
            'report_type': 'comprehensive_risk_report',
            'generated_at': datetime.now().isoformat(),
            'portfolio_snapshot': snapshot.to_dict(),
            'risk_summary': risk_summary,
            'validation_statistics': validation_stats,
            'recent_violations': violations,
            'risk_parameters': self.risk_engine.get_risk_parameters()
        }
    
    async def _handle_trigger_circuit_breaker(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Manually trigger circuit breaker"""
        reason = payload.get('reason', 'Manual trigger')
        
        await self.risk_engine.trigger_circuit_breaker(reason)
        
        return {
            'circuit_breaker_triggered': True,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _handle_reset_circuit_breaker(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Reset circuit breaker"""
        manual = payload.get('manual', True)
        
        success = await self.risk_engine.reset_circuit_breaker(manual=manual)
        
        return {
            'circuit_breaker_reset': success,
            'manual': manual,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _handle_get_portfolio_snapshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get current portfolio snapshot"""
        snapshot = await self.portfolio_tracker.get_current_snapshot()
        return snapshot.to_dict()
    
    def _should_consult_llm(
        self,
        result: Any,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Determine if LLM consultation is needed
        
        Consult LLM for:
        - High correlation risk with warnings
        - Recent losing streak (2+)
        - Low confidence + moderate risk
        - Multiple warnings
        """
        # Don't consult if already rejected
        if not result.approved:
            return False
        
        # Check for edge case indicators
        has_correlation_warning = any('correlation' in w.lower() for w in result.warnings)
        has_multiple_warnings = len(result.warnings) >= 2
        low_confidence = payload.get('confidence_score', 1.0) < 0.75
        moderate_risk = result.risk_score > 0.5
        
        should_consult = (
            has_correlation_warning or
            has_multiple_warnings or
            (low_confidence and moderate_risk)
        )
        
        return should_consult
    
    def _build_edge_case_context(
        self,
        result: Any,
        payload: Dict[str, Any]
    ) -> str:
        """Build context description for LLM"""
        context_parts = []
        
        if result.warnings:
            context_parts.append(f"Warnings: {', '.join(result.warnings)}")
        
        if result.risk_score > 0.5:
            context_parts.append(f"Moderate risk score: {result.risk_score:.2f}")
        
        if payload.get('confidence_score', 1.0) < 0.75:
            context_parts.append(
                f"Low confidence: {payload.get('confidence_score'):.2f}"
            )
        
        return " | ".join(context_parts) if context_parts else "Complex scenario requiring LLM analysis"
