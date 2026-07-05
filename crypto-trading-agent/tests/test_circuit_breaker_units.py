"""Circuit breaker unit-consistency tests.

Regression guard for the P0 where the breaker received display percentages
(heat/drawdown * 100) but compared them against fractions (0.08 / 0.20), so it
tripped on ~0.08% heat and halted all trading.
"""
from datetime import datetime

from src.risk.circuit_breaker import CircuitBreaker
from src.risk.portfolio_state_tracker import PortfolioSnapshot


def test_normal_risk_does_not_trip():
    cb = CircuitBreaker()
    snap = PortfolioSnapshot(
        timestamp=datetime(2026, 1, 1),
        account_balance=10000, total_equity=10000,
        portfolio_heat=0.05,        # 5% — under the 8% extreme-heat limit
        current_drawdown=0.10,      # 10% — under the 20% limit
        daily_pnl=-100.0,           # -1% of 10k — under the 5% daily-loss limit
        daily_start_equity=10000.0,
        loss_streak=0,
    )
    should_trigger, conditions = cb.check_conditions(snap.to_risk_dict())
    assert should_trigger is False, f"unexpectedly tripped: {conditions}"


def test_extreme_heat_trips_only_above_fraction_threshold():
    cb = CircuitBreaker()
    snap = PortfolioSnapshot(
        timestamp=datetime(2026, 1, 1),
        account_balance=10000, total_equity=10000,
        portfolio_heat=0.09,        # 9% > 8% -> should trip
        current_drawdown=0.0,
        daily_pnl=0.0, daily_start_equity=10000.0, loss_streak=0,
    )
    should_trigger, conditions = cb.check_conditions(snap.to_risk_dict())
    assert should_trigger is True
    assert any("heat" in c.lower() for c in conditions)


def test_daily_loss_uses_real_equity_not_hardcoded_10k():
    cb = CircuitBreaker()
    # On a 1000-equity account, a $60 loss is 6% (> 5% limit) and must trip.
    # With the old hardcoded $10k fallback it would read as 0.6% and never trip.
    snap = PortfolioSnapshot(
        timestamp=datetime(2026, 1, 1),
        account_balance=1000, total_equity=940,
        portfolio_heat=0.0, current_drawdown=0.0,
        daily_pnl=-60.0, daily_start_equity=1000.0, loss_streak=0,
    )
    should_trigger, conditions = cb.check_conditions(snap.to_risk_dict())
    assert should_trigger is True
    assert any("daily" in c.lower() for c in conditions)
