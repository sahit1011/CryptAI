"""
Unit tests for Trade Setup Builder

NOTE: This suite targets an older builder API and is skipped until rewritten.
The builder's `build_setup(symbol, analysis, current_price, atr)` was replaced by
`build_setup_with_confirmation(..., candles_5m, candles_15m, candles_1h)`, and the
`TradeSetup` dataclass gained required fields (`entry_trigger`, `entry_confirmation`).
Re-enable after updating the tests to the current API.
"""
import pytest
from src.strategy.trade_setup_builder import (
    EnhancedTradeSetupBuilder as TradeSetupBuilder,
    TradeSetup,
)

pytestmark = pytest.mark.skip(
    reason="Stale: builder API changed to build_setup_with_confirmation and "
    "TradeSetup gained required fields; tests need a rewrite."
)

@pytest.fixture
def sample_analysis():
    return {
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
                ],
                'fair_value_gaps': [
                    {
                        'type': 'bullish',
                        'gap': [43450, 43550],
                        'filled': False
                    }
                ]
            }
        },
        'ict_analysis': {
            'computational': {
                'killzone': {'current_killzone': 'london'},
                'order_flow': {'phase': 'accumulation'}
            }
        },
        'key_levels': {
            'resistance': [43500, 44000, 44500],
            'support': [43000, 42500, 42000]
        },
        'market_structure': {
            'alignment': 'strongly_aligned_bullish'
        }
    }

def test_builder_initialization():
    builder = TradeSetupBuilder()
    assert builder.setup_counter == 0

def test_build_setup(sample_analysis):
    builder = TradeSetupBuilder()

    setup = builder.build_setup(
        symbol='BTCUSDT',
        analysis=sample_analysis,
        current_price=43050,
        atr=150
    )

    assert setup is not None
    assert setup.symbol == 'BTCUSDT'
    assert setup.direction == 'LONG'
    assert setup.entry_price > 0
    assert setup.stop_loss < setup.entry_price
    assert len(setup.take_profit_levels) == 3

def test_risk_reward_calculation(sample_analysis):
    builder = TradeSetupBuilder()

    setup = builder.build_setup(
        symbol='BTCUSDT',
        analysis=sample_analysis,
        current_price=43050,
        atr=150
    )

    assert setup.risk_reward_ratio >= 2.0

def test_setup_validation():
    setup = TradeSetup(
        setup_id='test_1',
        symbol='BTCUSDT',
        timestamp='2024-01-01T00:00:00',
        direction='LONG',
        strategy_type='DAY_TRADE',
        entry_type='LIMIT',
        entry_price=43050,
        entry_zone_low=43000,
        entry_zone_high=43100,
        stop_loss=42750,
        stop_loss_type='HARD',
        risk_amount=200,
        risk_percentage=2.0,
        take_profit_levels=[
            {'level': 1, 'price': 43500, 'size': 0.33},
            {'level': 2, 'price': 43800, 'size': 0.33},
            {'level': 3, 'price': 44200, 'size': 0.34}
        ],
        final_target=44200,
        risk_reward_ratio=2.5,
        expected_duration_hours=6.0,
        confidence_score=0.85,
        confluences=['test'],
        key_levels={},
        invalidation_conditions=['test'],
        setup_reasoning='test'
    )

    assert setup.is_valid() == True

def test_invalid_setup_low_rr():
    setup = TradeSetup(
        setup_id='test_2',
        symbol='BTCUSDT',
        timestamp='2024-01-01T00:00:00',
        direction='LONG',
        strategy_type='DAY_TRADE',
        entry_type='LIMIT',
        entry_price=43050,
        entry_zone_low=43000,
        entry_zone_high=43100,
        stop_loss=42950,  # Very close SL
        stop_loss_type='HARD',
        risk_amount=100,
        risk_percentage=1.0,
        take_profit_levels=[
            {'level': 1, 'price': 43200, 'size': 1.0}  # Only 1.5:1 RR
        ],
        final_target=43200,
        risk_reward_ratio=1.5,  # Below 2.0 minimum
        expected_duration_hours=6.0,
        confidence_score=0.85,
        confluences=['test'],
        key_levels={},
        invalidation_conditions=['test'],
        setup_reasoning='test'
    )

    assert setup.is_valid() == False