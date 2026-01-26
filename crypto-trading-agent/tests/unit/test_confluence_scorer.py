"""
Unit tests for Confluence Scorer (Consolidated Version)
"""
import pytest
from src.strategy.confluence_scorer import ConfluenceScorer, ConfluenceScore, Confluence

@pytest.fixture
def sample_smc_data():
    return {
        'computational': {
            'order_blocks': [
                {
                    'type': 'bullish',
                    'zone': [43000, 43100],
                    'strength': 0.85,
                    'timeframe': '4h'
                }
            ],
            'fair_value_gaps': [
                {
                    'type': 'bullish',
                    'gap': [43450, 43550],
                    'filled': False,
                    'timeframe': '1h'
                }
            ],
            'break_of_structure': {
                'detected': True,
                'direction': 'bullish',
                'timeframe': '1h'
            },
            'liquidity_zones': [
                {
                    'type': 'bearish',
                    'zone': [44000, 44100],
                    'strength': 0.8
                }
            ]
        }
    }

@pytest.fixture
def sample_ict_data():
    return {
        'computational': {
            'killzone': {'active': True, 'current_killzone': 'london'},
            'liquidity_sweeps': [
                {
                    'type': 'buy_side',
                    'level': 44000,
                    'reversed': True,
                    'significance': 'high',
                    'timeframe': '15m'
                }
            ],
            'ote_zones': {
                'in_ote_zone': True,
                'bias': 'long',
                'ote_low': 42900,
                'ote_high': 43100,
                'timeframe': '1h'
            }
        }
    }

@pytest.fixture
def sample_indicators():
    return {
        '1h': {
            'rsi_14': 30.0, # Oversold
            'macd_histogram': 10.0, # Bullish
            'volume': 1000.0,
            'volume_sma': 500.0 # High volume
        }
    }

@pytest.fixture
def sample_mtf_analysis():
    return {
        'htf_trend': 'bullish',
        'mtf_trend': 'bullish',
        'overall_bias': 'long'
    }

def test_confluence_scorer_initialization():
    scorer = ConfluenceScorer()
    assert scorer is not None

def test_score_long_setup(sample_smc_data, sample_ict_data, sample_indicators, sample_mtf_analysis):
    scorer = ConfluenceScorer()

    result = scorer.calculate(
        direction='LONG',
        smc_data=sample_smc_data,
        ict_data=sample_ict_data,
        indicators=sample_indicators,
        mtf_analysis=sample_mtf_analysis
    )

    assert isinstance(result, ConfluenceScore)
    assert result.total_score > 0.0
    assert result.confluence_count > 0
    assert result.confidence_level > 0.0
    assert result.quality_rating in ['EXCELLENT', 'GOOD', 'FAIR', 'POOR']
    assert isinstance(result.factors, list)
    assert isinstance(result.breakdown, dict)

def test_score_short_setup(sample_smc_data, sample_ict_data, sample_indicators, sample_mtf_analysis):
    scorer = ConfluenceScorer()

    # Adjust data for short setup
    sample_smc_data['computational']['order_blocks'][0]['type'] = 'bearish'
    sample_indicators['1h']['rsi_14'] = 70.0 # Overbought
    sample_mtf_analysis['htf_trend'] = 'bearish'
    sample_mtf_analysis['mtf_trend'] = 'bearish'

    result = scorer.calculate(
        direction='SHORT',
        smc_data=sample_smc_data,
        ict_data=sample_ict_data,
        indicators=sample_indicators,
        mtf_analysis=sample_mtf_analysis
    )

    assert isinstance(result, ConfluenceScore)
    assert result.total_score > 0.0
    assert result.confluence_count > 0

def test_empty_data():
    scorer = ConfluenceScorer()

    result = scorer.calculate(
        direction='LONG',
        smc_data={},
        ict_data={},
        indicators={},
        mtf_analysis={}
    )

    assert result.confluence_count == 0
    assert result.total_score == 0.0
    assert result.quality_rating == 'POOR'

def test_smc_scoring(sample_smc_data):
    scorer = ConfluenceScorer()
    confluences = scorer._score_smc(sample_smc_data, 'LONG')
    
    assert len(confluences) > 0
    assert all(isinstance(c, Confluence) for c in confluences)
    assert all(c.category == 'SMC' for c in confluences)

def test_ict_scoring(sample_ict_data):
    scorer = ConfluenceScorer()
    confluences = scorer._score_ict(sample_ict_data, 'LONG')
    
    assert len(confluences) > 0
    assert all(c.category == 'ICT' for c in confluences)

def test_indicator_scoring(sample_indicators):
    scorer = ConfluenceScorer()
    confluences = scorer._score_indicators(sample_indicators, 'LONG')
    
    assert len(confluences) > 0
    assert all(c.category == 'INDICATOR' for c in confluences)

def test_to_dict():
    score = ConfluenceScore(
        total_score=0.75,
        confluence_count=5,
        confidence_level=0.85,
        quality_rating='GOOD',
        meets_minimum=True,
        reasoning="Test reasoning",
        confluences=[
            Confluence('Test Factor', 'SMC', 1.0, 'Test Desc', '1h')
        ],
        by_category={'SMC': 1}
    )

    result = score.to_dict()

    assert result['total_score'] == 0.75
    assert result['confluence_count'] == 5
    assert result['quality_rating'] == 'GOOD'
    assert len(result['factors']) == 1
    assert result['factors'][0]['factor'] == 'Test Factor'