"""
Unit tests for LLM Context Builder
"""
import pytest
from src.analysis.llm_context_builder import LLMContextBuilder

@pytest.fixture
def sample_candles():
    return {
        '5m': [{'timestamp': f'2024-01-01 00:{i:02d}', 'open': 43000+i, 'high': 43100+i,
                'low': 42900+i, 'close': 43050+i, 'volume': 1000} for i in range(500)],
        '1h': [{'timestamp': f'2024-01-01 {i:02d}:00', 'open': 43000+i*10, 'high': 43100+i*10,
                'low': 42900+i*10, 'close': 43050+i*10, 'volume': 5000} for i in range(100)]
    }

@pytest.fixture
def sample_indicators():
    import pandas as pd
    return {
        '5m': {
            'rsi_14': pd.Series([45, 50, 55, 60, 58]),
            'macd': pd.Series([10, 12, 15, 18, 20]),
            'macd_signal': pd.Series([8, 10, 12, 14, 16]),
            'macd_histogram': pd.Series([2, 2, 3, 4, 4])
        }
    }

def test_context_builder_initialization():
    builder = LLMContextBuilder()
    assert builder.MAX_TOKENS == 150000
    assert builder.context_cache == {}

def test_build_analysis_context(sample_candles, sample_indicators):
    builder = LLMContextBuilder()

    context = builder.build_analysis_context(
        symbol='BTCUSDT',
        candles=sample_candles,
        indicators=sample_indicators,
        smc_results={'order_blocks': []},
        ict_results={'killzone': {}},
        patterns={'patterns': []}
    )

    assert 'system_prompt' in context
    assert 'current_data' in context
    assert 'indicators' in context
    assert '_context_hash' in context

def test_token_estimation(sample_candles, sample_indicators):
    builder = LLMContextBuilder()

    context = builder.build_analysis_context(
        symbol='BTCUSDT',
        candles=sample_candles,
        indicators=sample_indicators,
        smc_results={'order_blocks': []},
        ict_results={},
        patterns={}
    )

    tokens = builder._estimate_tokens(context)
    assert tokens > 0
    assert tokens < builder.MAX_TOKENS

def test_context_optimization():
    builder = LLMContextBuilder()

    # Create oversized context
    large_context = {
        'system_prompt': 'test' * 10000,  # Much larger system prompt
        'current_data': {'5m': [{'o': 1, 'h': 2, 'l': 0.5, 'c': 1.5, 'v': 100}] * 20000},  # More candles
        'indicators': {},
        'smc_analysis': {},
        'ict_analysis': {},
        'patterns': {},
        'historical_context': {},
        'task_instructions': 'test' * 5000  # Larger task instructions
    }

    tokens = builder._estimate_tokens(large_context)
    assert tokens > builder.MAX_TOKENS

    optimized = builder._optimize_context(large_context, tokens)
    optimized_tokens = builder._estimate_tokens(optimized)

    assert optimized_tokens < tokens