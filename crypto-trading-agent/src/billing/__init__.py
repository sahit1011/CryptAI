"""Billing / subscription groundwork for the multi-tenant SaaS.

This package turns a subscription *tier* into the concrete per-user trading config the
multi-user engine already consumes (UserRiskConfig -> balance + RiskParameters). Wiring
tiers here means a plan change is a real change in what a tenant can do, and Stripe (or
any provider) only has to write a user's tier into the subscription source — see
plans.py for the integration seam.
"""
from src.billing.plans import (
    PLAN_TIERS,
    Plan,
    plan_config,
    plan_for_user,
    resolve_tier,
)

__all__ = ["PLAN_TIERS", "Plan", "plan_config", "plan_for_user", "resolve_tier"]
