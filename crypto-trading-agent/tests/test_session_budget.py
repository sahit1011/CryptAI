"""LLM spend metering — the thing that makes the session cost cap real.

The load-bearing property is the unknown-model fallback: charging zero for a model
missing from the pricing table would let any unbudgeted model bypass the cap entirely.
"""
import json
from datetime import datetime, timedelta

import pytest

from src.core.session_budget import (
    ANTHROPIC_PRICING,
    UNKNOWN_MODEL_PRICING,
    SessionBudget,
    cost_micros,
    pricing_for,
)
from src.core.session_manager import ENDED, SessionManager

USER = "user-aaa"
START = datetime(2026, 8, 2, 10, 0, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def mgr(tmp_path, clock):
    return SessionManager(
        f"sqlite:///{tmp_path}/s.db",
        daily_quota_seconds=1800,
        cost_cap_micros=500_000,
        now_fn=clock,
    )


# --- pricing ------------------------------------------------------------------

def test_known_models_price_from_the_table():
    assert pricing_for("claude-opus-5") == ANTHROPIC_PRICING["claude-opus-5"]
    assert pricing_for("claude-haiku-4-5").input_per_mtok == 1.0


def test_an_unknown_model_is_charged_the_expensive_fallback_not_zero():
    """THE property. Zero-rating an unknown model disables the cap for it entirely."""
    price = pricing_for("some-new-provider/mystery-model")
    assert price == UNKNOWN_MODEL_PRICING
    assert price.input_per_mtok > 0 and price.output_per_mtok > 0

    charged = cost_micros("some-new-provider/mystery-model", 1_000_000, 1_000_000)
    assert charged > 0, "an unknown model was billed nothing"
    # At least as expensive as the priciest known model, so it can't be a cheap bypass.
    priciest = max(p.output_per_mtok for p in ANTHROPIC_PRICING.values())
    assert UNKNOWN_MODEL_PRICING.output_per_mtok >= priciest


def test_a_dated_snapshot_inherits_its_family_price(monkeypatch):
    """Otherwise every dated model ID silently falls to the expensive fallback."""
    monkeypatch.delenv("LLM_PRICING_OVERRIDES", raising=False)
    assert pricing_for("claude-opus-5-20260101") == ANTHROPIC_PRICING["claude-opus-5"]


def test_env_overrides_win_over_the_builtin_table(monkeypatch):
    """A price change must not require a deploy."""
    monkeypatch.setenv(
        "LLM_PRICING_OVERRIDES", json.dumps({"claude-opus-5": {"input": 99.0, "output": 199.0}})
    )
    assert pricing_for("claude-opus-5").input_per_mtok == 99.0


def test_a_malformed_override_is_ignored_not_fatal(monkeypatch):
    """A bad env var must not take the engine down; the built-in table still bounds spend."""
    monkeypatch.setenv("LLM_PRICING_OVERRIDES", "{not json")
    assert pricing_for("claude-opus-5") == ANTHROPIC_PRICING["claude-opus-5"]

    monkeypatch.setenv("LLM_PRICING_OVERRIDES", json.dumps({"claude-opus-5": {"in": 1}}))
    assert pricing_for("claude-opus-5") == ANTHROPIC_PRICING["claude-opus-5"]


# --- cost arithmetic ----------------------------------------------------------

def test_cost_matches_the_published_rate(monkeypatch):
    monkeypatch.delenv("LLM_PRICING_OVERRIDES", raising=False)
    # Opus 5: $5 per Mtok in, $25 out. 1M + 1M = $30.00 = 30_000_000 micros.
    assert cost_micros("claude-opus-5", 1_000_000, 1_000_000) == 30_000_000


def test_cache_reads_are_charged_at_a_tenth(monkeypatch):
    """Otherwise a caching-heavy workload trips the cap far too early — exactly the
    workloads caching exists to help."""
    monkeypatch.delenv("LLM_PRICING_OVERRIDES", raising=False)
    fresh = cost_micros("claude-opus-5", 1_000_000, 0)
    cached = cost_micros("claude-opus-5", 0, 0, cache_read_tokens=1_000_000)
    assert cached == pytest.approx(fresh * 0.1, rel=1e-6)


def test_cache_writes_carry_their_premium(monkeypatch):
    monkeypatch.delenv("LLM_PRICING_OVERRIDES", raising=False)
    fresh = cost_micros("claude-opus-5", 1_000_000, 0)
    written = cost_micros("claude-opus-5", 0, 0, cache_write_tokens=1_000_000)
    assert written == pytest.approx(fresh * 1.25, rel=1e-6)


def test_a_tiny_call_costs_at_least_one_micro(monkeypatch):
    """Rounding down to zero would make a tight loop of small calls free forever."""
    monkeypatch.delenv("LLM_PRICING_OVERRIDES", raising=False)
    assert cost_micros("claude-haiku-4-5", 1, 1) >= 1


def test_zero_usage_costs_nothing():
    assert cost_micros("claude-opus-5", 0, 0) == 0


def test_negative_and_none_token_counts_are_clamped():
    """A provider returning junk must not produce a negative charge that refunds budget."""
    assert cost_micros("claude-opus-5", -5000, None) == 0
    assert cost_micros("claude-opus-5", None, -1) == 0


# --- SessionBudget ------------------------------------------------------------

def test_recording_advances_the_session_meter(mgr):
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    state = budget.record("claude-opus-5", input_tokens=10_000, output_tokens=2_000)
    assert state["llm_cost_micros"] > 0
    assert state["llm_tokens_used"] == 12_000


def test_spending_past_the_cap_ends_the_session(mgr):
    """The whole point: the cap previously guarded a number nothing wrote to."""
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    state = budget.record("claude-opus-5", input_tokens=0, output_tokens=1_000_000)
    assert state["status"] == ENDED
    assert state["end_reason"] == "cost_cap"


def test_can_spend_is_false_once_the_session_ends(mgr):
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    assert budget.can_spend() is True
    mgr.end(s["session_id"])
    assert budget.can_spend() is False


def test_can_spend_enforces_the_clock_too(mgr, clock):
    """Checking before every call means time cannot overrun by more than one cycle."""
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    clock.advance(1801)
    assert budget.can_spend() is False
    assert mgr.get(s["session_id"])["end_reason"] == "quota_exhausted"


def test_can_spend_fails_closed_on_a_broken_session(mgr):
    budget = SessionBudget(mgr, "does-not-exist")
    assert budget.can_spend() is False, "a missing session was treated as spendable"


def test_record_response_reads_an_sdk_usage_object(mgr):
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])

    class Usage:
        input_tokens = 1_000
        output_tokens = 500
        cache_read_input_tokens = 4_000
        cache_creation_input_tokens = 200

    state = budget.record_response("claude-opus-5", Usage())
    assert state["llm_tokens_used"] == 5_700
    assert state["llm_cost_micros"] > 0


def test_record_response_tolerates_missing_cache_fields(mgr):
    """A provider omitting a field must degrade to zero for that component, not raise
    inside the metering path and lose the entire charge."""
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])

    class Sparse:
        input_tokens = 1_000
        output_tokens = 100

    state = budget.record_response("claude-opus-5", Sparse())
    assert state["llm_tokens_used"] == 1_100
    assert state["llm_cost_micros"] > 0


def test_record_response_accepts_a_plain_dict(mgr):
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    state = budget.record_response(
        "claude-opus-5", {"input_tokens": 100, "output_tokens": 50}
    )
    assert state["llm_tokens_used"] == 150


def test_an_unknown_model_still_charges_the_session(mgr):
    """End-to-end version of the fallback property: adding a provider must not silently
    disable the cap for it."""
    s = mgr.start(USER)
    budget = SessionBudget(mgr, s["session_id"])
    state = budget.record("mystery/model-x", input_tokens=0, output_tokens=1_000_000)
    assert state["status"] == ENDED
    assert state["end_reason"] == "cost_cap"
