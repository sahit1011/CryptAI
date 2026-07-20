"""
Unit tests for Performance Analytics and Market Regime Detector
"""
import pytest
from datetime import datetime, timedelta
from src.memory.performance_analytics import PerformanceAnalyticsEngine as PerformanceAnalytics
from src.memory.market_regime_detector import MarketRegimeDetector, MarketRegime

def test_performance_analytics():
    """Test performance metrics calculation"""
    analytics = PerformanceAnalytics(initial_capital=1000.0)
    
    # Create sample trades
    trades = [
        {
            'exit_time': datetime.now() - timedelta(days=2),
            'is_winner': True,
            'pnl': 100.0,
            'risk_reward_ratio': 2.0,
            'duration_minutes': 60
        },
        {
            'exit_time': datetime.now() - timedelta(days=1),
            'is_winner': False,
            'pnl': -50.0,
            'risk_reward_ratio': 2.0,
            'duration_minutes': 30
        },
        {
            'exit_time': datetime.now(),
            'is_winner': True,
            'pnl': 150.0,
            'risk_reward_ratio': 3.0,
            'duration_minutes': 120
        }
    ]
    
    metrics = analytics.calculate_metrics(trades, current_balance=1200.0)
    
    assert metrics.total_trades == 3
    assert metrics.win_rate == pytest.approx(2/3)
    assert metrics.total_pnl == 200.0
    assert metrics.max_drawdown > 0
    assert metrics.profit_factor == pytest.approx(5.0)
    assert metrics.average_trade_duration == 70.0

def test_market_regime_detector():
    """Test market regime detection"""
    detector = MarketRegimeDetector()
    
    # Test Trending Bullish
    regime = detector.detect_regime(
        adx=30.0,
        atr=10.0,
        trend_direction='up',
        volume_ratio=1.5
    )
    assert regime.regime == MarketRegime.TRENDING_BULLISH
    assert regime.confidence > 0.5
    
    # Test Ranging
    regime = detector.detect_regime(
        adx=15.0,
        atr=10.0,
        trend_direction='sideways'
    )
    assert regime.regime == MarketRegime.RANGING
    
    # Test Volatile (needs history)
    detector = MarketRegimeDetector() # Reset to ensure clean history
    # Fill history with low ATR
    for _ in range(20):
        detector.detect_regime(20, 5.0, 'sideways')
        
    # Spike ATR
    regime = detector.detect_regime(
        adx=20.0,
        atr=20.0,  # High relative to history
        trend_direction='sideways'
    )
    assert regime.regime == MarketRegime.VOLATILE

def test_strategy_recommendations():
    """Test strategy recommendations"""
    detector = MarketRegimeDetector()
    
    recs = detector.get_strategy_recommendations(MarketRegime.TRENDING_BULLISH)
    assert 'pullback_entry' in recs['preferred_strategies']
    assert 'mean_reversion' in recs['avoid_strategies']
    
    recs = detector.get_strategy_recommendations(MarketRegime.VOLATILE)
    assert recs['position_sizing'] == 'reduced'
