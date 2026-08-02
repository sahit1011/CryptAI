"""Preferences validation and the tighten-only risk rule.

SQLite-backed, no services. The load-bearing property is that nothing a user types can
widen a risk limit — preferences are an input to risk, never an override of it.
"""
import pytest

from src.core.preferences import (
    DEFAULTS,
    HARD_CAPS,
    PreferencesError,
    PreferencesStore,
    universe_for,
)

USER = "user-aaa"


@pytest.fixture
def store(tmp_path):
    return PreferencesStore(f"sqlite:///{tmp_path}/prefs.db")


# --- defaults ----------------------------------------------------------------

def test_an_unconfigured_user_gets_conservative_defaults(store):
    """Never opening the preferences screen must not mean maximum risk."""
    prefs = store.get(USER)
    assert prefs["max_risk_per_trade_pct"] == 1.0
    assert prefs["max_concurrent_positions"] == 1
    assert prefs["max_leverage"] == 3.0
    assert prefs["min_risk_reward"] >= 1.0


def test_defaults_are_below_every_hard_cap(store):
    for key, cap in HARD_CAPS.items():
        assert DEFAULTS[key] <= cap, f"default {key} exceeds its own hard cap"


# --- the tighten-only rule ---------------------------------------------------

def test_risk_cannot_be_widened_past_the_hard_cap(store):
    got = store.set(USER, {"max_risk_per_trade_pct": 50.0})
    assert got["max_risk_per_trade_pct"] == HARD_CAPS["max_risk_per_trade_pct"]


def test_every_risk_field_is_clamped(store):
    got = store.set(
        USER,
        {
            "max_risk_per_trade_pct": 99.0,
            "max_concurrent_positions": 999,
            "max_daily_trades": 999,
            "max_leverage": 125.0,
        },
    )
    for key, cap in HARD_CAPS.items():
        assert got[key] <= cap, f"{key} escaped its cap: {got[key]}"


def test_the_plan_cap_binds_when_tighter_than_the_hard_cap(store):
    got = store.set(
        USER,
        {"max_risk_per_trade_pct": 4.0, "max_concurrent_positions": 10},
        plan_caps={"max_risk_per_trade_pct": 1.0, "max_concurrent_positions": 3},
    )
    assert got["max_risk_per_trade_pct"] == 1.0
    assert got["max_concurrent_positions"] == 3


def test_the_hard_cap_binds_when_the_plan_is_more_permissive(store):
    """A misconfigured plan must not be able to authorise ruin."""
    got = store.set(
        USER,
        {"max_leverage": 100.0},
        plan_caps={"max_leverage": 500.0},
    )
    assert got["max_leverage"] == HARD_CAPS["max_leverage"]


def test_tightening_below_the_cap_is_always_allowed(store):
    got = store.set(USER, {"max_risk_per_trade_pct": 0.25, "max_leverage": 1.0})
    assert got["max_risk_per_trade_pct"] == 0.25
    assert got["max_leverage"] == 1.0


def test_integer_fields_stay_integers_after_clamping(store):
    got = store.set(USER, {"max_concurrent_positions": 999})
    assert isinstance(got["max_concurrent_positions"], int)


# --- validation --------------------------------------------------------------

def test_unknown_keys_are_rejected_not_ignored(store):
    """A silently dropped typo looks exactly like a setting that did not save."""
    with pytest.raises(PreferencesError, match="unknown preference"):
        store.set(USER, {"max_rissk_per_trade_pct": 1.0})


def test_enum_fields_are_validated(store):
    with pytest.raises(PreferencesError, match="risk_appetite"):
        store.set(USER, {"risk_appetite": "yolo"})
    with pytest.raises(PreferencesError, match="goal_horizon"):
        store.set(USER, {"goal_horizon": "forever"})


def test_risk_reward_below_one_is_rejected(store):
    """Below 1.0 the setup needs a >50% win rate just to break even before fees."""
    with pytest.raises(PreferencesError, match="min_risk_reward"):
        store.set(USER, {"min_risk_reward": 0.5})


def test_nonsensical_numbers_are_rejected(store):
    for updates, match in [
        ({"trading_capital": 0}, "trading_capital"),
        ({"trading_capital": -100}, "trading_capital"),
        ({"min_confidence": 1.5}, "min_confidence"),
        ({"max_concurrent_positions": 0}, "max_concurrent_positions"),
        ({"monthly_pnl_target_pct": -5}, "monthly_pnl_target_pct"),
    ]:
        with pytest.raises(PreferencesError, match=match):
            store.set(USER, updates)


def test_an_empty_universe_is_rejected(store):
    """An empty list would scan nothing while looking configured."""
    with pytest.raises(PreferencesError, match="cannot be empty"):
        store.set(USER, {"symbol_universe": []})


def test_universe_is_normalised_to_uppercase(store):
    got = store.set(USER, {"symbol_universe": ["btcusdt", "EthUsdt"]})
    assert got["symbol_universe"] == ["BTCUSDT", "ETHUSDT"]


def test_goal_notes_are_truncated_not_rejected(store):
    got = store.set(USER, {"goal_notes": "x" * 5000})
    assert len(got["goal_notes"]) == 500


# --- persistence -------------------------------------------------------------

def test_updates_are_partial_and_persist(store):
    store.set(USER, {"risk_appetite": "aggressive"})
    store.set(USER, {"trading_capital": 50_000.0})
    got = store.get(USER)
    assert got["risk_appetite"] == "aggressive", "second write clobbered the first"
    assert got["trading_capital"] == 50_000.0
    assert got["max_concurrent_positions"] == DEFAULTS["max_concurrent_positions"]


def test_preferences_are_isolated_between_users(store):
    store.set(USER, {"trading_capital": 99_000.0})
    assert store.get("user-bbb")["trading_capital"] == DEFAULTS["trading_capital"]


# --- universe resolution -----------------------------------------------------

def test_null_universe_means_platform_default_not_nothing(store):
    """An empty scan is indistinguishable from a broken engine on the dashboard."""
    prefs = store.get(USER)
    assert universe_for(prefs, ["BTCUSDT", "ETHUSDT"]) == ["BTCUSDT", "ETHUSDT"]


def test_an_explicit_universe_overrides_the_default(store):
    prefs = store.set(USER, {"symbol_universe": ["SOLUSDT"]})
    assert universe_for(prefs, ["BTCUSDT", "ETHUSDT"]) == ["SOLUSDT"]
