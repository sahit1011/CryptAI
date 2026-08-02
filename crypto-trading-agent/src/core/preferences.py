"""Per-user trading preferences — the persona that parameterises a user's agents.

Distinct from `UserSettingsStore`, which holds operational flags (mode, exchange,
onboarded) read by the daemon every cycle. Preferences are the richer, faster-evolving
set read once per SESSION to drive universe selection, sizing, filtering, and ranking.

# Preferences may only ever TIGHTEN risk

This is the rule that matters here. A user's stated risk appetite, and a stretch monthly
PnL target, must never widen a limit above what their plan allows. Every risk field is
clamped against the plan ceiling on write, so a user who types 50% risk-per-trade gets
their plan's cap instead — silently in the value, loudly in the log.

The direction is deliberate: preferences are an input to risk, never an override of it.
The deterministic risk engine downstream can shrink exposure further; nothing in this
path can grow it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.data_models import UserPreferences

RISK_APPETITES = ("conservative", "moderate", "aggressive")
GOAL_HORIZONS = ("scalp", "intraday", "swing", "position")

#: Absolute ceilings, independent of plan. A plan can be more restrictive; nothing can
#: be more permissive. These exist so a misconfigured plan cannot authorise ruin.
HARD_CAPS = {
    "max_risk_per_trade_pct": 5.0,
    "max_concurrent_positions": 20,
    "max_daily_trades": 50,
    "max_leverage": 20.0,
}

#: What a brand-new user gets: the most conservative setting in every dimension. A user
#: who never opens the preferences screen must not thereby be taking maximum risk.
DEFAULTS: Dict[str, Any] = {
    "trading_capital": 10_000.0,
    "capital_currency": "USDT",
    "risk_appetite": "moderate",
    "max_risk_per_trade_pct": 1.0,
    "max_concurrent_positions": 1,
    "max_daily_trades": 3,
    "max_leverage": 3.0,
    "monthly_pnl_target_pct": None,
    "goal_horizon": "swing",
    "goal_notes": None,
    "symbol_universe": None,
    "allowed_strategies": None,
    "min_risk_reward": 1.5,
    "min_confidence": 0.6,
    "avoid_high_funding": True,
}


class PreferencesError(ValueError):
    """Invalid preference input."""


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class PreferencesStore:
    """CRUD for per-user trading preferences.

    Synchronous, matching `UserSettingsStore` and `CredentialVault`.
    """

    def __init__(self, database_url: str):
        from src.utils.db import pool_kwargs

        self.engine = create_engine(database_url, **pool_kwargs())
        UserPreferences.__table__.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)

    # -- read ----------------------------------------------------------------

    def get(self, user_id: str) -> Dict[str, Any]:
        """A user's preferences, falling back to conservative defaults.

        Absence is not an error: a user who has never opened the preferences screen is
        fully functional on the defaults.
        """
        db = self.Session()
        try:
            row = db.query(UserPreferences).filter_by(user_id=user_id).first()
            if row is None:
                return {"user_id": user_id, **DEFAULTS}
            return self._to_dict(row)
        finally:
            db.close()

    # -- write ---------------------------------------------------------------

    def set(
        self,
        user_id: str,
        updates: Dict[str, Any],
        plan_caps: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Upsert preferences. Unknown keys are rejected; risk fields are clamped.

        `plan_caps` is the user's subscription ceiling (see `src.billing.plans`). Risk
        fields are clamped to the tighter of the plan cap and the hard cap, so a plan
        upgrade widens what is available but a preference can never exceed either.
        """
        clean = self._validate(updates)
        clean = self._clamp_risk(user_id, clean, plan_caps or {})

        db = self.Session()
        try:
            row = db.query(UserPreferences).filter_by(user_id=user_id).first()
            if row is None:
                row = UserPreferences(user_id=user_id, **DEFAULTS)
                db.add(row)
            for key, value in clean.items():
                setattr(row, key, value)
            db.commit()
            db.refresh(row)
            logger.info(f"preferences updated for {user_id}: {sorted(clean)}")
            return self._to_dict(row)
        finally:
            db.close()

    # -- validation ----------------------------------------------------------

    def _validate(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        unknown = set(updates) - set(DEFAULTS)
        if unknown:
            # Rejected rather than ignored: a typo'd key that is silently dropped looks
            # to the user exactly like a setting that did not take effect.
            raise PreferencesError(f"unknown preference keys: {sorted(unknown)}")

        clean: Dict[str, Any] = {}
        for key, value in updates.items():
            if key == "risk_appetite":
                if value not in RISK_APPETITES:
                    raise PreferencesError(
                        f"risk_appetite must be one of {RISK_APPETITES}, got {value!r}"
                    )
            elif key == "goal_horizon":
                if value not in GOAL_HORIZONS:
                    raise PreferencesError(
                        f"goal_horizon must be one of {GOAL_HORIZONS}, got {value!r}"
                    )
            elif key == "trading_capital":
                value = float(value)
                if value <= 0:
                    raise PreferencesError("trading_capital must be positive")
            elif key == "min_risk_reward":
                value = float(value)
                # Below 1.0 the setup needs a >50% win rate just to break even before
                # fees. Allowing it invites a user to configure themselves into a loss.
                if value < 1.0:
                    raise PreferencesError("min_risk_reward must be at least 1.0")
            elif key == "min_confidence":
                value = float(value)
                if not 0.0 <= value <= 1.0:
                    raise PreferencesError("min_confidence must be between 0 and 1")
            elif key == "monthly_pnl_target_pct":
                if value is not None:
                    value = float(value)
                    if value <= 0:
                        raise PreferencesError("monthly_pnl_target_pct must be positive")
            elif key in ("max_concurrent_positions", "max_daily_trades"):
                value = int(value)
                if value < 1:
                    raise PreferencesError(f"{key} must be at least 1")
            elif key in ("max_risk_per_trade_pct", "max_leverage"):
                value = float(value)
                if value <= 0:
                    raise PreferencesError(f"{key} must be positive")
            elif key == "symbol_universe":
                if value is not None:
                    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
                        raise PreferencesError("symbol_universe must be a list of strings")
                    value = [s.upper() for s in value]
                    if not value:
                        # An empty list would scan nothing while looking configured.
                        raise PreferencesError("symbol_universe cannot be empty; use null for the default")
            elif key == "allowed_strategies":
                if value is not None and not isinstance(value, list):
                    raise PreferencesError("allowed_strategies must be a list or null")
            elif key == "avoid_high_funding":
                value = bool(value)
            elif key == "goal_notes":
                if value is not None:
                    value = str(value)[:500]
            elif key == "capital_currency":
                value = str(value).upper()[:8]

            clean[key] = value
        return clean

    def _clamp_risk(
        self, user_id: str, clean: Dict[str, Any], plan_caps: Dict[str, float]
    ) -> Dict[str, Any]:
        """Clamp every risk field to the tighter of plan cap and hard cap.

        Logged loudly when it bites: a silently reduced limit is indistinguishable to the
        user from one that saved correctly, and they will size their expectations wrong.
        """
        for key, hard in HARD_CAPS.items():
            if key not in clean:
                continue
            ceiling = min(hard, float(plan_caps.get(key, hard)))
            requested = clean[key]
            capped = _clamp(float(requested), 0.0, ceiling)
            if capped != float(requested):
                logger.warning(
                    f"{user_id}: {key}={requested} exceeds ceiling {ceiling}; clamped. "
                    f"Preferences may only tighten risk, never widen it."
                )
            clean[key] = int(capped) if isinstance(requested, int) else capped
        return clean

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _to_dict(row: UserPreferences) -> Dict[str, Any]:
        return {
            "user_id": row.user_id,
            "trading_capital": row.trading_capital,
            "capital_currency": row.capital_currency,
            "risk_appetite": row.risk_appetite,
            "max_risk_per_trade_pct": row.max_risk_per_trade_pct,
            "max_concurrent_positions": row.max_concurrent_positions,
            "max_daily_trades": row.max_daily_trades,
            "max_leverage": row.max_leverage,
            "monthly_pnl_target_pct": row.monthly_pnl_target_pct,
            "goal_horizon": row.goal_horizon,
            "goal_notes": row.goal_notes,
            "symbol_universe": row.symbol_universe,
            "allowed_strategies": row.allowed_strategies,
            "min_risk_reward": row.min_risk_reward,
            "min_confidence": row.min_confidence,
            "avoid_high_funding": bool(row.avoid_high_funding),
        }


def universe_for(prefs: Dict[str, Any], platform_default: List[str]) -> List[str]:
    """Symbols to scan for this user.

    A null universe means "the platform default", not "nothing" — the distinction matters
    because an empty scan looks identical to a broken engine from the dashboard.
    """
    chosen = prefs.get("symbol_universe")
    return list(chosen) if chosen else list(platform_default)
