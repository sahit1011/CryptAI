"""
Unit tests for Circuit Breaker System
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerCondition


class TestCircuitBreaker:
    """Test CircuitBreaker class"""
    
    @pytest.fixture
    def breaker(self):
        """Create circuit breaker with default settings"""
        return CircuitBreaker(cooldown_minutes=60, auto_reset=False)
    
    @pytest.fixture
    def auto_breaker(self):
        """Create circuit breaker with auto-reset enabled"""
        return CircuitBreaker(cooldown_minutes=1, auto_reset=True)
    
    def test_breaker_initialization(self, breaker):
        """Test circuit breaker initialization"""
        assert breaker.active is False
        assert breaker.cooldown_minutes == 60
        assert breaker.auto_reset is False
        assert len(breaker.trigger_history) == 0
    
    def test_check_conditions_no_triggers(self, breaker):
        """Test checking conditions when all are normal"""
        portfolio_snapshot = {
            'loss_streak': 0,
            'daily_pnl': 100,
            'daily_start_equity': 10000,
            'current_drawdown': 0.05,
            'portfolio_heat': 0.04
        }
        
        should_trigger, conditions = breaker.check_conditions(portfolio_snapshot)
        
        assert should_trigger is False
        assert len(conditions) == 0
    
    def test_check_conditions_consecutive_losses(self, breaker):
        """Test trigger on 3+ consecutive losses"""
        portfolio_snapshot = {
            'loss_streak': 3,
            'daily_pnl': -200,
            'daily_start_equity': 10000,
            'current_drawdown': 0.05,
            'portfolio_heat': 0.04
        }
        
        should_trigger, conditions = breaker.check_conditions(portfolio_snapshot)
        
        assert should_trigger is True
        assert any('consecutive losses' in c for c in conditions)
    
    def test_check_conditions_daily_loss(self, breaker):
        """Test trigger on daily loss limit"""
        portfolio_snapshot = {
            'loss_streak': 0,
            'daily_pnl': -500,  # 5% loss
            'daily_start_equity': 10000,
            'current_drawdown': 0.05,
            'portfolio_heat': 0.04
        }
        
        should_trigger, conditions = breaker.check_conditions(portfolio_snapshot)
        
        assert should_trigger is True
        assert any('Daily loss' in c for c in conditions)
    
    def test_check_conditions_max_drawdown(self, breaker):
        """Test trigger on max drawdown"""
        portfolio_snapshot = {
            'loss_streak': 0,
            'daily_pnl': 0,
            'daily_start_equity': 10000,
            'current_drawdown': 0.20,  # 20% drawdown
            'portfolio_heat': 0.04
        }
        
        should_trigger, conditions = breaker.check_conditions(portfolio_snapshot)
        
        assert should_trigger is True
        assert any('drawdown' in c for c in conditions)
    
    def test_check_conditions_extreme_heat(self, breaker):
        """Test trigger on extreme portfolio heat"""
        portfolio_snapshot = {
            'loss_streak': 0,
            'daily_pnl': 0,
            'daily_start_equity': 10000,
            'current_drawdown': 0.05,
            'portfolio_heat': 0.08  # 8% heat
        }
        
        should_trigger, conditions = breaker.check_conditions(portfolio_snapshot)
        
        assert should_trigger is True
        assert any('heat' in c for c in conditions)
    
    def test_trigger_manual(self, breaker):
        """Test manual trigger"""
        breaker.trigger(reason="Testing manual trigger", manual=True)
        
        assert breaker.active is True
        assert breaker.reason == "Testing manual trigger"
        assert breaker.triggered_at is not None
        assert len(breaker.trigger_history) == 1
        assert breaker.trigger_history[0]['manual'] is True
    
    def test_trigger_automatic(self, breaker):
        """Test automatic trigger"""
        breaker.trigger(reason="Automatic trigger", manual=False)
        
        assert breaker.active is True
        assert len(breaker.trigger_history) == 1
        assert breaker.trigger_history[0]['manual'] is False
    
    def test_trigger_when_already_active(self, breaker):
        """Test triggering when already active (should not duplicate)"""
        breaker.trigger(reason="First trigger", manual=False)
        initial_count = len(breaker.trigger_history)
        
        breaker.trigger(reason="Second trigger", manual=False)
        
        # Should not add another trigger
        assert len(breaker.trigger_history) == initial_count
    
    def test_reset_manual(self, breaker):
        """Test manual reset"""
        breaker.trigger(reason="Test", manual=False)
        assert breaker.active is True
        
        success = breaker.reset(manual=True)
        
        assert success is True
        assert breaker.active is False
        assert breaker.reason == ""
        assert len(breaker.reset_history) == 1
    
    def test_reset_before_cooldown(self, breaker):
        """Test reset before cooldown period (should fail)"""
        breaker.trigger(reason="Test", manual=False)
        
        # Try to reset immediately (cooldown not elapsed)
        success = breaker.reset(manual=False)
        
        assert success is False
        assert breaker.active is True  # Still active
    
    def test_reset_after_cooldown(self):
        """Test reset after cooldown period"""
        # Create breaker with 0 minute cooldown for testing
        breaker = CircuitBreaker(cooldown_minutes=0, auto_reset=False)
        breaker.trigger(reason="Test", manual=False)
        
        # Reset should succeed immediately
        success = breaker.reset(manual=False)
        
        assert success is True
        assert breaker.active is False
    
    def test_reset_when_not_active(self, breaker):
        """Test reset when not active (should fail)"""
        success = breaker.reset(manual=True)
        
        assert success is False
    
    def test_auto_reset_enabled(self, auto_breaker):
        """Test auto-reset functionality"""
        auto_breaker.trigger(reason="Test", manual=False)
        assert auto_breaker.active is True

        # Rewind the trigger timestamp past the cooldown instead of sleeping for
        # it. reset() compares `datetime.now() - triggered_at` against
        # `cooldown_minutes`, so this exercises the exact same branch — but takes
        # microseconds instead of 61 seconds (which alone was 95% of the suite's
        # entire runtime).
        auto_breaker.triggered_at -= timedelta(
            minutes=auto_breaker.cooldown_minutes, seconds=1
        )

        # Check auto-reset
        reset_performed = auto_breaker.check_auto_reset()

        assert reset_performed is True
        assert auto_breaker.active is False
    
    def test_is_active_with_auto_reset(self, auto_breaker):
        """Test is_active checks auto-reset"""
        auto_breaker.trigger(reason="Test", manual=False)
        
        # Immediately after trigger
        assert auto_breaker.is_active() is True
        
        # After cooldown (would need to simulate time passing)
        # This is tested in test_auto_reset_enabled
    
    def test_get_status_inactive(self, breaker):
        """Test getting status when inactive"""
        status = breaker.get_status()
        
        assert status['active'] is False
        assert status['reason'] == ""
        assert status['triggered_at'] is None
        assert status['total_triggers'] == 0
    
    def test_get_status_active(self, breaker):
        """Test getting status when active"""
        breaker.trigger(reason="Test trigger", manual=False)
        
        status = breaker.get_status()
        
        assert status['active'] is True
        assert status['reason'] == "Test trigger"
        assert status['triggered_at'] is not None
        assert 'elapsed_minutes' in status
        assert 'remaining_cooldown_minutes' in status
    
    def test_get_history(self, breaker):
        """Test getting trigger/reset history"""
        # Trigger and reset a few times
        breaker.trigger(reason="Trigger 1", manual=False)
        breaker.reset(manual=True)
        breaker.trigger(reason="Trigger 2", manual=False)
        breaker.reset(manual=True)
        
        history = breaker.get_history(limit=10)
        
        assert history['total_triggers'] == 2
        assert history['total_resets'] == 2
        assert len(history['triggers']) == 2
        assert len(history['resets']) == 2
    
    def test_get_history_with_limit(self, breaker):
        """Test history with limit"""
        # Trigger multiple times
        for i in range(5):
            breaker.trigger(reason=f"Trigger {i}", manual=False)
            breaker.reset(manual=True)
        
        history = breaker.get_history(limit=2)
        
        # Should only return last 2
        assert len(history['triggers']) == 2
        assert len(history['resets']) == 2
        assert history['total_triggers'] == 5
    
    def test_get_triggered_conditions(self, breaker):
        """Test getting triggered conditions"""
        portfolio_snapshot = {
            'loss_streak': 3,
            'daily_pnl': -500,
            'daily_start_equity': 10000,
            'current_drawdown': 0.05,
            'portfolio_heat': 0.04
        }
        
        breaker.check_conditions(portfolio_snapshot)
        conditions = breaker.get_triggered_conditions()
        
        assert len(conditions) > 0
        assert all(cond.triggered for cond in conditions)
    
    def test_clear_history(self, breaker):
        """Test clearing history"""
        breaker.trigger(reason="Test", manual=False)
        breaker.reset(manual=True)
        
        assert len(breaker.trigger_history) > 0
        assert len(breaker.reset_history) > 0
        
        breaker.clear_history()
        
        assert len(breaker.trigger_history) == 0
        assert len(breaker.reset_history) == 0


class TestCircuitBreakerCondition:
    """Test CircuitBreakerCondition dataclass"""
    
    def test_condition_creation(self):
        """Test creating a condition"""
        condition = CircuitBreakerCondition(
            name="test_condition",
            description="Test condition",
            threshold=0.05,
            current_value=0.06,
            triggered=True
        )
        
        assert condition.name == "test_condition"
        assert condition.triggered is True
        assert condition.current_value > condition.threshold
    
    def test_condition_to_dict(self):
        """Test condition serialization"""
        condition = CircuitBreakerCondition(
            name="daily_loss",
            description="Daily loss limit",
            threshold=0.05,
            current_value=0.06,
            triggered=True,
            triggered_at=datetime.now()
        )
        
        # Should be able to convert to dict via __dict__
        cond_dict = condition.__dict__
        
        assert cond_dict['name'] == "daily_loss"
        assert cond_dict['triggered'] is True
