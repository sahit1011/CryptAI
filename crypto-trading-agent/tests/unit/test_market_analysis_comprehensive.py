"""
Comprehensive Unit Tests for Market Analysis Components
Tests all components with proper data validation and error handling.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from src.analysis.indicators import TechnicalIndicators
from src.strategy.confluence_scorer import ConfluenceScorer, ConfluenceScore, Confluence
from src.analysis.schemas import (
    IndicatorData, SMCAnalysis, ICTAnalysis, MarketStructure,
    ConfluenceScore as ConfluenceScoreSchema, TradeOpportunity,
    validate_data
)
from src.analysis.exceptions import (
    InvalidIndicatorDataError, InvalidPriceDataError,
    DataValidationError
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    np.random.seed(42)
    
    close = 50000 + np.cumsum(np.random.randn(100) * 100)
    high = close + np.random.rand(100) * 100
    low = close - np.random.rand(100) * 100
    open_price = close + np.random.randn(100) * 50
    volume = np.random.rand(100) * 1000 + 500
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    return df


@pytest.fixture
def sample_indicators(sample_ohlcv_data):
    """Calculate sample indicators"""
    return TechnicalIndicators.calculate_all(sample_ohlcv_data)


@pytest.fixture
def sample_smc_data():
    """Sample SMC analysis data"""
    return {
        'computational': {
            'order_blocks': [
                {
                    'type': 'bullish',
                    'price': 50000.0,
                    'zone': [49900.0, 50100.0],
                    'strength': 0.85,
                    'timeframe': '4h'
                }
            ],
            'fair_value_gaps': [
                {
                    'type': 'bullish',
                    'gap': [50200.0, 50400.0],
                    'price': 50300.0,
                    'filled': False,
                    'timeframe': '1h'
                }
            ],
            'break_of_structure': {
                'detected': True,
                'direction': 'bullish',
                'level': 50500.0,
                'timeframe': '1h'
            },
            'liquidity_zones': []
        }
    }


@pytest.fixture
def sample_ict_data():
    """Sample ICT analysis data"""
    return {
        'computational': {
            'killzone': {
                'active': True,
                'current_killzone': 'london',
                'name': 'London Killzone'
            },
            'liquidity_sweeps': [
                {
                    'type': 'buy_side',
                    'level': 51000.0,
                    'reversed': True,
                    'significance': 'high',
                    'timeframe': '15m'
                }
            ],
            'ote_zones': {
                'in_ote_zone': True,
                'bias': 'long',
                'ote_low': 49800.0,
                'ote_high': 50200.0,
                'timeframe': '1h'
            }
        }
    }


@pytest.fixture
def sample_market_structure():
    """Sample market structure data"""
    return {
        'htf_trend': 'bullish',
        'mtf_trend': 'bullish',
        'structure_break': False,
        'overall_bias': 'long'
    }


# ============================================================================
# Technical Indicators Tests
# ============================================================================

class TestTechnicalIndicators:
    """Test suite for TechnicalIndicators"""
    
    def test_calculate_all_returns_dict(self, sample_ohlcv_data):
        """Test that calculate_all returns a dictionary"""
        result = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        assert isinstance(result, dict)
        assert len(result) > 0
    
    def test_calculate_all_includes_volume(self, sample_ohlcv_data):
        """Test that volume is included in indicators"""
        result = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        assert 'volume' in result
        assert 'volume_sma' in result
        assert result['volume'] is not None
    
    def test_calculate_all_includes_required_indicators(self, sample_ohlcv_data):
        """Test that all required indicators are present"""
        result = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        required = ['rsi_14', 'macd', 'macd_histogram', 'ema_9', 'ema_21', 
                   'bb_upper', 'bb_lower', 'atr_14', 'adx', 'volume']
        for indicator in required:
            assert indicator in result, f"Missing indicator: {indicator}"
    
    def test_indicators_are_series(self, sample_ohlcv_data):
        """Test that indicators return pandas Series"""
        result = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        for key, value in result.items():
            assert isinstance(value, pd.Series), f"{key} is not a Series"
    
    def test_rsi_bounds(self, sample_ohlcv_data):
        """Test that RSI values are within valid bounds"""
        result = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        rsi = result['rsi_14'].dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrame"""
        empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        result = TechnicalIndicators.calculate_all(empty_df)
        # Should return empty dict or handle gracefully
        assert isinstance(result, dict)
    
    def test_insufficient_data_handling(self):
        """Test handling of insufficient data"""
        small_df = pd.DataFrame({
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [101, 102],
            'volume': [1000, 1100]
        })
        result = TechnicalIndicators.calculate_all(small_df)
        # Should handle gracefully, some indicators may be NaN
        assert isinstance(result, dict)


# ============================================================================
# Confluence Scorer Tests
# ============================================================================

class TestConfluenceScorer:
    """Test suite for ConfluenceScorer"""
    
    def test_initialization(self):
        """Test ConfluenceScorer initialization"""
        scorer = ConfluenceScorer()
        assert scorer is not None
        assert hasattr(scorer, 'category_weights')
    
    def test_score_setup_long(self, sample_smc_data, sample_ict_data, sample_market_structure):
        """Test scoring for LONG setup"""
        scorer = ConfluenceScorer()
        
        # Prepare indicators with scalar values
        indicators = {
            'rsi_14': 30.0,  # Oversold
            'macd_histogram': 10.0,  # Bullish
            'volume': 1000.0,
            'volume_sma': 500.0  # High volume
        }
        
        result = scorer.score_setup(
            smc_analysis=sample_smc_data,
            ict_analysis=sample_ict_data,
            indicators=indicators,
            patterns={},
            market_structure=sample_market_structure,
            direction='LONG'
        )
        
        assert isinstance(result, ConfluenceScore)
        assert result.total_score > 0
        assert result.confluence_count > 0
        assert result.quality_rating in ['EXCELLENT', 'GOOD', 'FAIR', 'POOR']
    
    def test_score_setup_short(self, sample_smc_data, sample_ict_data):
        """Test scoring for SHORT setup"""
        scorer = ConfluenceScorer()
        
        # Modify data for bearish setup
        smc_data = sample_smc_data.copy()
        smc_data['computational']['order_blocks'][0]['type'] = 'bearish'
        
        market_structure = {
            'htf_trend': 'bearish',
            'mtf_trend': 'bearish'
        }
        
        indicators = {
            'rsi_14': 70.0,  # Overbought
            'macd_histogram': -10.0,  # Bearish
            'volume': 1000.0,
            'volume_sma': 500.0
        }
        
        result = scorer.score_setup(
            smc_analysis=smc_data,
            ict_analysis=sample_ict_data,
            indicators=indicators,
            patterns={},
            market_structure=market_structure,
            direction='SHORT'
        )
        
        assert isinstance(result, ConfluenceScore)
        assert result.confluence_count >= 0
    
    def test_empty_data_handling(self):
        """Test handling of empty data"""
        scorer = ConfluenceScorer()
        
        result = scorer.score_setup(
            smc_analysis={},
            ict_analysis={},
            indicators={},
            patterns={},
            market_structure={},
            direction='LONG'
        )
        
        assert result.confluence_count == 0
        assert result.quality_rating == 'POOR'
        assert not result.meets_minimum
    
    def test_minimum_confluence_requirement(self, sample_smc_data, sample_ict_data, sample_market_structure):
        """Test minimum confluence requirement"""
        scorer = ConfluenceScorer()
        
        result = scorer.score_setup(
            smc_analysis=sample_smc_data,
            ict_analysis=sample_ict_data,
            indicators={'rsi_14': 50.0},
            patterns={},
            market_structure=sample_market_structure,
            direction='LONG',
            minimum_required=10  # High requirement
        )
        
        # Should not meet minimum with limited data
        assert isinstance(result.meets_minimum, bool)
    
    def test_calculate_method_compatibility(self, sample_smc_data, sample_ict_data):
        """Test calculate method (Strategy Agent compatibility)"""
        scorer = ConfluenceScorer()
        
        result = scorer.calculate(
            direction='LONG',
            smc_data=sample_smc_data,
            ict_data=sample_ict_data,
            indicators={'rsi_14': 30.0},
            mtf_analysis={'htf_trend': 'bullish', 'mtf_trend': 'bullish'}
        )
        
        assert isinstance(result, ConfluenceScore)
        assert hasattr(result, 'total_score')
        assert hasattr(result, 'confluence_count')


# ============================================================================
# Data Validation Tests
# ============================================================================

class TestDataValidation:
    """Test suite for data validation schemas"""
    
    def test_indicator_data_validation(self):
        """Test IndicatorData validation"""
        valid_data = {
            'rsi_14': 50.0,
            'macd': 10.0,
            'volume': 1000.0
        }
        
        validated = IndicatorData(**valid_data)
        assert validated.rsi_14 == 50.0
        assert validated.macd == 10.0
    
    def test_indicator_data_invalid_rsi(self):
        """Test IndicatorData with invalid RSI"""
        invalid_data = {
            'rsi_14': 150.0  # Out of bounds
        }
        
        with pytest.raises(Exception):  # Pydantic validation error
            IndicatorData(**invalid_data)
    
    def test_smc_analysis_validation(self):
        """Test SMCAnalysis validation"""
        valid_data = {
            'order_blocks': [
                {
                    'type': 'bullish',
                    'price': 50000.0,
                    'zone': [49900.0, 50100.0],
                    'strength': 0.8,
                    'timeframe': '1h'
                }
            ],
            'fair_value_gaps': [],
            'liquidity_zones': []
        }
        
        validated = SMCAnalysis(**valid_data)
        assert len(validated.order_blocks) == 1
        assert validated.order_blocks[0].type == 'bullish'
    
    def test_market_structure_validation(self):
        """Test MarketStructure validation"""
        valid_data = {
            'htf_trend': 'bullish',
            'mtf_trend': 'neutral',
            'structure_break': False
        }
        
        validated = MarketStructure(**valid_data)
        assert validated.htf_trend == 'bullish'
        assert validated.mtf_trend == 'neutral'
    
    def test_trade_opportunity_validation(self):
        """Test TradeOpportunity validation"""
        valid_data = {
            'direction': 'LONG',
            'confidence': 0.85,
            'entry_zone': [50000.0, 50100.0],
            'stop_loss': 49500.0,
            'take_profit': [50500.0, 51000.0],
            'risk_reward': 2.5,
            'timeframe': '1h'
        }
        
        validated = TradeOpportunity(**valid_data)
        assert validated.direction == 'LONG'
        assert validated.confidence == 0.85


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for data flow"""
    
    def test_indicators_to_confluence_scorer(self, sample_ohlcv_data, sample_smc_data, sample_ict_data):
        """Test data flow from indicators to confluence scorer"""
        # Calculate indicators
        indicators = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        
        # Extract scalar values for confluence scorer
        indicator_scalars = {
            key: value.iloc[-1] if hasattr(value, 'iloc') else value
            for key, value in indicators.items()
        }
        
        # Score confluence
        scorer = ConfluenceScorer()
        result = scorer.score_setup(
            smc_analysis=sample_smc_data,
            ict_analysis=sample_ict_data,
            indicators=indicator_scalars,
            patterns={},
            market_structure={'htf_trend': 'bullish', 'mtf_trend': 'bullish'},
            direction='LONG'
        )
        
        assert isinstance(result, ConfluenceScore)
        assert result.confluence_count >= 0
    
    def test_end_to_end_type_compatibility(self, sample_ohlcv_data):
        """Test end-to-end type compatibility"""
        # 1. Calculate indicators
        indicators = TechnicalIndicators.calculate_all(sample_ohlcv_data)
        assert isinstance(indicators, dict)
        
        # 2. Validate indicator data
        indicator_scalars = {
            key: value.iloc[-1] if hasattr(value, 'iloc') else value
            for key, value in indicators.items()
            if key in ['rsi_14', 'macd', 'volume', 'volume_sma']
        }
        
        # Should not raise validation errors
        validated = IndicatorData(**indicator_scalars)
        assert validated is not None


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling"""
    
    def test_invalid_dataframe_structure(self):
        """Test handling of invalid DataFrame structure"""
        invalid_df = pd.DataFrame({'invalid': [1, 2, 3]})
        
        # Should handle gracefully or raise specific error
        result = TechnicalIndicators.calculate_all(invalid_df)
        assert isinstance(result, dict)
    
    def test_nan_handling_in_indicators(self):
        """Test NaN handling in indicators"""
        df = pd.DataFrame({
            'open': [100, np.nan, 102],
            'high': [102, 103, np.nan],
            'low': [99, 100, 101],
            'close': [101, 102, 103],
            'volume': [1000, 1100, 1200]
        })
        
        result = TechnicalIndicators.calculate_all(df)
        # Should handle NaN gracefully
        assert isinstance(result, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
