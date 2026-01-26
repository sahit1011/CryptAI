"""
Integration tests for Risk Management Agent Pipeline
Tests the complete flow from trade validation through all risk components
"""
import pytest
import asyncio
from src.risk.portfolio_state_tracker import PortfolioStateTracker
from src.risk.risk_rules_engine import RiskRulesEngine, RiskParameters
from src.risk.correlation_analyzer import CorrelationAnalyzer
from src.risk.circuit_breaker import CircuitBreaker


@pytest.fixture
async def risk_pipeline():
    """Create complete risk management pipeline"""
    tracker = PortfolioStateTracker(initial_balance=10000.0)
    engine = RiskRulesEngine(
        portfolio_tracker=tracker,
        risk_params=RiskParameters(),
        enable_circuit_breaker=True
    )
    return engine, tracker


class TestRiskPipeline:
    """Integration tests for complete risk pipeline"""
    
    @pytest.mark.asyncio
    async def test_normal_trade_approval(self, risk_pipeline):
        """Test normal trade gets approved through pipeline"""
        engine, tracker = await risk_pipeline
        
        result = await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000, 45000],
            recommended_position_size=0.044,
            risk_amount=200,
            confidence_score=0.85,
            market_regime='TRENDING_BULLISH'
        )
        
        assert result.approved is True
        assert result.risk_score < 0.5
        assert len(result.rejection_reasons) == 0
    
    @pytest.mark.asyncio
    async def test_excessive_risk_rejection(self, risk_pipeline):
        """Test excessive risk gets rejected"""
        engine, tracker = await risk_pipeline
        
        result = await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=500,  # 5% - too high!
            confidence_score=0.85
        )
        
        assert result.approved is False
        assert any('risk' in reason.lower() for reason in result.rejection_reasons)
    
    @pytest.mark.asyncio
    async def test_correlation_detection(self, risk_pipeline):
        """Test correlation risk is detected"""
        engine, tracker = await risk_pipeline
        
        # Add BTC position
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=200
        )
        
        # Try to add correlated ETH position
        result = await engine.validate_trade(
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            stop_loss=2400,
            take_profit_levels=[2600],
            recommended_position_size=1.0,
            risk_amount=200,
            confidence_score=0.85
        )
        
        # Should still approve but with warnings
        assert result.approved is True
        assert len(result.warnings) > 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self, risk_pipeline):
        """Test circuit breaker activates and blocks trades"""
        engine, tracker = await risk_pipeline
        
        # Simulate losing streak
        tracker.loss_streak = 3
        
        # Check if circuit breaker triggers
        snapshot = await tracker.get_current_snapshot()
        should_trigger, conditions = engine.circuit_breaker.check_conditions(
            snapshot.to_dict()
        )
        
        assert should_trigger is True
        
        # Trigger circuit breaker
        await engine.trigger_circuit_breaker(\"3 consecutive losses\")
        
        # Try to validate trade (should be rejected)
        result = await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.044,
            risk_amount=200,
            confidence_score=0.85
        )
        
        assert result.approved is False
        assert any('circuit breaker' in reason.lower() for reason in result.rejection_reasons)
    
    @pytest.mark.asyncio
    async def test_portfolio_heat_limit(self, risk_pipeline):
        """Test portfolio heat limit enforcement"""
        engine, tracker = await risk_pipeline
        
        # Add positions to reach heat limit
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=1.0,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=300
        )
        
        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=5.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=300
        )
        
        # Current heat = 600/10000 = 6% (at limit)
        # Try to add more (should fail)
        result = await engine.validate_trade(
            symbol='BNBUSDT',
            direction='LONG',
            entry_price=310,
            stop_loss=305,
            take_profit_levels=[315],
            recommended_position_size=1.0,
            risk_amount=100,
            confidence_score=0.85
        )
        
        assert result.approved is False
        assert any('heat' in reason.lower() for reason in result.rejection_reasons)
    
    @pytest.mark.asyncio
    async def test_market_regime_adjustment(self, risk_pipeline):
        """Test market regime affects validation"""
        engine, tracker = await risk_pipeline
        
        # High volatility should trigger warnings
        result = await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.044,
            risk_amount=200,
            confidence_score=0.85,
            market_regime='HIGH_VOLATILITY'
        )
        
        # Should approve but recommend size reduction
        assert result.approved is True
        assert len(result.warnings) > 0 or len(result.recommendations) > 0
    
    @pytest.mark.asyncio
    async def test_validation_statistics_tracking(self, risk_pipeline):
        """Test validation statistics are tracked"""
        engine, tracker = await risk_pipeline
        
        # Validate several trades
        for i in range(5):
            await engine.validate_trade(
                symbol='BTCUSDT',
                direction='LONG',
                entry_price=43000,
                stop_loss=42500,
                take_profit_levels=[44000],
                recommended_position_size=0.044,
                risk_amount=200,
                confidence_score=0.85
            )
        
        # Get statistics
        stats = await engine.get_validation_statistics()
        
        assert stats['validations']['total'] == 5
        assert stats['validations']['approvals'] > 0
        assert 'performance' in stats
    
    @pytest.mark.asyncio
    async def test_rule_violations_tracking(self, risk_pipeline):
        """Test rule violations are tracked"""
        engine, tracker = await risk_pipeline
        
        # Submit trade that will be rejected
        await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.5,
            risk_amount=500,  # Excessive risk
            confidence_score=0.85
        )
        
        # Get violations
        violations = await engine.get_rule_violations(severity='ERROR')
        
        assert len(violations) > 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_reset(self, risk_pipeline):
        """Test circuit breaker can be reset"""
        engine, tracker = await risk_pipeline
        
        # Trigger circuit breaker
        await engine.trigger_circuit_breaker(\"Test trigger\")
        assert engine.circuit_breaker.is_active() is True
        
        # Reset it
        success = await engine.reset_circuit_breaker(manual=True)
        
        assert success is True
        assert engine.circuit_breaker.is_active() is False
    
    @pytest.mark.asyncio
    async def test_complete_trade_lifecycle(self, risk_pipeline):
        """Test complete trade lifecycle through risk system"""
        engine, tracker = await risk_pipeline
        
        # 1. Validate trade
        result = await engine.validate_trade(
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            stop_loss=42500,
            take_profit_levels=[44000],
            recommended_position_size=0.044,
            risk_amount=200,
            confidence_score=0.85
        )
        
        assert result.approved is True
        
        # 2. Add position to tracker
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.044,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=200
        )
        
        # 3. Update position price
        await tracker.update_position_price('pos_001', 43500)
        
        # 4. Check portfolio state
        snapshot = await tracker.get_current_snapshot()
        assert len(snapshot.open_positions) == 1
        assert snapshot.total_unrealized_pnl > 0
        
        # 5. Close position
        close_result = await tracker.close_position('pos_001', exit_price=44000)
        
        assert close_result['pnl'] > 0
        assert tracker.daily_wins == 1
        assert tracker.win_streak == 1


class TestMultiPositionScenarios:
    """Test scenarios with multiple positions"""
    
    @pytest.mark.asyncio
    async def test_multiple_uncorrelated_positions(self, risk_pipeline):
        """Test adding multiple uncorrelated positions"""
        engine, tracker = await risk_pipeline
        
        # Add positions in different assets
        symbols = ['BTCUSDT', 'ADAUSDT', 'DOTUSDT']
        
        for i, symbol in enumerate(symbols):
            result = await engine.validate_trade(
                symbol=symbol,
                direction='LONG',
                entry_price=100,
                stop_loss=95,
                take_profit_levels=[105],
                recommended_position_size=1.0,
                risk_amount=150,
                confidence_score=0.85
            )
            
            if i < 3:  # Within position limit
                assert result.approved is True
            
            if result.approved:
                await tracker.add_position(
                    position_id=f'pos_{i:03d}',
                    symbol=symbol,
                    direction='LONG',
                    entry_price=100,
                    position_size=1.0,
                    stop_loss=95,
                    take_profit_levels=[105],
                    risk_amount=150
                )
        
        # Check final state
        snapshot = await tracker.get_current_snapshot()
        assert len(snapshot.open_positions) <= 3  # Position limit
    
    @pytest.mark.asyncio
    async def test_correlated_positions_size_adjustment(self, risk_pipeline):
        """Test size adjustment for correlated positions"""
        engine, tracker = await risk_pipeline
        
        # Add BTC position
        await tracker.add_position(
            position_id='pos_001',
            symbol='BTCUSDT',
            direction='LONG',
            entry_price=43000,
            position_size=0.5,
            stop_loss=42500,
            take_profit_levels=[44000],
            risk_amount=250
        )
        
        # Add ETH position (correlated)
        await tracker.add_position(
            position_id='pos_002',
            symbol='ETHUSDT',
            direction='LONG',
            entry_price=2500,
            position_size=5.0,
            stop_loss=2400,
            take_profit_levels=[2600],
            risk_amount=250
        )
        
        # Try to add BNB (also correlated)
        result = await engine.validate_trade(
            symbol='BNBUSDT',
            direction='LONG',
            entry_price=310,
            stop_loss=305,
            take_profit_levels=[315],
            recommended_position_size=1.0,
            risk_amount=150,
            confidence_score=0.85
        )
        
        # Should have correlation warnings
        assert len(result.warnings) > 0
        # May have size adjustment recommendation
        if result.adjusted_position_size:
            assert result.adjusted_position_size < 1.0
