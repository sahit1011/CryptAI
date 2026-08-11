"""Per-user setup synthesis — the difference between an agent team and a filter.

`docs/MULTI_TENANCY.md` puts the shared/per-user boundary here: the signal plane and the
analysis agents produce *facts and candidates* that are identical for everyone, and the
per-user session decides **which trade, for this person, right now**. Until this module
existed the session only sized and filtered a shared setup, so every user was offered the
same trade at a different size — a filter wearing an agent team's clothes.

# What the model is allowed to do

It **chooses among candidates and explains the choice**. It does not invent entries,
stops or targets.

That line is a money-safety decision, not a modesty one. Price levels come from
deterministic analysis of real candles; a language model asked to produce them will
produce plausible ones, and a plausible stop is indistinguishable from a correct stop
until it fills. Selection is where the per-user judgment actually lives anyway — it is
exactly the doc's own example: *a conservative user gets the 1h pullback continuation at
2.5R; an aggressive user gets the 5m liquidity sweep at 4R.* Same chart, different trade,
no invented numbers.

Sizing stays with `ProposalService.size_position`, which is arithmetic over the user's own
risk budget and must never be an opinion.

# Failure policy

Synthesis is an ENHANCEMENT over the deterministic pick. Every failure — no LLM
configured, a timeout, malformed JSON, an out-of-range index, a hallucinated symbol —
falls back to the highest-confidence candidate with no thesis. A session must never
produce nothing because the model was unavailable; the user is paying for scan time.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from loguru import logger

#: Tokens that turn an explanation into a prediction. The product's whole honesty stance
#: is that it scores conditions and never forecasts direction — the signal engine's own
#: walk-forward eval refuted regime-as-direction. A thesis containing these is rejected
#: rather than shown, because a confident-sounding forecast is the one thing that would
#: make a user over-trust the system.
BANNED = re.compile(
    r"\b(will\s+(?:hit|reach|go|rise|fall|moon)|should\s+reach|guaranteed|certain(?:ly)?|"
    r"sure\s+thing|expect\s+(?:it\s+)?to\s+(?:hit|reach)|predict|moon)\b",
    re.I,
)

SYSTEM_PROMPT = (
    "You choose which of several pre-computed trade setups best fits ONE specific "
    "trader, and explain why in their terms.\n\n"
    "HARD RULES:\n"
    "1. You may ONLY choose from the numbered candidates. Never invent a setup, a "
    "symbol, or any price level.\n"
    "2. You do NOT forecast direction. The entry/stop/target already exist; you are "
    "judging fit, not predicting the outcome. Never claim a trade will win.\n"
    "3. If none of the candidates suit this trader right now, choose none. Declining is "
    "a valid, useful answer — they are not obliged to trade.\n"
    "4. The thesis is exactly three sentences: (a) what has already happened, in past "
    "tense; (b) why this entry and this stop suit THIS trader; (c) what would make the "
    "setup wrong.\n\n"
    'Reply with JSON only: {"choice": <candidate number or null>, "thesis": "<three '
    'sentences, or empty if choice is null>"}'
)


def _fmt_positions(positions: List[Dict[str, Any]]) -> str:
    if not positions:
        return "none"
    return ", ".join(
        f"{p.get('symbol')} {p.get('positionSide') or p.get('direction') or ''}".strip()
        for p in positions[:8]
    )


def build_messages(
    candidates: List[Dict[str, Any]],
    prefs: Dict[str, Any],
    pulses: Dict[str, Any],
    open_positions: Optional[List[Dict[str, Any]]] = None,
    channel: Optional[str] = None,
) -> List[Dict[str, str]]:
    """The prompt. Pure, so the shape of what we ask can be tested without a provider."""
    lines: List[str] = ["THIS TRADER", "-----------"]
    lines.append(f"capital: {prefs.get('trading_capital')} {prefs.get('capital_currency', 'USDT')}")
    lines.append(f"risk appetite: {prefs.get('risk_appetite')}")
    lines.append(f"risk per trade: {prefs.get('max_risk_per_trade_pct')}%")
    lines.append(f"style for this scan: {channel or prefs.get('goal_horizon')}")
    lines.append(f"minimum reward:risk they accept: {prefs.get('min_risk_reward')}")
    lines.append(f"max leverage: {prefs.get('max_leverage')}x")
    if prefs.get("monthly_pnl_target_pct"):
        lines.append(f"30-day goal: {prefs['monthly_pnl_target_pct']}%")
    if prefs.get("goal_notes"):
        lines.append(f"their notes: {prefs['goal_notes']}")
    lines.append(f"already holding: {_fmt_positions(open_positions or [])}")

    lines += ["", "MARKET CONDITIONS (shared, not a forecast)", "-----------------------------------------"]
    if pulses:
        for symbol, pulse in pulses.items():
            if not isinstance(pulse, dict):
                continue
            vetoes = pulse.get("vetoes") or []
            lines.append(
                f"{symbol}: state {pulse.get('regime', 'unknown')}, "
                f"conditions {pulse.get('tradability', 'n/a')}/100"
                + (f", blocked by {', '.join(map(str, vetoes))}" if vetoes else "")
            )
    else:
        lines.append("no live condition scores available")

    lines += ["", "CANDIDATES", "----------"]
    for i, c in enumerate(candidates, 1):
        tps = c.get("take_profit_levels") or []
        first_tp = tps[0].get("price") if tps and isinstance(tps[0], dict) else (tps[0] if tps else None)
        lines.append(
            f"{i}. {c.get('symbol')} {c.get('direction')} "
            f"entry {c.get('entry_price')} stop {c.get('stop_loss')} target {first_tp} "
            f"playbook {c.get('strategy_type', 'n/a')} "
            f"model confidence {c.get('confidence_score', 'n/a')}"
        )

    lines += ["", "Which candidate fits this trader right now, and why?"]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def parse_choice(raw: str, candidate_count: int) -> Tuple[Optional[int], str]:
    """Extract (zero-based index, thesis) from a model reply. Pure and defensive.

    Returns (None, "") for a decline, malformed JSON, or an out-of-range index — every
    one of which must degrade to the deterministic path rather than raise into a metered
    cycle. A thesis carrying prediction language is dropped while the choice is kept: the
    selection is still useful, the forecast is not.
    """
    if not raw:
        return None, ""
    text = raw.strip()
    # Models wrap JSON in prose or fences often enough that finding the object is worth
    # more than insisting on a clean reply.
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None, ""
    try:
        obj = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None, ""
    if not isinstance(obj, dict):
        return None, ""

    choice = obj.get("choice")
    if choice is None:
        return None, ""
    try:
        idx = int(choice) - 1
    except (TypeError, ValueError):
        return None, ""
    if idx < 0 or idx >= candidate_count:
        return None, ""

    thesis = obj.get("thesis")
    thesis = thesis.strip() if isinstance(thesis, str) else ""
    if thesis and BANNED.search(thesis):
        logger.info("synthesis thesis rejected: prediction language")
        thesis = ""
    return idx, thesis


#: (messages, ) -> (reply_text, usage_object_or_None). Injected so this module never
#: depends on a provider SDK and stays unit-testable.
ChatFn = Callable[[List[Dict[str, str]]], Awaitable[Tuple[str, Any]]]


def build_synthesizer(chat: ChatFn, model: str = "unknown"):
    """A per-user chooser over shared candidates.

    Returns `(setup, usage)`. `setup` is one of the CANDIDATES, unmodified except for an
    added `thesis` — never a synthesized price. `usage` is whatever the provider reported,
    handed back so the caller can bill it to the session's budget (the meter that has
    existed, tested, and gone unfed since it was written).
    """

    async def synthesize(
        candidates: List[Dict[str, Any]],
        prefs: Dict[str, Any],
        pulses: Dict[str, Any],
        open_positions: Optional[List[Dict[str, Any]]] = None,
        channel: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Any, str]:
        if not candidates:
            return None, None, "no_candidates"
        messages = build_messages(candidates, prefs, pulses, open_positions, channel)
        try:
            reply, usage = await chat(messages)
        except Exception as e:
            logger.warning(f"synthesis call failed ({e}); falling back to the ranked pick")
            return None, None, "llm_error"

        idx, thesis = parse_choice(reply, len(candidates))
        if idx is None:
            # A deliberate decline and an unparseable reply are different events, but the
            # caller treats both the same: no per-user pick this cycle.
            return None, usage, "declined"

        chosen = dict(candidates[idx])
        if thesis:
            chosen["thesis"] = thesis
        chosen["synthesis_model"] = model
        return chosen, usage, "chosen"

    return synthesize
