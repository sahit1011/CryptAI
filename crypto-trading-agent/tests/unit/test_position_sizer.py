"""
Unit tests for Position Sizing Engine
"""
import pytest
from src.strategy.position_sizer import PositionSizer, PositionSizeResult

def test_position_sizer_initialization():
    sizer = PositionSizer()
    assert sizer.default_risk_percent == 2.0
    assert sizer.max_portfolio_heat == 6.0
    assert sizer.max_leverage == 10.0

def test_fixed_risk_sizing():
    sizer = PositionSizer()

    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500,
        risk_percent=2.0
    )

    # Risk amount = 10000 * 0.02 = 200
    # Price risk = 50000 - 49500 = 500
    # Size = 200 / 500 = 0.4
    assert abs(result.recommended_size - 0.4) < 0.001
    assert result.sizing_method == 'fixed_risk'
    assert result.risk_amount == 200.0
    assert result.position_value == 20000.0  # 0.4 * 50000
    assert result.leverage_used == 2.0  # 20000 / 10000

def test_volatility_adjusted_sizing():
    sizer = PositionSizer()

    # High volatility scenario (ATR > stop distance)
    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500,  # 500 point stop
        risk_percent=2.0,
        atr=800,  # ATR > stop distance
        method='volatility_adjusted'
    )

    # Base size would be 0.4, but ATR ratio = 800/500 = 1.6
    # Adjusted size should be 0.4 * 1.6 = 0.64 (capped at 2.0x)
    assert result.recommended_size > 0.4
    assert result.sizing_method == 'volatility_adjusted'

def test_kelly_sizing():
    sizer = PositionSizer()

    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500,
        method='kelly'
    )

    # Kelly should give conservative sizing
    assert result.recommended_size > 0
    assert result.sizing_method == 'kelly'
    # Quarter Kelly with 50% win rate and 2.5 RR - check it's reasonable
    assert result.recommended_size <= 1.0  # Should be capped appropriately

def test_portfolio_heat_limit():
    sizer = PositionSizer(max_portfolio_heat=6.0)

    # Current exposure 4%, trying to risk 3% (would exceed 6% total)
    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500,
        risk_percent=3.0,
        current_exposure=4.0
    )

    # Should be capped to 2% available exposure
    expected_size = (10000 * 0.02) / 500  # 200 / 500 = 0.4
    assert abs(result.recommended_size - expected_size) < 0.001
    assert len(result.warnings) > 0
    assert "exceeds available exposure" in result.warnings[0]

def test_leverage_capping():
    sizer = PositionSizer(max_leverage=5.0)

    result = sizer.calculate_size(
        account_balance=1000,
        entry_price=50000,
        stop_loss=49500,
        risk_percent=10.0  # Would create high leverage
    )

    # Max position value = 1000 * 5 = 5000
    # Max size = 5000 / 50000 = 0.1
    assert result.recommended_size <= 0.1
    assert result.leverage_used <= 5.0

def test_max_size_calculation():
    sizer = PositionSizer(max_leverage=10.0)

    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500
    )

    # Max size = (10000 * 10) / 50000 = 2.0
    assert result.max_size == 2.0

def test_correlation_adjusted_sizing():
    sizer = PositionSizer()

    existing_positions = [
        {'symbol': 'BTCUSDT', 'size': 0.1}
    ]

    correlation_matrix = {
        'BTCUSDT': 0.8  # High correlation
    }

    result = sizer.calculate_with_correlation(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500,
        existing_positions=existing_positions,
        correlation_matrix=correlation_matrix
    )

    # Should be reduced due to correlation
    base_result = sizer.calculate_size(10000, 50000, 49500)
    assert result.recommended_size < base_result.recommended_size
    assert "correlation" in str(result.warnings)

def test_size_validation():
    sizer = PositionSizer()

    # Valid size
    is_valid, issues = sizer.validate_size(
        position_size=0.1,
        entry_price=50000,
        stop_loss=49500,
        account_balance=10000
    )

    assert is_valid == True
    assert len(issues) == 0

    # Invalid: negative size
    is_valid, issues = sizer.validate_size(
        position_size=-0.1,
        entry_price=50000,
        stop_loss=49500,
        account_balance=10000
    )

    assert is_valid == False
    assert "positive" in issues[0]

    # Invalid: too high risk
    is_valid, issues = sizer.validate_size(
        position_size=1.0,  # Would be 5% risk
        entry_price=50000,
        stop_loss=49500,
        account_balance=10000,
        max_risk_percent=2.0
    )

    assert is_valid == False
    assert "exceeds maximum" in issues[0]

    # Invalid: too high leverage
    is_valid, issues = sizer.validate_size(
        position_size=0.5,  # 25000 position value
        entry_price=50000,
        stop_loss=49500,
        account_balance=1000,  # 25x leverage
        max_risk_percent=30.0  # Allow high risk for leverage test
    )

    assert is_valid == False
    # Both risk and leverage issues should be present
    assert len(issues) >= 1

def test_edge_cases():
    sizer = PositionSizer()

    # Zero balance
    result = sizer.calculate_size(
        account_balance=0,
        entry_price=50000,
        stop_loss=49500
    )

    assert result.recommended_size == 0
    assert len(result.warnings) > 0

    # Zero price risk
    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=50000
    )

    assert result.recommended_size == 0
    assert len(result.warnings) > 0

    # Very small size
    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49999,  # 1 point risk
        risk_percent=0.001  # Very small risk
    )

    assert result.recommended_size > 0
    # Size = (10000 * 0.001) / 1 = 0.1, which is reasonable
    assert result.recommended_size == 0.1

def test_result_to_dict():
    sizer = PositionSizer()

    result = sizer.calculate_size(
        account_balance=10000,
        entry_price=50000,
        stop_loss=49500
    )

    result_dict = result.to_dict()

    assert 'recommended_size' in result_dict
    assert 'max_size' in result_dict
    assert 'risk_amount' in result_dict
    assert 'position_value' in result_dict
    assert 'leverage_used' in result_dict
    assert 'sizing_method' in result_dict
    assert 'warnings' in result_dict

    # Check rounding
    assert isinstance(result_dict['recommended_size'], float)
    assert result_dict['recommended_size'] == round(result.recommended_size, 6)