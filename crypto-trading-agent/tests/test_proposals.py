"""Deterministic sizing, shelf life, and approval-time re-validation.

This is the layer LLM output passes through before it can become an order, so every test
here is about what the arithmetic refuses to do. No LLM involved; the clock is injected.
"""
from datetime import datetime, timedelta

import pytest

from src.core.proposals import (
    EXPIRED,
    INVALIDATED,
    PROPOSED,
    REASON_BAD_GEOMETRY,
    REASON_CONFIDENCE_LOW,
    REASON_EXPIRED,
    REASON_INVALIDATED,
    REASON_PRICE_MOVED,
    REASON_RR_DEGRADED,
    ProposalService,
    size_position,
)

ALICE = "user-alice"
BOB = "user-bob"
SESSION = "sess-1"
START = datetime(2026, 8, 2, 10, 0, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


PREFS = {
    "trading_capital": 10_000.0,
    "capital_currency": "USDT",
    "max_risk_per_trade_pct": 1.0,
    "max_leverage": 3.0,
    "min_risk_reward": 1.5,
    "min_confidence": 0.6,
}

# LONG 100, stop 95 (5 wide), target 110 (10 wide) -> R:R 2.0
SETUP = {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 100.0,
    "stop_loss": 95.0,
    "take_profit_levels": [110.0, 120.0],
    "confidence_score": 0.8,
    "thesis": "clean pullback into demand",
}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def svc(tmp_path, clock):
    return ProposalService(f"sqlite:///{tmp_path}/p.db", ttl_seconds=180, now_fn=clock)


# --- sizing arithmetic --------------------------------------------------------

def test_size_comes_from_the_users_own_risk_budget():
    """$10k at 1% = $100 risk; a $5 stop distance means 20 units."""
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=95.0,
        take_profits=[110.0], prefs=PREFS,
    )
    assert r.ok
    assert r.risk_amount == 100.0
    assert r.position_size == pytest.approx(20.0)
    assert r.risk_reward_ratio == pytest.approx(2.0)


def test_leverage_caps_the_notional():
    """Without the cap, a tight stop produces an enormous position for the same risk."""
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=99.9,  # 0.1 wide
        take_profits=[100.5], prefs={**PREFS, "min_risk_reward": 1.0},
    )
    assert r.ok
    # 3x leverage on $10k = $30k notional ceiling.
    assert r.notional <= 30_000.0 + 1e-6


def test_a_stop_on_the_wrong_side_is_refused():
    """Not a rounding problem — the position would stop out on entry."""
    long_bad = size_position(
        direction="LONG", entry_price=100.0, stop_loss=105.0,
        take_profits=[110.0], prefs=PREFS,
    )
    short_bad = size_position(
        direction="SHORT", entry_price=100.0, stop_loss=95.0,
        take_profits=[90.0], prefs=PREFS,
    )
    assert not long_bad.ok and long_bad.reason == REASON_BAD_GEOMETRY
    assert not short_bad.ok and short_bad.reason == REASON_BAD_GEOMETRY


def test_a_target_on_the_wrong_side_is_refused():
    """The 'profit' leg would be a loss."""
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=95.0,
        take_profits=[90.0], prefs=PREFS,
    )
    assert not r.ok and r.reason == REASON_BAD_GEOMETRY


def test_risk_reward_uses_the_FIRST_target():
    """The nearest target is the one most likely to be reached. Using the furthest
    flatters every setup — 100/95 with targets [101, 200] is not a 20R trade."""
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=95.0,
        take_profits=[101.0, 200.0], prefs=PREFS,
    )
    assert not r.ok, "R:R was computed from the furthest target"
    assert r.reason == REASON_RR_DEGRADED


def test_a_setup_below_the_users_min_rr_is_refused():
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=95.0,
        take_profits=[105.0], prefs=PREFS,  # 1.0 R:R vs min 1.5
    )
    assert not r.ok and r.reason == REASON_RR_DEGRADED


def test_shorts_size_correctly():
    r = size_position(
        direction="SHORT", entry_price=100.0, stop_loss=105.0,
        take_profits=[90.0], prefs=PREFS,
    )
    assert r.ok
    assert r.position_size == pytest.approx(20.0)
    assert r.risk_reward_ratio == pytest.approx(2.0)


def test_zero_or_missing_capital_is_refused():
    for bad in ({**PREFS, "trading_capital": 0}, {**PREFS, "max_risk_per_trade_pct": 0}):
        r = size_position(
            direction="LONG", entry_price=100.0, stop_loss=95.0,
            take_profits=[110.0], prefs=bad,
        )
        assert not r.ok


def test_no_targets_is_refused():
    r = size_position(
        direction="LONG", entry_price=100.0, stop_loss=95.0,
        take_profits=[], prefs=PREFS,
    )
    assert not r.ok and r.reason == REASON_BAD_GEOMETRY


# --- creation -----------------------------------------------------------------

def test_a_valid_setup_becomes_a_proposal(svc):
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    assert p is not None
    assert p["status"] == PROPOSED
    assert p["position_size"] == pytest.approx(20.0)
    assert p["invalidation_price"] == 95.0
    assert p["expires_at"] is not None


def test_a_setup_violating_the_users_rules_is_dropped(svc):
    """An LLM producing a setup that breaks the user's own risk rules gets it dropped
    here, not surfaced for approval."""
    bad_rr = {**SETUP, "take_profit_levels": [102.0]}
    assert svc.create(user_id=ALICE, session_id=SESSION, setup=bad_rr, prefs=PREFS) is None


def test_low_confidence_is_dropped(svc):
    shy = {**SETUP, "confidence_score": 0.2}
    assert svc.create(user_id=ALICE, session_id=SESSION, setup=shy, prefs=PREFS) is None


def test_confidence_gate_uses_the_users_threshold(svc):
    shy = {**SETUP, "confidence_score": 0.3}
    relaxed = {**PREFS, "min_confidence": 0.1}
    assert svc.create(user_id=ALICE, session_id=SESSION, setup=shy, prefs=relaxed) is not None


def test_sizing_reflects_the_individual_users_capital(svc):
    """Same setup, different users, different sizes — the point of per-user synthesis."""
    rich = svc.create(
        user_id=ALICE, session_id=SESSION, setup=SETUP,
        prefs={**PREFS, "trading_capital": 100_000.0},
    )
    poor = svc.create(
        user_id=BOB, session_id=SESSION, setup=SETUP,
        prefs={**PREFS, "trading_capital": 1_000.0},
    )
    assert rich["position_size"] > poor["position_size"] * 50


# --- shelf life ---------------------------------------------------------------

def test_a_pending_proposal_is_readable(svc):
    svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    assert svc.get_pending(ALICE)["status"] == PROPOSED


def test_expiry_is_evaluated_on_read(svc, clock):
    """Otherwise a proposal is approvable in the gap between lapsing and the sweep."""
    svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    clock.advance(181)
    assert svc.get_pending(ALICE)["status"] == EXPIRED


def test_the_sweeper_expires_stale_proposals(svc, clock):
    svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    clock.advance(181)
    assert svc.expire_stale() == 1
    assert svc.expire_stale() == 0


# --- re-validation: the money-safety core -------------------------------------

def test_approving_at_the_proposed_price_is_allowed(svc):
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=100.0, prefs=PREFS
    )
    assert r.ok
    assert r.position_size == pytest.approx(20.0)


def test_approving_an_expired_proposal_is_refused(svc, clock):
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    clock.advance(181)
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=100.0, prefs=PREFS
    )
    assert not r.ok and r.reason == REASON_EXPIRED


def test_price_beyond_the_invalidation_level_is_refused(svc):
    """Price already reached where the thesis says the trade was wrong."""
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=94.0, prefs=PREFS
    )
    assert not r.ok and r.reason == REASON_INVALIDATED
    assert svc.get(p["proposal_id"], ALICE)["status"] == INVALIDATED


def test_price_drifting_past_tolerance_is_refused(svc):
    """A setup priced at 100 is a different trade at 103."""
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=103.0, prefs=PREFS
    )
    assert not r.ok and r.reason == REASON_PRICE_MOVED


def test_resizing_never_grows_the_position(svc):
    """THE rule. Price drifting toward the stop shrinks the stop distance, and naive
    risk-neutral re-sizing would then demand a LARGER position for the same nominal
    risk — same risk on paper, several times the gap exposure.
    """
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    original = p["position_size"]

    # 99.6 is inside tolerance but closer to the 95 stop: distance 4.6 instead of 5.0,
    # so the risk-neutral size would be ~21.7 vs the original 20.
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=99.6, prefs=PREFS
    )
    assert r.ok
    assert r.position_size <= original + 1e-9, "re-sizing grew the position"


def test_favourable_drift_shrinks_the_position(svc):
    """Price away from the stop widens the distance, so the same risk buys less size."""
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=100.4, prefs=PREFS
    )
    assert r.ok
    assert r.position_size < p["position_size"]
    assert r.resized is True


def test_revalidation_rechecks_risk_reward_at_the_live_price(svc):
    """Drift toward the target degrades R:R; a setup that no longer clears the user's
    minimum must not be approved just because it did when proposed."""
    tight = {**SETUP, "take_profit_levels": [107.6]}  # R:R 1.52 at entry, just over 1.5
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=tight, prefs=PREFS)
    assert p is not None
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=100.4, prefs=PREFS
    )
    assert not r.ok and r.reason == REASON_RR_DEGRADED


def test_an_already_decided_proposal_cannot_be_revalidated(svc):
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    svc.mark(p["proposal_id"], "executed", trade_id="t-1")
    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=ALICE, current_price=100.0, prefs=PREFS
    )
    assert not r.ok


# --- tenancy ------------------------------------------------------------------

def test_a_proposal_id_from_another_tenant_does_not_resolve(svc):
    """The backend bypasses RLS, so application-layer scoping is the only guard."""
    p = svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    assert svc.get(p["proposal_id"], BOB) is None

    r = svc.revalidate(
        proposal_id=p["proposal_id"], user_id=BOB, current_price=100.0, prefs=PREFS
    )
    assert not r.ok, "another tenant re-validated a proposal that is not theirs"


def test_pending_lookups_are_per_user(svc):
    svc.create(user_id=ALICE, session_id=SESSION, setup=SETUP, prefs=PREFS)
    assert svc.get_pending(BOB) is None
