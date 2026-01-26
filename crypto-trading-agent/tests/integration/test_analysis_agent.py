"""
Integration tests for Market Analysis Agent
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import pandas as pd

from src.agents.analysis_agent import MarketAnalysisAgent
from src.core.message_bus import MessageBus, AgentMessage
from src.core.state_manager import StateManager

@pytest.fixture
async def mock_message_bus():
    bus = AsyncMock(spec=MessageBus)
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus

@pytest.fixture
async def mock_state_manager():
    manager = AsyncMock(spec=StateManager)
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock()
    return manager

@pytest.fixture
def sample_market_data():
    """Generate realistic market data"""
    dates = pd.date_range(start='2024-01-01', periods=500, freq='5min')

    data = {
        '5m': [],
        '15m': [],
        '1h': [],
        '4h': [],
        '1d': []
    }

    # Generate 5m candles
    base_price = 43000
    for i, date in enumerate(dates):
        close = base_price + (i * 2) + (50 * (i % 10))
        data['5m'].append({
            'timestamp': date.isoformat(),
            'open': close - 10,
            'high': close + 20,
            'low': close - 30,
            'close': close,
            'volume': 1000 + (i % 100)
        })

    # Generate higher timeframes (simplified)
    for tf in ['15m', '1h', '4h', '1d']:
        data[tf] = data['5m'][:100]  # Simplified

    return data

@pytest.mark.asyncio
async def test_analysis_agent_initialization(mock_message_bus, mock_state_manager):
    """Test agent initializes correctly"""
    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)

    assert agent.name == "analysis_agent"
    assert agent.indicators_calc is not None
    assert agent.smc_detector is not None
    assert agent.ict_detector is not None

@pytest.mark.asyncio
async def test_computational_analysis(mock_message_bus, mock_state_manager, sample_market_data):
    """Test computational analysis pipeline"""
    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)

    # Convert to proper format
    candles = sample_market_data

    result = await agent._run_computational_analysis(candles)

    assert 'indicators' in result
    assert 'smc' in result
    assert 'ict' in result
    assert 'patterns' in result

    # Check indicators were calculated
    assert '5m' in result['indicators']
    assert 'rsi_14' in result['indicators']['5m']

@pytest.mark.asyncio
@patch('src.agents.analysis_agent.AsyncAnthropic')
async def test_llm_analysis_with_mock(
    mock_anthropic,
    mock_message_bus,
    mock_state_manager,
    sample_market_data
):
    """Test LLM analysis with mocked response"""

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='''
{
  "market_structure": {
    "1d_trend": "bullish",
    "4h_trend": "bullish",
    "1h_trend": "bullish",
    "alignment": "aligned",
    "overall_bias": "bullish"
  },
  "key_levels": {
    "resistance": [44000, 44500, 45000],
    "support": [43000, 42500, 42000],
    "most_significant": {
      "level": 43000,
      "type": "support",
      "reason": "Strong order block"
    }
  },
  "smc_confluences": [
    {
      "type": "order_block",
      "timeframe": "4h",
      "description": "Bullish OB at 43000",
      "significance": "high"
    }
  ],
  "ict_setup": {
    "killzone_active": true,
    "liquidity_sweeps": ["asian_low"],
    "order_flow_phase": "accumulation",
    "ote_zone_status": "in_zone"
  },
  "trade_opportunities": [
    {
      "direction": "LONG",
      "entry_zone": [43000, 43100],
      "confluence_count": 5,
      "key_factors": [
        "Bullish order block",
        "FVG above",
        "Liquidity sweep",
        "RSI divergence",
        "MACD bullish"
      ],
      "confidence": 0.85,
      "invalidation_level": 42800
    }
  ],
  "reasoning": "Strong bullish setup with multiple confluences"
}
    ''')]
    mock_response.usage = MagicMock(input_tokens=50000, output_tokens=1000)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_anthropic.return_value = mock_client

    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)
    agent.llm_client = mock_client

    # Run analysis
    result = await agent.analyze_market(
        symbol='BTCUSDT',
        candles=sample_market_data
    )

    assert result['symbol'] == 'BTCUSDT'
    assert len(result['trade_opportunities']) > 0
    assert result['overall_confidence'] > 0

@pytest.mark.asyncio
async def test_full_pipeline(mock_message_bus, mock_state_manager, sample_market_data):
    """Test complete analysis pipeline"""
    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)

    # Mock LLM to avoid actual API call
    agent.llm_client = AsyncMock()
    agent.llm_client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text='{"market_structure": {}, "key_levels": {}, "smc_confluences": [], "ict_setup": {}, "trade_opportunities": [], "reasoning": "test"}')],
            usage=MagicMock(input_tokens=1000, output_tokens=100)
        )
    )

    # Run analysis
    result = await agent.analyze_market(
        symbol='BTCUSDT',
        candles=sample_market_data
    )

    # Validate structure
    assert 'symbol' in result
    assert 'timestamp' in result
    assert 'market_structure' in result
    assert 'smc_analysis' in result
    assert 'ict_analysis' in result
    assert 'performance_metrics' in result

    # Check performance
    assert result['performance_metrics']['total_time_seconds'] < 60

@pytest.mark.asyncio
async def test_error_handling_fallback(mock_message_bus, mock_state_manager, sample_market_data):
    """Test fallback when LLM fails"""
    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)

    # Mock LLM to raise error
    agent.llm_client = AsyncMock()
    agent.llm_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

    # Should still complete with fallback
    result = await agent.analyze_market(
        symbol='BTCUSDT',
        candles=sample_market_data
    )

    assert result['is_fallback'] == True
    assert 'smc_analysis' in result

@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skipif("not config.getoption('--run-llm')", reason="Skipping real LLM test")
async def test_real_llm_integration(mock_message_bus, mock_state_manager, sample_market_data, pytestconfig):
    """
    Test with real LLM API (optional, requires API key)
    Run with: pytest tests/integration/test_analysis_agent.py --run-llm
    """
    agent = MarketAnalysisAgent(mock_message_bus, mock_state_manager)

    result = await agent.analyze_market(
        symbol='BTCUSDT',
        candles=sample_market_data
    )

    assert result['symbol'] == 'BTCUSDT'
    assert 'trade_opportunities' in result
    assert result['performance_metrics']['llm_time'] > 0

def pytest_addoption(parser):
    parser.addoption(
        "--run-llm",
        action="store_true",
        default=False,
        help="run tests that call real LLM API"
    )

@pytest.fixture
def pytestconfig(request):
    return request.config