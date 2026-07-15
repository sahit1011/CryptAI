"""Subscription tiers -> per-user trading config.

A tenant's plan decides their starting balance, risk limits, and feature access. These
map directly onto the engine's `UserRiskConfig` (initial_balance + RiskParameters), so
the daemon's `config_for` can size every user by their plan instead of a hardcoded
default (see src/multi_user_daemon.py).

Tier resolution is pluggable and dependency-free today:
  1. per-user override from the `PLAN_OVERRIDES` env var (JSON: {"<user_id>": "pro"}),
  2. the global `DEFAULT_PLAN_TIER` env var (default: "free").

Stripe integration seam (later): a checkout webhook writes each user's active tier into
a `subscriptions` table; swap `resolve_tier` to read that table (keep the env fallback
for local/dev). Nothing else in the engine has to change — plans already flow into risk.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger

from src.core.multi_user import UserRiskConfig
from src.risk.deterministic_risk_calculator import RiskParameters


@dataclass(frozen=True)
class Plan:
    """A subscription tier and the trading limits it grants."""
    tier: str
    name: str
    price_usd_month: float
    initial_balance: float
    max_risk_per_trade: float          # fraction of balance risked per trade
    max_concurrent_positions: int
    max_daily_trades: int
    max_position_size_usd: float
    allow_live: bool                   # tier permits live keys (still globally gated)
    features: List[str] = field(default_factory=list)

    def to_risk_config(self) -> UserRiskConfig:
        """Concrete per-user engine config for this plan."""
        return UserRiskConfig(
            initial_balance=self.initial_balance,
            risk_params=RiskParameters(
                max_risk_per_trade=self.max_risk_per_trade,
                max_concurrent_positions=self.max_concurrent_positions,
                max_daily_trades=self.max_daily_trades,
                max_position_size_usd=self.max_position_size_usd,
            ),
        )


# The catalogue. Balances are paper sizing for testnet; real-money sizing is unlocked
# only when live trading is globally validated (LIVE_TRADING_CONFIRMED) AND the tier
# allows it. Keep tiers ordered free -> paid.
PLAN_TIERS: Dict[str, Plan] = {
    "free": Plan(
        tier="free", name="Free", price_usd_month=0.0,
        initial_balance=10_000.0, max_risk_per_trade=0.01,
        max_concurrent_positions=1, max_daily_trades=3,
        max_position_size_usd=2_000.0, allow_live=False,
        features=["Paper trading", "Live dashboard", "1 concurrent position"],
    ),
    "starter": Plan(
        tier="starter", name="Starter", price_usd_month=19.0,
        initial_balance=25_000.0, max_risk_per_trade=0.02,
        max_concurrent_positions=3, max_daily_trades=5,
        max_position_size_usd=10_000.0, allow_live=True,
        features=["Everything in Free", "Connect exchange (testnet)", "3 concurrent positions"],
    ),
    "pro": Plan(
        tier="pro", name="Pro", price_usd_month=79.0,
        initial_balance=100_000.0, max_risk_per_trade=0.03,
        max_concurrent_positions=8, max_daily_trades=20,
        max_position_size_usd=100_000.0, allow_live=True,
        features=["Everything in Starter", "8 concurrent positions", "Priority insights"],
    ),
}

DEFAULT_TIER = "free"


def resolve_tier(user_id: str, overrides: Optional[Dict[str, str]] = None) -> str:
    """The active subscription tier for a user.

    Order: explicit `overrides` arg, then PLAN_OVERRIDES env (JSON), then
    DEFAULT_PLAN_TIER env, then "free". Unknown tiers fall back to "free".
    Replace this with a `subscriptions` table read once Stripe is wired.
    """
    if overrides and user_id in overrides:
        tier = overrides[user_id]
    else:
        env_overrides: Dict[str, str] = {}
        raw = os.getenv("PLAN_OVERRIDES", "").strip()
        if raw:
            try:
                env_overrides = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("PLAN_OVERRIDES is not valid JSON; ignoring")
        tier = env_overrides.get(user_id) or os.getenv("DEFAULT_PLAN_TIER", DEFAULT_TIER)
    if tier not in PLAN_TIERS:
        logger.warning(f"Unknown plan tier '{tier}' for {user_id}; using '{DEFAULT_TIER}'")
        tier = DEFAULT_TIER
    return tier


def plan_for_user(user_id: str, overrides: Optional[Dict[str, str]] = None) -> Plan:
    """Resolve a user's Plan object."""
    return PLAN_TIERS[resolve_tier(user_id, overrides)]


def plan_config(user_id: str, overrides: Optional[Dict[str, str]] = None) -> UserRiskConfig:
    """The engine's per-user risk config for a user's current plan.

    This is what the daemon passes as `config_for`, so every tenant is sized by their
    subscription tier automatically.
    """
    return plan_for_user(user_id, overrides).to_risk_config()
