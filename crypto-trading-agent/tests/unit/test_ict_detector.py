"""
Unit tests for ICT Detector
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.analysis.ict_detector import ICTDetector

@pytest.fixture
def sample_data():
    """Generate sample OHLCV data"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')

    # Create realistic price movement
    np.random.seed(42)
    base_price = 43000

    data = []
    for i, date in enumerate(dates):
        # Add some trend and volatility
        trend = (i / 100) * 1000
        volatility = np.random.randn() * 100

        close = base_price + trend + volatility
        high = close + abs(np.random.randn() * 50)
        low = close - abs(np.random.randn() * 50)
        open_price = close + np.random.randn() * 30
        volume = 1000 + np.random.randint(-200, 200)

        data.append({
            'timestamp': date,
            'open': max(low, open_price),
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df

@pytest.mark.asyncio
async def test_ict_detector_initialization():
    """Test ICT detector initializes correctly"""
    detector = ICTDetector()
    assert len(detector.KILL_ZONES) == 4
    assert 'london' in detector.KILL_ZONES
    assert 'new_york' in detector.KILL_ZONES

@pytest.mark.asyncio
async def test_killzone_detection(sample_data):
    """Test killzone identification"""
    detector = ICTDetector()
    result = detector.analyze_killzone(sample_data)

    assert 'current_killzone' in result
    assert 'killzone_stats' in result
    assert 'optimal_for_trading' in result

@pytest.mark.asyncio
async def test_liquidity_sweep_detection(sample_data):
    """Test liquidity sweep detection"""
    detector = ICTDetector()
    sweeps = detector.detect_liquidity_sweeps(sample_data)

    assert isinstance(sweeps, list)
    if len(sweeps) > 0:
        sweep = sweeps[0]
        assert 'type' in sweep
        assert 'level' in sweep
        assert 'strength' in sweep

@pytest.mark.asyncio
async def test_order_flow_analysis(sample_data):
    """Test order flow phase detection"""
    detector = ICTDetector()
    flow = detector.analyze_order_flow(sample_data)

    assert 'phase' in flow
    assert 'confidence' in flow
    assert flow['phase'] in ['accumulation', 'manipulation', 'distribution', 'markup', 'markdown', 'neutral']
    assert 0 <= flow['confidence'] <= 1

@pytest.mark.asyncio
async def test_ote_zone_calculation(sample_data):
    """Test OTE zone calculation"""
    detector = ICTDetector()
    ote = detector.calculate_ote_zones(sample_data)

    assert 'ote_low' in ote
    assert 'ote_high' in ote
    assert 'bias' in ote
    assert ote['ote_high'] > ote['ote_low']

@pytest.mark.asyncio
async def test_complete_ict_analysis(sample_data):
    """Test complete ICT analysis"""
    detector = ICTDetector()
    result = detector.analyze(sample_data)

    assert 'killzone' in result
    assert 'liquidity_sweeps' in result
    assert 'order_flow' in result
    assert 'ote_zones' in result
    assert 'setup_quality' in result
    assert 'confluence_score' in result

    # Check performance
    assert result['performance_ms'] < 200

@pytest.mark.asyncio
async def test_setup_quality_assessment(sample_data):
    """Test setup quality classification"""
    detector = ICTDetector()
    result = detector.analyze(sample_data)

    assert result['setup_quality'] in ['excellent', 'good', 'fair', 'poor']
    assert 0 <= result['confluence_score'] <= 1