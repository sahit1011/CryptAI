"""Binds session workers to real work: per-user proposals from shared analysis.

This is the `analyze_fn` the SessionWorkerPool was designed around (session_worker.py
calls it once per metered cycle). M2 scope, stated honestly:

- The candidate SETUPS come from the shared analysis cycle — computed once per symbol
  for the whole deployment and cached here. That part is deliberately shared
  (docs/MULTI_TENANCY.md category 1/2: facts are user-independent).
- The JUDGMENT is per-user: universe from preferences, pulse gating, strategy filter,
  deterministic sizing against the user's own risk prefs (ProposalService), and the
  session state transition that pauses their clock while they decide.
- Full per-user LLM synthesis (different theses for different users on the same chart)
  is M3 (HLD FR-SYNTH-1). Until then `usage` is returned as None: the shared cycle's
  LLM spend is not attributable to any one session, and pretending otherwise would
  meter users for compute they did not cause.

One proposal at a time, by design: the state machine pauses the clock in
SETUP_PROPOSED, so proposing N setups at once would give N-1 of them away unmetered
and un-consented. The best candidate wins the slot; the rest die in the cache.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

#: A shared setup older than this is not proposable — the market has moved on. Matches
#: the shared cycle cadence (180s) with headroom for a slow LLM pass, and stays well
#: under the proposal TTL so we never propose something already near expiry.
DEFAULT_SETUP_FRESHNESS_SECONDS = 900

#: Minimum risk:reward a setup must clear to qualify for a channel. Faster styles
#: accept a tighter ratio (higher hit-rate, quicker turnover); slower styles demand
#: more reward per unit risk. Applied tighten-only against the user's own floor — the
#: channel can only make the bar STRICTER, never loosen the persona's risk rule.
CHANNEL_MIN_RR = {
    "scalp": 1.2,
    "intraday": 1.5,
    "swing": 2.0,
    "position": 2.5,
}


def effective_prefs_for_channel(
    prefs: Dict[str, Any], channel: Optional[str]
) -> Dict[str, Any]:
    """Overlay the session's chosen channel onto the persona: it sets goal_horizon for
    this session and raises (never lowers) the R:R floor. None keeps the persona as-is."""
    if not channel:
        return prefs
    floor = CHANNEL_MIN_RR.get(channel)
    out = {**prefs, "goal_horizon": channel}
    if floor is not None:
        out["min_risk_reward"] = max(float(prefs.get("min_risk_reward") or 0.0), floor)
    return out


class SharedSetupCache:
    """Latest shared-analysis setups per symbol, timestamped.

    Written by the daemon's analysis cycle, read by every session worker. Plain dict +
    monotonic-ish wall clock; single-process by design (the daemon owns both sides).
    """

    def __init__(self):
        self._by_symbol: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    def put(self, symbol: str, setups: List[Dict[str, Any]]) -> None:
        self._by_symbol[str(symbol).upper()] = (time.time(), list(setups or []))

    def fresh(
        self, symbol: str, max_age_seconds: float = DEFAULT_SETUP_FRESHNESS_SECONDS
    ) -> List[Dict[str, Any]]:
        stamped = self._by_symbol.get(str(symbol).upper())
        if stamped is None:
            return []
        ts, setups = stamped
        if time.time() - ts > max_age_seconds:
            return []
        return list(setups)


def _pulse_allows(pulse: Optional[Dict[str, Any]]) -> bool:
    """FR-SYNTH-2: do not spend a cycle on a symbol the shared plane has vetoed.

    A missing pulse ALLOWS: when the signal engine is not deployed the pulses dict is
    empty and gating is a no-op (mirrors SessionWorker._fresh_pulses). Once the engine
    ships, a present pulse with vetoes or zero tradability blocks the symbol.
    """
    if pulse is None:
        return True
    if pulse.get("vetoes"):
        return False
    tradability = pulse.get("tradability")
    if tradability is not None and float(tradability) <= 0:
        return False
    return True


def _strategy_allowed(setup: Dict[str, Any], prefs: Dict[str, Any]) -> bool:
    allowed = prefs.get("allowed_strategies")
    if not allowed:
        return True
    strategy = setup.get("strategy_type")
    return strategy is None or strategy in allowed


def build_analyze_fn(
    *,
    session_manager,
    proposal_service,
    setup_cache: SharedSetupCache,
    freshness_seconds: float = DEFAULT_SETUP_FRESHNESS_SECONDS,
    synthesize=None,
):
    """The production AnalyzeFn: shared candidates -> ONE proposal for THIS user.

    Returns `(proposals, usage)` per the session_worker contract.

    `synthesize` (optional, from `src.core.synthesis`) is what makes the choice personal:
    given the candidates plus this user's persona, holdings and the live conditions, it
    picks the one that fits them and writes the thesis. Without it — no LLM configured,
    or the call failed — the pick falls back to highest model confidence, which is the
    same trade for everyone. That fallback is deliberate: a user paying scan time must
    still get an answer when the model is unavailable.

    `usage` is the provider's token usage from that call, handed to the worker so it can
    bill the session's cost cap. Before synthesis existed nothing produced usage, which is
    why the cap guarded a number that never moved.
    """

    async def analyze(context: Dict[str, Any]) -> tuple:
        user_id = context["user_id"]
        session_id = context["session_id"]
        base_prefs = context.get("preferences") or {}
        # The session's channel (chosen at start) overrides the persona for THIS session.
        prefs = effective_prefs_for_channel(base_prefs, context.get("channel"))
        pulses = context.get("pulses") or {}
        symbols = context.get("symbols") or []

        # One pending proposal at a time — but scoped to THIS session. Normally
        # unreachable (the session is paused in SETUP_PROPOSED while one is pending);
        # the guard covers the sweeper-resume race. Scoping by session matters: an
        # orphan left PROPOSED by a crashed/quota-ended session must not hold the
        # slot and starve the user's NEXT session until the orphan's TTL lapses.
        # get_pending returns a lapsed row marked "expired"; that one never blocks.
        pending = await asyncio.to_thread(proposal_service.get_pending, user_id)
        if (
            pending is not None
            and pending.get("status") == "proposed"
            and pending.get("session_id") == session_id
        ):
            return [], None

        candidates: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]] = []
        vetoed = 0
        for symbol in symbols:
            pulse = pulses.get(symbol)
            if not _pulse_allows(pulse):
                vetoed += 1
                continue
            for setup in setup_cache.fresh(symbol, freshness_seconds):
                if _strategy_allowed(setup, prefs):
                    candidates.append((setup, pulse))

        if not candidates:
            session_manager.log_agent_step(
                session_id,
                "analysis",
                "no qualifying setups this cycle"
                + (f" ({vetoed} symbol(s) pulse-vetoed)" if vetoed else ""),
                {"symbols": symbols, "pulse_vetoed": vetoed},
            )
            return [], None

        # Who gets the single proposal slot? Ask the user's own agent first; fall back to
        # raw model confidence, which is the same answer for everybody.
        usage = None
        setup, pulse = max(
            candidates, key=lambda c: float(c[0].get("confidence_score") or 0.0)
        )
        if synthesize is not None:
            by_setup = {id(c[0]): c[1] for c in candidates}
            chosen, usage, outcome = await synthesize(
                [c[0] for c in candidates],
                prefs,
                pulses,
                context.get("open_positions"),
                context.get("channel"),
            )
            if outcome == "declined":
                # The user's agent looked at their book, their goals and these candidates
                # and said none of them fit. That is a real answer and the product's whole
                # premise — surface it and spend no more of their clock this cycle.
                session_manager.log_agent_step(
                    session_id,
                    "synthesis",
                    "none of this cycle's candidates fit your rules right now",
                    {"candidates": len(candidates)},
                )
                return [], usage
            if chosen is not None:
                # Keep the pulse that belongs to the CHOSEN setup, not the ranked one —
                # they can be different symbols, and the proposal records the pulse it
                # was built against.
                setup = chosen
                pulse = by_setup.get(id(candidates[0][0]), pulse)
                for original, original_pulse in candidates:
                    if original.get("symbol") == chosen.get("symbol"):
                        pulse = original_pulse
                        break

        # ProposalService.create floats each take-profit; shared setups carry
        # {price, size} dicts. Normalize to bare prices without mutating the cache.
        setup = {
            **setup,
            "take_profit_levels": [
                t["price"] if isinstance(t, dict) else float(t)
                for t in (setup.get("take_profit_levels") or [])
            ],
        }

        proposal = await asyncio.to_thread(
            proposal_service.create,
            user_id=user_id,
            session_id=session_id,
            setup=setup,
            prefs=prefs,
            pulse=pulse,
        )
        if proposal is None:
            # Failed deterministic validation against THIS user's prefs (sizing, R:R,
            # confidence floor). Not an error: the same setup may be valid for another
            # user — that asymmetry is the whole point of per-user gating.
            session_manager.log_agent_step(
                session_id,
                "risk_gate",
                f"candidate {setup.get('symbol')} rejected by your risk preferences",
                {"symbol": setup.get("symbol")},
            )
            return [], usage

        # Pause the clock; the user is deciding now. run_cycle checked SCANNING before
        # calling us, so this transition is legal barring an admin race (which raises
        # and is surfaced by the worker as a failed cycle — correct and loud).
        await asyncio.to_thread(
            session_manager.propose,
            session_id,
            f"{proposal['direction']} {proposal['symbol']} proposed "
            f"(size {proposal['position_size']:.6f}, R:R {proposal['risk_reward_ratio']:.2f})",
        )
        logger.info(
            f"proposal {proposal['proposal_id']} created for {user_id} "
            f"in session {session_id}"
        )
        return [proposal], usage

    return analyze
