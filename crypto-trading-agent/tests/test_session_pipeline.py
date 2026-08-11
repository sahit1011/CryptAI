"""The session pipeline: metered cycles produce per-user proposals and pause the clock.

This is the M2 wiring test — the exact gap the audit flagged as "a session that meters
time runs zero analysis." Real SessionManager/PreferencesStore/ProposalService over
SQLite, injected clock, no Redis, no LLM (the analyze_fn under test IS the production
one; its inputs are the shared-setup cache and preferences).
"""
from datetime import datetime, timedelta

import pytest

from src.core.preferences import PreferencesStore
from src.core.proposals import ProposalService
from src.core.session_manager import SCANNING, SETUP_PROPOSED, SessionManager
from src.core.session_pipeline import (
    CHANNEL_MIN_RR,
    SharedSetupCache,
    build_analyze_fn,
    effective_prefs_for_channel,
)
from src.core.session_worker import (
    CYCLE_RAN,
    CYCLE_SKIPPED_NOT_SCANNING,
    SessionWorker,
)

START = datetime(2026, 8, 2, 10, 0, 0)
USER = "user-aaa"

SHARED_SETUP = {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 64000.0,
    "stop_loss": 62000.0,
    # Deliberately the daemon's dict shape — the pipeline must normalize it.
    "take_profit_levels": [{"price": 68000.0, "size": 1.0}],
    "confidence_score": 0.72,
    "strategy_type": "SWING",
    "thesis": "HTF bias long, pullback to demand",
}


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
def stores(tmp_path, clock):
    mgr = SessionManager(
        f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock
    )
    prefs = PreferencesStore(f"sqlite:///{tmp_path}/p.db")
    proposals = ProposalService(f"sqlite:///{tmp_path}/pr.db", now_fn=clock)
    cache = SharedSetupCache()
    return mgr, prefs, proposals, cache


def _worker(stores, session):
    mgr, prefs, proposals, cache = stores
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )
    return SessionWorker(mgr, prefs, session, analyze)


@pytest.mark.asyncio
async def test_a_metered_cycle_creates_a_proposal_and_pauses_the_clock(stores, clock):
    """The core M2 promise: a session that meters time does real work, and the clock
    stops while the user deliberates."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    worker = _worker(stores, session)

    assert await worker.run_cycle() == CYCLE_RAN

    pending = proposals.get_pending(USER)
    assert pending is not None
    assert pending["symbol"] == "BTCUSDT"
    assert pending["position_size"] > 0
    assert pending["take_profit_levels"] == [{"price": 68000.0}]

    state = mgr.get_active(USER)
    assert state["status"] == SETUP_PROPOSED

    # Deliberation is not charged: advance 10 minutes, metered time must not move.
    used_before = mgr.used_today(USER)
    clock.advance(600)
    assert mgr.used_today(USER) == used_before

    # And the next cycle does nothing while the proposal is on the table.
    assert await worker.run_cycle() == CYCLE_SKIPPED_NOT_SCANNING


@pytest.mark.asyncio
async def test_no_shared_setups_means_no_proposal(stores):
    mgr, prefs, proposals, cache = stores  # cache left empty
    session = mgr.start(USER)
    worker = _worker(stores, session)

    assert await worker.run_cycle() == CYCLE_RAN
    assert proposals.get_pending(USER) is None
    assert mgr.get_active(USER)["status"] == SCANNING  # still metering, still scanning


@pytest.mark.asyncio
async def test_stale_shared_setups_are_not_proposed(stores):
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache,
        freshness_seconds=0,  # everything in the cache is instantly too old
    )
    worker = SessionWorker(mgr, prefs, session, analyze)

    await worker.run_cycle()
    assert proposals.get_pending(USER) is None


@pytest.mark.asyncio
async def test_pulse_veto_blocks_the_symbol(stores):
    """FR-SYNTH-2: a vetoed pulse means no metered work on that symbol."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )

    context = {
        "session_id": session["session_id"],
        "user_id": USER,
        "preferences": prefs.get(USER),
        "pulses": {"BTCUSDT": {"vetoes": ["spread_too_wide"], "tradability": 0}},
        "symbols": ["BTCUSDT"],
    }
    setups, usage = await analyze(context)
    assert setups == [] and usage is None
    assert proposals.get_pending(USER) is None


@pytest.mark.asyncio
async def test_zero_tradability_blocks_even_without_vetoes(stores):
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )
    context = {
        "session_id": session["session_id"],
        "user_id": USER,
        "preferences": prefs.get(USER),
        "pulses": {"BTCUSDT": {"vetoes": [], "tradability": 0}},
        "symbols": ["BTCUSDT"],
    }
    setups, _ = await analyze(context)
    assert setups == []


@pytest.mark.asyncio
async def test_disallowed_strategy_is_filtered_per_user(stores):
    """Per-user judgment over shared facts: the same setup is proposable for one user
    and filtered for another."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])  # strategy_type SWING
    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )
    context = {
        "session_id": session["session_id"],
        "user_id": USER,
        "preferences": {**prefs.get(USER), "allowed_strategies": ["SCALP"]},
        "pulses": {},
        "symbols": ["BTCUSDT"],
    }
    setups, _ = await analyze(context)
    assert setups == []
    assert proposals.get_pending(USER) is None


@pytest.mark.asyncio
async def test_best_confidence_wins_the_single_proposal_slot(stores):
    mgr, prefs, proposals, cache = stores
    weaker = {**SHARED_SETUP, "confidence_score": 0.61}
    stronger = {
        **SHARED_SETUP,
        "symbol": "ETHUSDT",
        "entry_price": 2500.0,
        "stop_loss": 2400.0,
        "take_profit_levels": [{"price": 2800.0, "size": 1.0}],
        "confidence_score": 0.9,
    }
    cache.put("BTCUSDT", [weaker])
    cache.put("ETHUSDT", [stronger])
    session = mgr.start(USER)
    worker = _worker(stores, session)

    await worker.run_cycle()
    pending = proposals.get_pending(USER)
    assert pending is not None and pending["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_a_pending_proposal_blocks_a_second(stores):
    """One decision on the table at a time — proposing more would hand out unmetered,
    un-consented setups."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    worker = _worker(stores, session)
    await worker.run_cycle()
    first = proposals.get_pending(USER)

    # Even if the session were somehow scanning again with the proposal still live,
    # analyze must not stack a second one.
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )
    context = {
        "session_id": session["session_id"],
        "user_id": USER,
        "preferences": prefs.get(USER),
        "pulses": {},
        "symbols": ["BTCUSDT"],
    }
    setups, _ = await analyze(context)
    assert setups == []
    assert proposals.get_pending(USER)["proposal_id"] == first["proposal_id"]


@pytest.mark.asyncio
async def test_orphan_proposal_from_a_dead_session_does_not_starve_the_next(stores, clock):
    """A crashed or quota-ended session can leave a PROPOSED row behind. The pending
    guard is scoped by session, so the user's NEXT session proposes immediately instead
    of idling (metered!) until the orphan's TTL lapses."""
    mgr, prefs, proposals, cache = stores
    orphan = proposals.create(
        user_id=USER, session_id="dead-session",
        setup={**SHARED_SETUP, "take_profit_levels": [68000.0]},
        prefs=prefs.get(USER),
    )
    assert orphan is not None

    # In production an orphan is strictly older than the next session's proposal;
    # advance the shared fake clock so created_at DESC ordering reflects that instead
    # of tying both rows to the same frozen instant. (Also keeps the orphan inside its
    # 180s TTL — this test is about the guard, not expiry.)
    clock.advance(60)
    cache.put("BTCUSDT", [SHARED_SETUP])
    session = mgr.start(USER)
    worker = _worker(stores, session)

    assert await worker.run_cycle() == CYCLE_RAN
    pending = proposals.get_pending(USER)
    assert pending["session_id"] == session["session_id"]  # the NEW proposal won
    assert mgr.get_active(USER)["status"] == SETUP_PROPOSED


# --- channel differentiation -------------------------------------------------

def test_effective_prefs_overlays_the_channel():
    base = {"goal_horizon": "swing", "min_risk_reward": 1.5}
    scalp = effective_prefs_for_channel(base, "scalp")
    assert scalp["goal_horizon"] == "scalp"
    # scalp floor is 1.2 < the user's 1.5, so the stricter user value wins (tighten-only).
    assert scalp["min_risk_reward"] == 1.5

    position = effective_prefs_for_channel(base, "position")
    assert position["min_risk_reward"] == CHANNEL_MIN_RR["position"]  # 2.5 > 1.5


def test_no_channel_leaves_prefs_untouched():
    base = {"goal_horizon": "swing", "min_risk_reward": 1.5}
    assert effective_prefs_for_channel(base, None) is base


@pytest.mark.asyncio
async def test_channel_gates_which_setups_qualify(stores):
    """The same shared setup is proposable on a lenient channel and rejected on a strict
    one — the channel doing real work, not decoration."""
    mgr, prefs, proposals, cache = stores
    # A setup with R:R exactly 2.0: entry 64000, stop 62000 (risk 2000), target 68000
    # (reward 4000) => rr 2.0. Passes scalp/intraday/swing floors, fails position (2.5).
    setup = {**SHARED_SETUP, "take_profit_levels": [{"price": 68000.0, "size": 1.0}]}
    cache.put("BTCUSDT", [setup])

    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache
    )

    def _ctx(session_id, channel):
        return {
            "session_id": session_id, "user_id": USER,
            "preferences": {**prefs.get(USER), "min_risk_reward": 1.0},  # low persona floor
            "pulses": {}, "symbols": ["BTCUSDT"], "channel": channel,
        }

    # Scalp session: rr 2.0 clears the 1.2 floor -> proposed.
    s1 = mgr.start(USER, channel="scalp")
    setups, _ = await analyze(_ctx(s1["session_id"], "scalp"))
    assert len(setups) == 1
    mgr.end(s1["session_id"])

    # Position session: rr 2.0 is below the 2.5 floor -> rejected, session keeps scanning.
    s2 = mgr.start(USER, channel="position")
    setups, _ = await analyze(_ctx(s2["session_id"], "position"))
    assert setups == []
    assert mgr.get_active(USER)["status"] == SCANNING


# --- per-user synthesis ------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesis_can_pick_a_different_trade_than_the_confidence_sort(stores):
    """Same chart, different trade — the product's core claim. Without synthesis the
    highest-confidence candidate wins for everyone; with it, this user's agent picks the
    one that suits them."""
    mgr, prefs, proposals, cache = stores
    # Both clear the user's 0.6 confidence floor, so the only thing separating them is
    # whose judgment picks — which is exactly what synthesis is for.
    weaker_but_suitable = {**SHARED_SETUP, "confidence_score": 0.65}
    stronger = {
        **SHARED_SETUP, "symbol": "ETHUSDT", "entry_price": 2500.0, "stop_loss": 2400.0,
        "take_profit_levels": [{"price": 2800.0, "size": 1.0}], "confidence_score": 0.95,
    }
    cache.put("BTCUSDT", [weaker_but_suitable])
    cache.put("ETHUSDT", [stronger])

    async def choose_btc(candidates, prefs_, pulses, positions, channel):
        pick = next(c for c in candidates if c["symbol"] == "BTCUSDT")
        return {**pick, "thesis": "It did. It suits you. It breaks here."}, \
               {"input_tokens": 1000, "output_tokens": 50}, "chosen"

    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache,
        synthesize=choose_btc,
    )
    setups, usage = await analyze({
        "session_id": session["session_id"], "user_id": USER,
        "preferences": prefs.get(USER), "pulses": {}, "symbols": ["BTCUSDT", "ETHUSDT"],
    })

    assert len(setups) == 1
    assert setups[0]["symbol"] == "BTCUSDT", "synthesis was overridden by the confidence sort"
    assert setups[0]["thesis"] == "It did. It suits you. It breaks here."
    # The usage must reach the caller, or the session cost cap guards nothing.
    assert usage == {"input_tokens": 1000, "output_tokens": 50}


@pytest.mark.asyncio
async def test_synthesis_declining_produces_no_proposal_but_still_bills(stores):
    """'None of these fit you' is a real answer. The tokens it cost are still billed."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])

    async def decline(candidates, prefs_, pulses, positions, channel):
        return None, {"input_tokens": 900, "output_tokens": 8}, "declined"

    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache,
        synthesize=decline,
    )
    setups, usage = await analyze({
        "session_id": session["session_id"], "user_id": USER,
        "preferences": prefs.get(USER), "pulses": {}, "symbols": ["BTCUSDT"],
    })

    assert setups == []
    assert proposals.get_pending(USER) is None
    assert usage == {"input_tokens": 900, "output_tokens": 8}
    assert mgr.get_active(USER)["status"] == SCANNING  # clock keeps running, still scanning


@pytest.mark.asyncio
async def test_a_broken_synthesizer_falls_back_to_the_deterministic_pick(stores):
    """A user paying scan time must still get an answer when the model is unavailable."""
    mgr, prefs, proposals, cache = stores
    cache.put("BTCUSDT", [SHARED_SETUP])

    async def broken(candidates, prefs_, pulses, positions, channel):
        return None, None, "llm_error"

    session = mgr.start(USER)
    analyze = build_analyze_fn(
        session_manager=mgr, proposal_service=proposals, setup_cache=cache,
        synthesize=broken,
    )
    setups, _ = await analyze({
        "session_id": session["session_id"], "user_id": USER,
        "preferences": prefs.get(USER), "pulses": {}, "symbols": ["BTCUSDT"],
    })

    assert len(setups) == 1, "the deterministic fallback did not produce a proposal"
    assert setups[0]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_user_risk_prefs_can_reject_what_the_market_offers(stores):
    """A setup below the user's own R:R floor dies at THEIR gate, and the session keeps
    scanning — the per-user boundary doing its job."""
    mgr, prefs, proposals, cache = stores
    poor_rr = {
        **SHARED_SETUP,
        # 2000 risk for 400 reward: R:R 0.2, below every default floor.
        "take_profit_levels": [{"price": 64400.0, "size": 1.0}],
    }
    cache.put("BTCUSDT", [poor_rr])
    session = mgr.start(USER)
    worker = _worker(stores, session)

    assert await worker.run_cycle() == CYCLE_RAN
    assert proposals.get_pending(USER) is None
    assert mgr.get_active(USER)["status"] == SCANNING
