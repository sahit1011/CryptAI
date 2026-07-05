"""
Risk Rules Engine
Centralized orchestration of all risk checks and validation logic
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from src.risk.portfolio_state_tracker import PortfolioStateTracker
from src.risk.deterministic_risk_calculator import (
    DeterministicRiskCalculator,
    RiskParameters,
    RiskValidationResult
)
from src.risk.correlation_analyzer import CorrelationAnalyzer
from src.risk.circuit_breaker import CircuitBreaker
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


@dataclass
class RuleViolation:
    """Record of a rule violation"""
    rule_name: str
    severity: str  # 'ERROR', 'WARNING', 'INFO'
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_name': self.rule_name,
            'severity': self.severity,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


class RiskRulesEngine:
    """
    Centralized risk rules engine
    
    Responsibilities:
    - Load and manage risk parameters
    - Execute all deterministic checks in sequence
    - Aggregate results from multiple validators
    - Provide detailed rejection/approval reasoning
    - Track rule violations and statistics
    - Coordinate with circuit breaker
    """
    
    def __init__(
        self,
        portfolio_tracker: PortfolioStateTracker,
        risk_params: Optional[RiskParameters] = None,
        enable_circuit_breaker: bool = True
    ):
        self.portfolio_tracker = portfolio_tracker
        self.risk_params = risk_params or RiskParameters()
        
        # Initialize components
        self.risk_calculator = DeterministicRiskCalculator(
            portfolio_tracker=portfolio_tracker,
            risk_params=self.risk_params
        )
        
        self.correlation_analyzer = CorrelationAnalyzer(
            max_correlated_exposure=self.risk_params.max_correlated_exposure
        )
        
        self.circuit_breaker = CircuitBreaker(
            cooldown_minutes=60,
            auto_reset=False
        ) if enable_circuit_breaker else None
        
        # Statistics
        self.total_validations = 0
        self.total_approvals = 0
        self.total_rejections = 0
        self.rule_violations: List[RuleViolation] = []
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        plog.info(
            "Risk rules engine initialized",
            agent="risk_agent",
            phase="initialization"
        )
    
    async def validate_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: List[float],
        recommended_position_size: float,
        risk_amount: float,
        confidence_score: float,
        market_regime: Optional[str] = None
    ) -> RiskValidationResult:
        """
        Comprehensive trade validation through all risk checks
        
        Returns:
            RiskValidationResult with approval/rejection decision
        """
        async with self._lock:
            self.total_validations += 1
            
            plog.info(
                f"🔍 Validating trade: {direction} {symbol} @ ${entry_price:.2f}",
                agent="risk_agent",
                phase="risk_validation"
            )
            
            # Step 1: Check circuit breaker
            if self.circuit_breaker and self.circuit_breaker.is_active():
                plog.error(
                    "🚨 Circuit breaker is ACTIVE - rejecting all trades",
                    agent="risk_agent",
                    phase="risk_validation"
                )
                
                result = RiskValidationResult(approved=False)
                result.add_rejection(
                    f"Circuit breaker active: {self.circuit_breaker.reason}"
                )
                self.total_rejections += 1
                return result
            
            # Step 2: Run deterministic risk validation
            result = await self.risk_calculator.validate_trade_setup(
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
            
            # Step 3: Additional correlation analysis (if not already done)
            if result.approved:
                snapshot = await self.portfolio_tracker.get_current_snapshot()
                positions = [pos.to_dict() for pos in snapshot.open_positions]
                
                correlation_result = self.correlation_analyzer.analyze_correlation(
                    new_symbol=symbol,
                    new_direction=direction,
                    existing_positions=positions,
                    total_equity=snapshot.total_equity
                )
                
                if correlation_result.has_correlation:
                    if correlation_result.correlation_strength > 0.75:
                        result.add_warning(
                            f"High correlation risk: {correlation_result.correlation_strength:.0%}"
                        )
                        result.add_recommendation(
                            f"Reduce size to {correlation_result.recommended_size_multiplier:.0%}"
                        )
                    
                    plog.debug(
                        f"Correlation analysis: {len(correlation_result.correlated_symbols)} "
                        f"correlated positions, strength={correlation_result.correlation_strength:.2f}",
                        agent="risk_agent",
                        phase="risk_validation"
                    )
            
            # Step 4: Check if circuit breaker should be triggered
            if self.circuit_breaker:
                snapshot = await self.portfolio_tracker.get_current_snapshot()
                # Use to_risk_dict() (raw fractions + daily_start_equity), NOT to_dict()
                # which returns heat/drawdown as display percentages and would trip the
                # breaker on ~0.08% heat.
                should_trigger, conditions = self.circuit_breaker.check_conditions(
                    snapshot.to_risk_dict()
                )
                
                if should_trigger:
                    self.circuit_breaker.trigger(
                        reason=f"Conditions met: {', '.join(conditions)}",
                        manual=False
                    )
                    
                    # Reject current trade
                    result.approved = False
                    result.add_rejection(
                        f"Circuit breaker triggered: {', '.join(conditions)}"
                    )
            
            # Step 5: Record violations
            if not result.approved:
                for reason in result.rejection_reasons:
                    self.rule_violations.append(
                        RuleViolation(
                            rule_name="trade_validation",
                            severity="ERROR",
                            message=reason
                        )
                    )
                self.total_rejections += 1
            else:
                self.total_approvals += 1
            
            # Step 6: Log warnings as violations
            for warning in result.warnings:
                self.rule_violations.append(
                    RuleViolation(
                        rule_name="trade_validation",
                        severity="WARNING",
                        message=warning
                    )
                )
            
            # Keep only last 100 violations
            if len(self.rule_violations) > 100:
                self.rule_violations = self.rule_violations[-100:]
            
            return result
    
    async def get_rule_violations(
        self,
        severity: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get recent rule violations
        
        Args:
            severity: Filter by severity ('ERROR', 'WARNING', 'INFO')
            limit: Maximum number of violations to return
            
        Returns:
            List of violation dictionaries
        """
        violations = self.rule_violations
        
        if severity:
            violations = [v for v in violations if v.severity == severity]
        
        return [v.to_dict() for v in violations[-limit:]]
    
    async def get_validation_statistics(self) -> Dict[str, Any]:
        """Get comprehensive validation statistics"""
        approval_rate = (
            self.total_approvals / self.total_validations
            if self.total_validations > 0
            else 0
        )
        
        # Get calculator performance
        calc_perf = await self.risk_calculator.get_performance_metrics()
        
        # Get circuit breaker status
        cb_status = (
            self.circuit_breaker.get_status()
            if self.circuit_breaker
            else {'active': False}
        )
        
        # Get portfolio summary
        risk_summary = await self.portfolio_tracker.get_risk_summary()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'validations': {
                'total': self.total_validations,
                'approvals': self.total_approvals,
                'rejections': self.total_rejections,
                'approval_rate': round(approval_rate * 100, 1)
            },
            'performance': calc_perf,
            'circuit_breaker': cb_status,
            'portfolio': risk_summary,
            'recent_violations': {
                'errors': len([v for v in self.rule_violations if v.severity == 'ERROR']),
                'warnings': len([v for v in self.rule_violations if v.severity == 'WARNING']),
                'total': len(self.rule_violations)
            }
        }
    
    async def update_risk_parameters(self, new_params: RiskParameters):
        """Update risk parameters"""
        async with self._lock:
            self.risk_params = new_params
            
            # Update calculator
            self.risk_calculator.risk_params = new_params
            
            # Update correlation analyzer
            self.correlation_analyzer.max_correlated_exposure = new_params.max_correlated_exposure
            
            plog.info(
                "Risk parameters updated",
                agent="risk_agent",
                phase="configuration"
            )
    
    async def reset_statistics(self):
        """Reset validation statistics"""
        async with self._lock:
            self.total_validations = 0
            self.total_approvals = 0
            self.total_rejections = 0
            self.rule_violations.clear()
            
            plog.info(
                "Validation statistics reset",
                agent="risk_agent",
                phase="maintenance"
            )
    
    async def trigger_circuit_breaker(self, reason: str):
        """Manually trigger circuit breaker"""
        if self.circuit_breaker:
            self.circuit_breaker.trigger(reason=reason, manual=True)
            
            # Also activate in portfolio tracker
            await self.portfolio_tracker.activate_circuit_breaker(reason)
            
            plog.error(
                f"🚨 Circuit breaker MANUALLY triggered: {reason}",
                agent="risk_agent",
                phase="circuit_breaker"
            )
    
    async def reset_circuit_breaker(self, manual: bool = True) -> bool:
        """Reset circuit breaker"""
        if not self.circuit_breaker:
            return False
        
        success = self.circuit_breaker.reset(manual=manual)
        
        if success:
            # Also deactivate in portfolio tracker
            await self.portfolio_tracker.deactivate_circuit_breaker(manual=manual)
            
            plog.info(
                "✅ Circuit breaker reset",
                agent="risk_agent",
                phase="circuit_breaker"
            )
        
        return success
    
    def get_risk_parameters(self) -> Dict[str, Any]:
        """Get current risk parameters"""
        return {
            'max_risk_per_trade': f"{self.risk_params.max_risk_per_trade*100}%",
            'min_risk_reward_ratio': self.risk_params.min_risk_reward_ratio,
            'max_portfolio_heat': f"{self.risk_params.max_portfolio_heat*100}%",
            'max_concurrent_positions': self.risk_params.max_concurrent_positions,
            'max_daily_loss': f"{self.risk_params.max_daily_loss*100}%",
            'max_weekly_loss': f"{self.risk_params.max_weekly_loss*100}%",
            'max_total_drawdown': f"{self.risk_params.max_total_drawdown*100}%",
            'max_correlated_exposure': f"{self.risk_params.max_correlated_exposure*100}%",
            'min_position_size_usd': f"${self.risk_params.min_position_size_usd}",
            'max_position_size_usd': f"${self.risk_params.max_position_size_usd}"
        }
