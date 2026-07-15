"""Subscription tiers -> per-user engine config."""
from src.billing import PLAN_TIERS, plan_config, plan_for_user, resolve_tier


def test_free_is_the_default_and_conservative():
    cfg = plan_config("someone")
    assert cfg.initial_balance == 10_000.0
    assert cfg.risk_params.max_concurrent_positions == 1  # free = 1 position


def test_explicit_override_selects_tier():
    assert resolve_tier("u1", {"u1": "pro"}) == "pro"
    cfg = plan_config("u1", {"u1": "pro"})
    assert cfg.initial_balance == 100_000.0
    assert cfg.risk_params.max_concurrent_positions == 8


def test_unknown_tier_falls_back_to_free():
    assert resolve_tier("u1", {"u1": "enterprise-galaxy"}) == "free"


def test_paid_tiers_scale_up_monotonically():
    free, starter, pro = (PLAN_TIERS[t] for t in ("free", "starter", "pro"))
    assert free.initial_balance < starter.initial_balance < pro.initial_balance
    assert free.max_concurrent_positions < starter.max_concurrent_positions < pro.max_concurrent_positions
    assert not free.allow_live and starter.allow_live and pro.allow_live


def test_plan_maps_to_real_risk_parameters():
    plan = plan_for_user("u", {"u": "starter"})
    cfg = plan.to_risk_config()
    assert cfg.risk_params.max_risk_per_trade == plan.max_risk_per_trade
    assert cfg.risk_params.max_daily_trades == plan.max_daily_trades
    assert cfg.risk_params.max_position_size_usd == plan.max_position_size_usd
