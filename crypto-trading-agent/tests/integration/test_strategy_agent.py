"""
Integration tests for Strategy Generation Agent
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.strategy_agent import StrategyGenerationAgent

@pytest.fixture
def sample_analysis():
    return {
        'symbol': 'BTCUSDT',
        'trade_opportunities': [
            {
                'direction': 'LONG',
                'entry_zone': [43000, 43100],
                'confluence_count': 5,
                'confidence': 0.85,
                'invalidation_level': 42750,
                'key_factors': [
                    'Bullish order block at 43000',
                    'FVG above at 43500',
                    'Liquidity sweep below Asian low',
                    'RSI bullish divergence',
                    'MACD bullish crossover'
                ]
            }
        ],
        'smc_analysis': {
            'computational': {
                'order_blocks': [
                    {
                        'type': 'bullish',
                        'zone': [43000, 43100],
                        'strength': 0.85
                    }
                ]
            }
        },
        'ict_analysis': {
            'computational': {
                'killzone': {'current_killzone': 'london'}
            }
        },
        '_raw_computational': {
            'indicators': {
                '1h': {
                    'rsi': {'divergence': 'bullish'},
                    'macd': {'trend': 'bullish'}
                }
            }
        }
    }

@pytest.fixture
def mock_state_manager():
    """Mock state manager that returns actual values"""
    mock = AsyncMock()
    mock.get.side_effect = lambda key: {
        "price:BTCUSDT": 43050.0,
        "atr:BTCUSDT": 150.0,
        "account_balance": 10000.0
    }.get(key, None)
    return mock

@pytest.mark.asyncio
async def test_strategy_generation_pipeline(sample_analysis, mock_state_manager):
    """Test complete strategy generation pipeline"""

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    # Mock LLM
    agent.llm_client = AsyncMock()
    agent.llm_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"trade_setup": null, "reason": "test"}'))],
            usage=MagicMock(prompt_tokens=1000, completion_tokens=100)
        )
    )

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    assert 'trade_setup' in result
    assert 'performance_metrics' in result
    assert 'confluence_analysis' in result
    assert 'sizing_analysis' in result

@pytest.mark.asyncio
async def test_confluence_scoring_integration(sample_analysis, mock_state_manager):
    """Test that confluence scorer is properly integrated"""

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    # Mock LLM to return null (computational only)
    agent.llm_client = AsyncMock()
    agent.llm_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"trade_setup": null, "reason": "insufficient confluences"}'))],
            usage=MagicMock(prompt_tokens=1000, completion_tokens=100)
        )
    )

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    # Should have confluence analysis
    assert 'confluence_analysis' in result
    confluence = result['confluence_analysis']
    assert 'total_score' in confluence
    assert 'confluence_count' in confluence
    assert 'quality_rating' in confluence

@pytest.mark.asyncio
async def test_insufficient_confluences(sample_analysis, mock_state_manager):
    """Test handling of insufficient confluences"""

    # Modify analysis to have low confluence
    sample_analysis['trade_opportunities'][0]['confluence_count'] = 2

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    assert result['trade_setup'] is None
    assert 'No valid computational setup' in result['reason']

@pytest.mark.asyncio
async def test_llm_fallback_mode(sample_analysis, mock_state_manager):
    """Test fallback to computational mode when LLM fails"""

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    # Mock LLM to fail
    agent.llm_client = AsyncMock()
    agent.llm_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    # Should still generate a result (computational mode)
    assert 'trade_setup' in result
    assert result.get('is_fallback') is None  # Not in fallback mode since LLM failed but computational worked

@pytest.mark.asyncio
async def test_position_sizing_integration(sample_analysis, mock_state_manager):
    """Test position sizing integration"""

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    # Mock LLM
    agent.llm_client = AsyncMock()
    agent.llm_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"trade_setup": null, "reason": "test"}'))],
            usage=MagicMock(prompt_tokens=1000, completion_tokens=100)
        )
    )

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    assert 'sizing_analysis' in result
    sizing = result['sizing_analysis']
    assert 'recommended_size' in sizing
    assert 'risk_amount' in sizing

@pytest.mark.asyncio
async def test_performance_metrics(sample_analysis, mock_state_manager):
    """Test performance metrics collection"""

    agent = StrategyGenerationAgent(AsyncMock(), mock_state_manager)

    # Mock LLM
    agent.llm_client = AsyncMock()
    agent.llm_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"trade_setup": null, "reason": "test"}'))],
            usage=MagicMock(prompt_tokens=1000, completion_tokens=100)
        )
    )

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=sample_analysis
    )

    assert 'performance_metrics' in result
    metrics = result['performance_metrics']
    assert 'total_time_seconds' in metrics
    assert 'confluence_time' in metrics
    assert all(v >= 0 for v in metrics.values())

@pytest.mark.asyncio
async def test_no_trade_opportunities():
    """Test handling when no trade opportunities exist"""

    analysis = {
        'symbol': 'BTCUSDT',
        'trade_opportunities': []
    }

    agent = StrategyGenerationAgent(AsyncMock(), AsyncMock())

    result = await agent.generate_strategy(
        symbol='BTCUSDT',
        analysis=analysis
    )

    assert result['trade_setup'] is None
    assert 'No valid computational setup' in result['reason']