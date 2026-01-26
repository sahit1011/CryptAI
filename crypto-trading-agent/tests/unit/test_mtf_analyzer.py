"""
Unit tests for Multi-Timeframe Analyzer
"""
import pytest
import pandas as pd
import numpy as np
from src.analysis.mtf_analyzer import MultiTimeframeAnalyzer

@pytest.fixture
def mtf_analyzer():
    return MultiTimeframeAnalyzer()

@pytest.fixture
def sample_candles():
    """Generate sample candle data for different timeframes"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')

    # Create trending data (bullish)
    base_price = 43000
    prices = []
    for i in range(100):
        price = base_price + (i * 10) + np.sin(i * 0.1) * 50
        prices.append(price)

    data = {
        '5m': pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p + 20 for p in prices],
            'low': [p - 20 for p in prices],
            'close': [p + np.random.normal(0, 5) for p in prices],
            'volume': [1000 + np.random.normal(0, 100) for _ in range(100)]
        }),
        '15m': pd.DataFrame({
            'timestamp': dates[::3][:33],  # Every 3rd candle, limit to 33
            'open': prices[::3][:33],
            'high': [p + 20 for p in prices[::3][:33]],
            'low': [p - 20 for p in prices[::3][:33]],
            'close': [p + np.random.normal(0, 5) for p in prices[::3][:33]],
            'volume': [3000 + np.random.normal(0, 300) for _ in range(33)]
        }),
        '1h': pd.DataFrame({
            'timestamp': dates[::12][:8],  # Every 12th candle, limit to 8
            'open': prices[::12][:8],
            'high': [p + 20 for p in prices[::12][:8]],
            'low': [p - 20 for p in prices[::12][:8]],
            'close': [p + np.random.normal(0, 5) for p in prices[::12][:8]],
            'volume': [12000 + np.random.normal(0, 1200) for _ in range(8)]
        })
    }

    # Set timestamps as index
    for tf, df in data.items():
        df.set_index('timestamp', inplace=True)

    return data

@pytest.fixture
def sample_indicators():
    """Generate sample indicators for different timeframes"""
    return {
        '5m': {
            'ema_9': pd.Series([43100 + i*5 for i in range(100)]),
            'ema_21': pd.Series([43050 + i*4 for i in range(100)]),
            'ema_50': pd.Series([43000 + i*3 for i in range(100)]),
            'ema_200': pd.Series([42950 + i*2 for i in range(100)]),
            'rsi_14': pd.Series([55 + np.sin(i*0.2)*10 for i in range(100)]),
            'macd': pd.Series([20 + np.sin(i*0.1)*5 for i in range(100)]),
            'macd_signal': pd.Series([18 + np.sin(i*0.1)*4 for i in range(100)]),
            'macd_histogram': pd.Series([2 + np.sin(i*0.1)*1 for i in range(100)])
        },
        '15m': {
            'ema_9': pd.Series([43100 + i*15 for i in range(33)]),
            'ema_21': pd.Series([43050 + i*12 for i in range(33)]),
            'ema_50': pd.Series([43000 + i*9 for i in range(33)]),
            'ema_200': pd.Series([42950 + i*6 for i in range(33)]),
            'rsi_14': pd.Series([55 + np.sin(i*0.6)*10 for i in range(33)]),
            'macd': pd.Series([20 + np.sin(i*0.3)*5 for i in range(33)]),
            'macd_signal': pd.Series([18 + np.sin(i*0.3)*4 for i in range(33)]),
            'macd_histogram': pd.Series([2 + np.sin(i*0.3)*1 for i in range(33)])
        },
        '1h': {
            'ema_9': pd.Series([43100 + i*60 for i in range(8)]),
            'ema_21': pd.Series([43050 + i*48 for i in range(8)]),
            'ema_50': pd.Series([43000 + i*36 for i in range(8)]),
            'ema_200': pd.Series([42950 + i*24 for i in range(8)]),
            'rsi_14': pd.Series([55 + np.sin(i*2.4)*10 for i in range(8)]),
            'macd': pd.Series([20 + np.sin(i*1.2)*5 for i in range(8)]),
            'macd_signal': pd.Series([18 + np.sin(i*1.2)*4 for i in range(8)]),
            'macd_histogram': pd.Series([2 + np.sin(i*1.2)*1 for i in range(8)])
        }
    }

def test_mtf_analyzer_initialization(mtf_analyzer):
    """Test analyzer initializes correctly"""
    assert mtf_analyzer.TIMEFRAME_HIERARCHY == {'1d': 5, '4h': 4, '1h': 3, '15m': 2, '5m': 1}

def test_analyze_with_sample_data(mtf_analyzer, sample_candles, sample_indicators):
    """Test complete analysis with sample data"""
    result = mtf_analyzer.analyze(sample_candles, sample_indicators)

    # Check required fields
    assert 'overall_bias' in result
    assert 'bias_strength' in result
    assert 'alignment' in result
    assert 'timeframe_trends' in result
    assert 'entry_timing' in result
    assert 'recommendation' in result
    assert 'confluence_score' in result

    # Check bias is valid
    assert result['overall_bias'] in ['bullish', 'bearish', 'neutral']

    # Check strength is between 0 and 1
    assert 0 <= result['bias_strength'] <= 1

    # Check confluence score
    assert 0 <= result['confluence_score'] <= 1

def test_analyze_timeframe_bullish(mtf_analyzer, sample_candles, sample_indicators):
    """Test single timeframe analysis - bullish case"""
    tf_result = mtf_analyzer._analyze_timeframe(
        sample_candles['5m'],
        sample_indicators['5m']
    )

    assert 'trend' in tf_result
    assert 'strength' in tf_result
    assert tf_result['trend'] in ['bullish', 'bearish', 'neutral']
    assert 0 <= tf_result['strength'] <= 1

def test_get_ema_trend_bullish(mtf_analyzer):
    """Test EMA trend detection - bullish"""
    indicators = {
        'ema_9': pd.Series([43100]),
        'ema_21': pd.Series([43050]),
        'ema_50': pd.Series([43000]),
        'ema_200': pd.Series([42950])
    }

    trend = mtf_analyzer._get_ema_trend(indicators)
    assert trend == 'bullish'

def test_get_ema_trend_bearish(mtf_analyzer):
    """Test EMA trend detection - bearish"""
    indicators = {
        'ema_9': pd.Series([42950]),
        'ema_21': pd.Series([43000]),
        'ema_50': pd.Series([43050]),
        'ema_200': pd.Series([43100])
    }

    trend = mtf_analyzer._get_ema_trend(indicators)
    assert trend == 'bearish'

def test_get_price_trend_bullish(mtf_analyzer):
    """Test price trend detection - bullish"""
    # Create clearly bullish price data
    prices = [43000 + i*50 for i in range(20)]  # Strong upward trend

    df = pd.DataFrame({
        'close': prices,
        'volume': [1000] * 20
    })

    trend = mtf_analyzer._get_price_trend(df)
    assert trend == 'bullish'

def test_get_price_trend_bearish(mtf_analyzer):
    """Test price trend detection - bearish"""
    # Create clearly bearish price data
    prices = [43000 - i*50 for i in range(20)]  # Strong downward trend

    df = pd.DataFrame({
        'close': prices,
        'volume': [1000] * 20
    })

    trend = mtf_analyzer._get_price_trend(df)
    assert trend == 'bearish'

def test_get_momentum_bullish(mtf_analyzer):
    """Test momentum detection - bullish"""
    indicators = {'macd_histogram': pd.Series([5])}
    momentum = mtf_analyzer._get_momentum(indicators)
    assert momentum == 'bullish'

def test_get_momentum_bearish(mtf_analyzer):
    """Test momentum detection - bearish"""
    indicators = {'macd_histogram': pd.Series([-5])}
    momentum = mtf_analyzer._get_momentum(indicators)
    assert momentum == 'bearish'

def test_get_volume_trend_increasing(mtf_analyzer):
    """Test volume trend detection - increasing"""
    df = pd.DataFrame({
        'volume': [1000] * 10 + [1400] * 10  # Recent volume 40% higher
    })

    trend = mtf_analyzer._get_volume_trend(df)
    assert trend == 'increasing'

def test_get_rsi_position_oversold(mtf_analyzer):
    """Test RSI position - oversold"""
    indicators = {'rsi_14': pd.Series([25])}
    position = mtf_analyzer._get_rsi_position(indicators)
    assert position == 'oversold'

def test_get_rsi_position_overbought(mtf_analyzer):
    """Test RSI position - overbought"""
    indicators = {'rsi_14': pd.Series([75])}
    position = mtf_analyzer._get_rsi_position(indicators)
    assert position == 'overbought'

def test_calculate_trend_score_bullish(mtf_analyzer):
    """Test trend score calculation - bullish"""
    score = mtf_analyzer._calculate_trend_score(
        ema_trend='bullish',
        price_trend='bullish',
        momentum='bullish',
        volume_trend='increasing',
        rsi_position='bullish'
    )

    assert score > 0

def test_calculate_trend_score_bearish(mtf_analyzer):
    """Test trend score calculation - bearish"""
    score = mtf_analyzer._calculate_trend_score(
        ema_trend='bearish',
        price_trend='bearish',
        momentum='bearish',
        volume_trend='decreasing',
        rsi_position='bearish'
    )

    assert score < 0

def test_determine_overall_bias_bullish(mtf_analyzer):
    """Test overall bias determination - bullish"""
    tf_trends = {
        '1h': {'trend': 'bullish', 'strength': 0.8},
        '15m': {'trend': 'bullish', 'strength': 0.7},
        '5m': {'trend': 'bullish', 'strength': 0.9}
    }

    bias, strength = mtf_analyzer._determine_overall_bias(tf_trends)
    assert bias == 'bullish'
    assert strength > 0

def test_check_alignment_strongly_aligned(mtf_analyzer):
    """Test alignment check - strongly aligned"""
    tf_trends = {
        '1h': {'trend': 'bullish'},
        '15m': {'trend': 'bullish'},
        '5m': {'trend': 'bullish'}
    }

    alignment = mtf_analyzer._check_alignment(tf_trends)
    assert alignment == 'strongly_aligned_bullish'

def test_check_alignment_conflicting(mtf_analyzer):
    """Test alignment check - conflicting"""
    tf_trends = {
        '1h': {'trend': 'bullish'},
        '15m': {'trend': 'bearish'},
        '5m': {'trend': 'neutral'}
    }

    alignment = mtf_analyzer._check_alignment(tf_trends)
    assert alignment == 'conflicting'

def test_evaluate_entry_timing_excellent(mtf_analyzer):
    """Test entry timing evaluation - excellent"""
    tf_trends = {
        '1d': {'trend': 'bullish'},
        '4h': {'trend': 'bearish'},  # Pullback
        '15m': {'trend': 'bullish'}  # Reversal
    }

    timing = mtf_analyzer._evaluate_entry_timing(tf_trends, 'bullish')
    assert timing == 'excellent'

def test_generate_recommendation_strong_setup(mtf_analyzer):
    """Test recommendation generation - strong setup"""
    recommendation = mtf_analyzer._generate_recommendation(
        bias='bullish',
        strength=0.8,
        alignment='strongly_aligned_bullish',
        timing='excellent'
    )

    assert 'STRONG BULLISH SETUP' in recommendation

def test_calculate_confluence_score(mtf_analyzer):
    """Test confluence score calculation"""
    tf_trends = {
        '1h': {'strength': 0.8},
        '15m': {'strength': 0.7},
        '5m': {'strength': 0.9}
    }

    score = mtf_analyzer._calculate_confluence_score(tf_trends)
    assert 0 <= score <= 1

def test_empty_result(mtf_analyzer):
    """Test empty result handling"""
    result = mtf_analyzer._empty_result()

    assert result['overall_bias'] == 'unknown'
    assert result['bias_strength'] == 0.0
    assert result['confluence_score'] == 0.0

def test_analyze_with_insufficient_data(mtf_analyzer):
    """Test analysis with insufficient data"""
    # Empty data should return empty result
    result = mtf_analyzer.analyze({}, {})

    assert result['overall_bias'] == 'neutral'  # Default when no data
    assert result['recommendation'] == 'No clear directional bias. Wait for better setup.'