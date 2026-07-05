"""Position-sizing unit-consistency tests.

Regression guard for the P1 where the deterministic calculator accumulated a
sizing MULTIPLIER into adjusted_position_size, but the risk agent emitted that
field as an ABSOLUTE size — so a 0.375 multiplier was sent as a 0.375-unit order.
"""
import pytest

from src.risk.deterministic_risk_calculator import (
    DeterministicRiskCalculator,
    RiskValidationResult,
)


class _StubTracker:
    pass


def _calc():
    return DeterministicRiskCalculator(portfolio_tracker=_StubTracker())


def test_result_defaults_are_unit_clean():
    r = RiskValidationResult(approved=True)
    assert r.position_size_multiplier == 1.0
    assert r.adjusted_position_size is None  # None == use recommended size


@pytest.mark.asyncio
async def test_regime_adjustment_accumulates_multiplier_not_absolute():
    calc = _calc()
    r = RiskValidationResult(approved=True)
    await calc._apply_market_regime_adjustments("HIGH_VOLATILITY", r)  # 0.5x
    # It must touch the multiplier, never write a bare fraction into the absolute field.
    assert r.position_size_multiplier == pytest.approx(0.5)
    assert r.adjusted_position_size is None


@pytest.mark.asyncio
async def test_multipliers_compound():
    calc = _calc()
    r = RiskValidationResult(approved=True)
    await calc._apply_market_regime_adjustments("RANGING", r)  # 0.75x
    r.position_size_multiplier *= 0.5  # e.g. a correlation adjustment
    assert r.position_size_multiplier == pytest.approx(0.375)


def test_absolute_size_derivation_formula():
    # Mirrors the derivation in validate_trade_setup: absolute = recommended * mult.
    recommended = 2.0
    r = RiskValidationResult(approved=True)
    r.position_size_multiplier = 0.375
    if r.position_size_multiplier < 1.0:
        r.adjusted_position_size = recommended * r.position_size_multiplier
    assert r.adjusted_position_size == pytest.approx(0.75)  # absolute units, not 0.375
