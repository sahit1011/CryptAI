"""
Unit tests for Risk-Reward Calculator
"""
import pytest
from src.strategy.risk_reward_calculator import RiskRewardCalculator, RiskRewardAnalysis

def test_calculator_initialization():
    calculator = RiskRewardCalculator()
    assert calculator is not None

def test_basic_rr_calculation():
    calculator = RiskRewardCalculator()

    tp_levels = [
        {'level': 1, 'price': 43500, 'size': 0.33},
        {'level': 2, 'price': 43800, 'size': 0.33},
        {'level': 3, 'price': 44200, 'size': 0.34}
    ]

    analysis = calculator.calculate(
        entry_price=43000,
        stop_loss=42750,
        take_profit_levels=tp_levels,
        win_rate_estimate=0.5,
        include_costs=False
    )

    assert isinstance(analysis, RiskRewardAnalysis)
    assert analysis.risk_amount > 0
    assert analysis.reward_amount > 0
    assert analysis.risk_reward_ratio >= 2.0
    assert analysis.expected_value != 0
    assert 0 <= analysis.break_even_win_rate <= 1.0
    assert len(analysis.optimized_tp_levels) == 3
    assert len(analysis.scenario_analysis) > 0

def test_rr_with_costs():
    calculator = RiskRewardCalculator()

    tp_levels = [
        {'level': 1, 'price': 43500, 'size': 0.33},
        {'level': 2, 'price': 43800, 'size': 0.33},
        {'level': 3, 'price': 44200, 'size': 0.34}
    ]

    analysis_no_costs = calculator.calculate(
        entry_price=43000,
        stop_loss=42750,
        take_profit_levels=tp_levels,
        include_costs=False
    )

    analysis_with_costs = calculator.calculate(
        entry_price=43000,
        stop_loss=42750,
        take_profit_levels=tp_levels,
        include_costs=True
    )

    # With costs, RR should be slightly lower
    assert analysis_with_costs.risk_reward_ratio < analysis_no_costs.risk_reward_ratio

def test_expected_value_calculation():
    calculator = RiskRewardCalculator()

    # Positive EV scenario
    ev_positive = calculator._calculate_expected_value(
        risk=250, reward=750, win_rate=0.6
    )
    assert ev_positive > 0

    # Negative EV scenario
    ev_negative = calculator._calculate_expected_value(
        risk=250, reward=250, win_rate=0.4
    )
    assert ev_negative < 0

def test_break_even_win_rate():
    calculator = RiskRewardCalculator()

    # 1:1 RR should require 50% win rate
    be_wr = calculator._calculate_break_even_win_rate(risk=250, reward=250)
    assert abs(be_wr - 0.5) < 0.01

    # 1:2 RR should require 33.3% win rate
    be_wr = calculator._calculate_break_even_win_rate(risk=250, reward=500)
    assert abs(be_wr - 0.333) < 0.01

def test_tp_optimization():
    calculator = RiskRewardCalculator()

    tp_levels = [
        {'level': 1, 'price': 43200, 'size': 0.33},  # 1:1.2 RR
        {'level': 2, 'price': 43500, 'size': 0.33},  # 1:2 RR
        {'level': 3, 'price': 44000, 'size': 0.34}   # 1:4 RR
    ]

    optimized = calculator._optimize_tp_levels(
        entry_price=43000,
        stop_loss=42750,
        tp_levels=tp_levels
    )

    assert len(optimized) == 3
    # TP1 should be optimized to at least 1.5:1
    assert optimized[0]['rr_ratio'] >= 1.5
    # TP2 should be optimized to at least 2.5:1
    assert optimized[1]['rr_ratio'] >= 2.5
    # TP3 should be optimized to at least 4:1
    assert optimized[2]['rr_ratio'] >= 4.0

def test_scenario_analysis():
    calculator = RiskRewardCalculator()

    tp_levels = [
        {'level': 1, 'price': 43500, 'size': 0.33},
        {'level': 2, 'price': 43800, 'size': 0.33},
        {'level': 3, 'price': 44200, 'size': 0.34}
    ]

    scenarios = calculator._run_scenario_analysis(
        entry_price=43000,
        stop_loss=42750,
        tp_levels=tp_levels,
        win_rate=0.5
    )

    required_scenarios = ['full_loss', 'tp1_only', 'tp1_tp2', 'all_tps', 'expected_outcome']
    for scenario in required_scenarios:
        assert scenario in scenarios

    # Full loss should be negative
    assert scenarios['full_loss'] < 0
    # All TPs should be positive
    assert scenarios['all_tps'] > 0

def test_minimum_rr_validation():
    calculator = RiskRewardCalculator()

    tp_levels = [
        {'level': 1, 'price': 43500, 'size': 0.33},
        {'level': 2, 'price': 43800, 'size': 0.33},
        {'level': 3, 'price': 44200, 'size': 0.34}
    ]

    # Should pass minimum 2.0 RR
    meets_req, actual_rr = calculator.validate_minimum_rr(
        entry_price=43000,
        stop_loss=42750,
        take_profit_levels=tp_levels,
        minimum_rr=2.0
    )

    assert meets_req == True
    assert actual_rr >= 2.0

    # Should fail minimum 4.0 RR (since actual is ~3.2)
    meets_req, actual_rr = calculator.validate_minimum_rr(
        entry_price=43000,
        stop_loss=42750,
        take_profit_levels=tp_levels,
        minimum_rr=4.0
    )

    assert meets_req == False
    assert actual_rr < 4.0

def test_position_risk_calculation():
    calculator = RiskRewardCalculator()

    risk_metrics = calculator.calculate_position_risk(
        entry_price=43000,
        stop_loss=42750,
        position_size=0.01,
        account_balance=10000
    )

    assert 'risk_per_unit' in risk_metrics
    assert 'total_risk_dollars' in risk_metrics
    assert 'risk_percentage' in risk_metrics
    assert 'position_value' in risk_metrics

    assert risk_metrics['risk_per_unit'] == 250.0  # 43000 - 42750
    assert risk_metrics['total_risk_dollars'] == 2.5  # 250 * 0.01
    assert risk_metrics['risk_percentage'] == 0.03  # 2.5 / 10000 * 100
    assert risk_metrics['position_value'] == 430.0  # 43000 * 0.01

def test_tp_adjustment():
    calculator = RiskRewardCalculator()

    # Long position
    new_tp = calculator.adjust_tp_for_better_rr(
        entry_price=43000,
        stop_loss=42750,
        current_tp=43500,
        target_rr=2.0
    )

    risk = 250  # 43000 - 42750
    expected_tp = 43000 + (risk * 2.0)  # 43250

    assert new_tp == expected_tp

    # Short position
    new_tp = calculator.adjust_tp_for_better_rr(
        entry_price=43000,
        stop_loss=43250,
        current_tp=42750,
        target_rr=2.0
    )

    risk = 250  # 43250 - 43000
    expected_tp = 43000 - (risk * 2.0)  # 42500

    assert new_tp == expected_tp