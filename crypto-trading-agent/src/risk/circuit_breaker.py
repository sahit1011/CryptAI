"""
Circuit Breaker System
Emergency stop system that halts trading when risk thresholds are breached
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from src.utils.pipeline_logger import PipelineLogger

plog = PipelineLogger()


@dataclass
class CircuitBreakerCondition:
    """Circuit breaker trigger condition"""
    name: str
    description: str
    threshold: Any
    current_value: Any
    triggered: bool = False
    triggered_at: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker system for emergency trading halt
    
    Trigger Conditions:
    - 3 consecutive losses
    - Daily loss limit hit (5%)
    - Max drawdown exceeded (20%)
    - Extreme market volatility
    - Manual trigger
    
    Features:
    - Auto-reset after cooldown period
    - Manual override capability
    - Alert system integration
    - Detailed logging
    """
    
    def __init__(
        self,
        cooldown_minutes: int = 60,
        auto_reset: bool = False
    ):
        self.active = False
        self.reason = ""
        self.triggered_at: Optional[datetime] = None
        self.cooldown_minutes = cooldown_minutes
        self.auto_reset = auto_reset
        
        # Trigger history
        self.trigger_history: List[Dict[str, Any]] = []
        self.reset_history: List[Dict[str, Any]] = []
        
        # Conditions
        self.conditions: Dict[str, CircuitBreakerCondition] = {}
        
        plog.info(
            f"Circuit breaker initialized | cooldown={cooldown_minutes}min | auto_reset={auto_reset}",
            agent="risk_agent",
            phase="initialization"
        )
    
    def check_conditions(
        self,
        portfolio_snapshot: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Check all circuit breaker conditions
        
        Returns:
            (should_trigger, list_of_triggered_conditions)
        """
        triggered_conditions = []
        
        # Condition 1: Consecutive losses
        loss_streak = portfolio_snapshot.get('loss_streak', 0)
        if loss_streak >= 3:
            triggered_conditions.append(
                f"3+ consecutive losses (current: {loss_streak})"
            )
            self.conditions['consecutive_losses'] = CircuitBreakerCondition(
                name="consecutive_losses",
                description="3+ consecutive losses",
                threshold=3,
                current_value=loss_streak,
                triggered=True
            )
        
        # Condition 2: Daily loss limit
        daily_pnl = portfolio_snapshot.get('daily_pnl', 0)
        daily_start_equity = portfolio_snapshot.get('daily_start_equity', 10000)
        daily_loss_pct = abs(min(0, daily_pnl)) / daily_start_equity if daily_start_equity > 0 else 0
        
        if daily_loss_pct >= 0.05:  # 5% daily loss
            triggered_conditions.append(
                f"Daily loss limit hit: {daily_loss_pct*100:.1f}% (limit: 5%)"
            )
            self.conditions['daily_loss'] = CircuitBreakerCondition(
                name="daily_loss",
                description="Daily loss limit",
                threshold=0.05,
                current_value=daily_loss_pct,
                triggered=True
            )
        
        # Condition 3: Max drawdown
        current_drawdown = portfolio_snapshot.get('current_drawdown', 0)
        if current_drawdown >= 0.20:  # 20% drawdown
            triggered_conditions.append(
                f"Max drawdown exceeded: {current_drawdown*100:.1f}% (limit: 20%)"
            )
            self.conditions['max_drawdown'] = CircuitBreakerCondition(
                name="max_drawdown",
                description="Maximum drawdown",
                threshold=0.20,
                current_value=current_drawdown,
                triggered=True
            )
        
        # Condition 4: Extreme portfolio heat
        portfolio_heat = portfolio_snapshot.get('portfolio_heat', 0)
        if portfolio_heat >= 0.08:  # 8% (above normal 6% limit)
            triggered_conditions.append(
                f"Extreme portfolio heat: {portfolio_heat*100:.1f}% (limit: 8%)"
            )
            self.conditions['extreme_heat'] = CircuitBreakerCondition(
                name="extreme_heat",
                description="Extreme portfolio heat",
                threshold=0.08,
                current_value=portfolio_heat,
                triggered=True
            )
        
        should_trigger = len(triggered_conditions) > 0
        
        if should_trigger:
            plog.warning(
                f"Circuit breaker conditions met: {', '.join(triggered_conditions)}",
                agent="risk_agent",
                phase="circuit_breaker"
            )
        
        return should_trigger, triggered_conditions
    
    def trigger(self, reason: str, manual: bool = False):
        """
        Trigger the circuit breaker
        
        Args:
            reason: Reason for triggering
            manual: Whether this is a manual trigger
        """
        if self.active:
            plog.warning(
                "Circuit breaker already active",
                agent="risk_agent",
                phase="circuit_breaker"
            )
            return
        
        self.active = True
        self.reason = reason
        self.triggered_at = datetime.now()
        
        # Record in history
        self.trigger_history.append({
            'timestamp': self.triggered_at.isoformat(),
            'reason': reason,
            'manual': manual,
            'conditions': {
                name: cond.__dict__
                for name, cond in self.conditions.items()
                if cond.triggered
            }
        })
        
        trigger_type = "MANUAL" if manual else "AUTOMATIC"
        
        plog.error(
            f"🚨 CIRCUIT BREAKER ACTIVATED ({trigger_type}): {reason}",
            agent="risk_agent",
            phase="circuit_breaker"
        )
        
        # TODO: Send alert to user (Telegram, email, etc.)
    
    def reset(self, manual: bool = False) -> bool:
        """
        Reset the circuit breaker
        
        Args:
            manual: Whether this is a manual reset
            
        Returns:
            True if reset successful, False otherwise
        """
        if not self.active:
            plog.warning(
                "Circuit breaker not active, cannot reset",
                agent="risk_agent",
                phase="circuit_breaker"
            )
            return False
        
        # Check cooldown period
        if not manual and self.triggered_at:
            elapsed = datetime.now() - self.triggered_at
            if elapsed < timedelta(minutes=self.cooldown_minutes):
                remaining = self.cooldown_minutes - (elapsed.total_seconds() / 60)
                plog.warning(
                    f"Cooldown period not elapsed. {remaining:.1f} minutes remaining.",
                    agent="risk_agent",
                    phase="circuit_breaker"
                )
                return False
        
        # Record reset
        self.reset_history.append({
            'timestamp': datetime.now().isoformat(),
            'manual': manual,
            'duration_minutes': (
                (datetime.now() - self.triggered_at).total_seconds() / 60
                if self.triggered_at
                else 0
            ),
            'previous_reason': self.reason
        })
        
        # Reset state
        self.active = False
        reset_type = "MANUAL" if manual else "AUTOMATIC"
        previous_reason = self.reason
        self.reason = ""
        self.triggered_at = None
        self.conditions.clear()
        
        plog.info(
            f"✅ Circuit breaker RESET ({reset_type}) | Previous reason: {previous_reason}",
            agent="risk_agent",
            phase="circuit_breaker"
        )
        
        return True
    
    def check_auto_reset(self) -> bool:
        """
        Check if auto-reset conditions are met
        
        Returns:
            True if auto-reset performed, False otherwise
        """
        if not self.active or not self.auto_reset:
            return False
        
        if not self.triggered_at:
            return False
        
        elapsed = datetime.now() - self.triggered_at
        if elapsed >= timedelta(minutes=self.cooldown_minutes):
            plog.info(
                f"Auto-reset conditions met (cooldown: {self.cooldown_minutes}min elapsed)",
                agent="risk_agent",
                phase="circuit_breaker"
            )
            return self.reset(manual=False)
        
        return False
    
    def is_active(self) -> bool:
        """Check if circuit breaker is active"""
        # Check auto-reset first
        if self.active and self.auto_reset:
            self.check_auto_reset()
        
        return self.active
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        status = {
            'active': self.active,
            'reason': self.reason,
            'triggered_at': self.triggered_at.isoformat() if self.triggered_at else None,
            'cooldown_minutes': self.cooldown_minutes,
            'auto_reset': self.auto_reset,
            'total_triggers': len(self.trigger_history),
            'total_resets': len(self.reset_history)
        }
        
        if self.active and self.triggered_at:
            elapsed = datetime.now() - self.triggered_at
            status['elapsed_minutes'] = round(elapsed.total_seconds() / 60, 1)
            status['remaining_cooldown_minutes'] = max(
                0,
                self.cooldown_minutes - (elapsed.total_seconds() / 60)
            )
        
        return status
    
    def get_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get circuit breaker history"""
        return {
            'triggers': self.trigger_history[-limit:],
            'resets': self.reset_history[-limit:],
            'total_triggers': len(self.trigger_history),
            'total_resets': len(self.reset_history)
        }
    
    def get_triggered_conditions(self) -> List[CircuitBreakerCondition]:
        """Get list of currently triggered conditions"""
        return [
            cond for cond in self.conditions.values()
            if cond.triggered
        ]
    
    def clear_history(self):
        """Clear trigger and reset history"""
        self.trigger_history.clear()
        self.reset_history.clear()
        
        plog.info(
            "Circuit breaker history cleared",
            agent="risk_agent",
            phase="circuit_breaker"
        )
