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
#: An adverb defeated the first version of this ("will LIKELY reach"), and so did any
#: verb it did not enumerate ("should hit", "going to hit"). Adjacency is the wrong shape
#: for the rule: what makes a sentence a forecast is a future-tense construction anywhere
#: near a price verb, so allow filler between the two rather than listing every phrasing.
_FILLER = r"(?:\s+\w+){0,3}\s+"
_TARGET_VERB = r"(?:hit|reach|touch|test|break|rally|climb|drop|fall|rise|go|continue|bounce)"
BANNED = re.compile(
    r"\b(?:"
    rf"(?:will|would|shall|gonna|going\s+to|should|ought\s+to|expects?\s+to|likely\s+to)"
    rf"{_FILLER}?{_TARGET_VERB}"
    # "I expect a move to 70k" has no target verb at all — the forecast lives in the
    # verb itself, so first-person expectation is banned outright.
    r"|expects?\b|anticipates?\b"
    r"|guaranteed|certain(?:ly)?|sure\s+thing|surely|definitely|"
    r"predicts?|prediction|forecasts?|highly\s+likely|moon"
    r")\b",
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


#: How `parse_choice` read the reply. The distinction matters more than it looks: a
#: DECLINE is the agent's judgment and is shown to the user as such, while UNREADABLE is
#: our failure to parse and must fall back silently to the deterministic pick. Collapsing
#: them tells the user "none of these fit your rules" — a decision their agent never
#: made — every time a free model answers in prose or gets truncated mid-JSON.
PICKED = "picked"
DECLINED = "declined"
UNREADABLE = "unreadable"


def parse_choice(raw: str, candidate_count: int) -> Tuple[str, Optional[int], str]:
    """Read a model reply into (verdict, zero-based index, thesis). Pure and defensive.

    Never raises: everything unexpected is UNREADABLE, because this runs inside a metered
    cycle. A thesis carrying prediction language is dropped while the choice is kept — the
    selection is still useful, the forecast is the part that would mislead.
    """
    if not raw or not raw.strip():
        return UNREADABLE, None, ""
    # Models wrap JSON in prose or fences often enough that finding the object is worth
    # more than insisting on a clean reply.
    match = re.search(r"\{.*\}", raw.strip(), re.S)
    if not match:
        return UNREADABLE, None, ""
    try:
        obj = json.loads(match.group(0))
    except (ValueError, TypeError):
        return UNREADABLE, None, ""
    if not isinstance(obj, dict):
        return UNREADABLE, None, ""
    if "choice" not in obj:
        return UNREADABLE, None, ""

    choice = obj.get("choice")
    if choice is None:
        # An explicit null is the model using the escape hatch the prompt offers. That is
        # a real answer and the only case the user should be told about.
        return DECLINED, None, ""
    try:
        idx = int(choice) - 1
    except (TypeError, ValueError):
        return UNREADABLE, None, ""
    if idx < 0 or idx >= candidate_count:
        # Naming candidate 7 of 2 is a broken reply, not a considered decline.
        return UNREADABLE, None, ""

    thesis = obj.get("thesis")
    thesis = thesis.strip() if isinstance(thesis, str) else ""
    if thesis and BANNED.search(thesis):
        logger.info("synthesis thesis rejected: prediction language")
        thesis = ""
    return PICKED, idx, thesis


#: (messages, ) -> (reply_text, usage_object_or_None). Injected so this module never
#: depends on a provider SDK and stays unit-testable.
ChatFn = Callable[[List[Dict[str, str]]], Awaitable[Tuple[str, Any]]]


def _normalize_usage(usage: Any, model: str) -> Optional[Dict[str, Any]]:
    """Translate a provider's usage object into the shape `SessionBudget` bills.

    `SessionBudget.record_response` reads ANTHROPIC field names (`input_tokens`,
    `output_tokens`, `cache_read_input_tokens`). The OpenAI-compatible SDK returns
    `prompt_tokens` / `completion_tokens`, so every lookup missed and every synthesis call
    booked ZERO — the cost cap guarded a constant while claiming to guard real spend.
    Translating here, where the provider shape is known, keeps that knowledge out of the
    generic meter.

    `model` is carried in the dict because the worker reads the model name off usage to
    price the call; without it every call prices as UNKNOWN ($10/$50 per Mtok), which
    would end a free-model session on the cost cap for spend that never happened.
    """
    if usage is None:
        return None

    def pick(*names: str) -> int:
        for name in names:
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(name)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
        return 0

    return {
        "model": model,
        "input_tokens": pick("input_tokens", "prompt_tokens"),
        "output_tokens": pick("output_tokens", "completion_tokens"),
        "cache_read_input_tokens": pick("cache_read_input_tokens", "cached_tokens"),
        "cache_creation_input_tokens": pick("cache_creation_input_tokens"),
    }


def build_openai_compatible_chat(client, models: List[str], max_tokens: int = 400):
    """A `ChatFn` over an OpenAI-style client (OpenRouter, OpenAI, Groq).

    `models` is tried in order and the first usable completion wins. That is not
    belt-and-braces: OpenRouter's `:free` catalogue rotates and rate-limits hard, so any
    single free model can be pulled, 429, or hand back an empty body at any moment —
    pinning one has already made this engine silently produce nothing once. The same
    rotation list the agents use (`config.llm.openrouter_free_models`) is passed in here.

    The client is called in a worker thread because the codebase deliberately uses the
    SYNC OpenAI client for OpenRouter (see `strategy_agent`: AsyncOpenAI misbehaves
    against it), and blocking the daemon's event loop would stall every other session's
    worker, the monitors and the paper tick loop along with it.

    `max_tokens` is small on purpose: the reply is one integer and three sentences.
    Output tokens are the expensive half and this runs once per cycle per active session,
    so the ceiling is what keeps a per-session cost bounded.
    """
    import asyncio as _asyncio

    async def chat(messages: List[Dict[str, str]]) -> Tuple[str, Any]:
        last_error: Optional[Exception] = None
        for model in models:
            def _call(m=model):
                return client.chat.completions.create(
                    model=m,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.2,  # a selection, not a creative writing exercise
                )

            try:
                response = await _asyncio.to_thread(_call)
            except Exception as e:  # 429, model pulled, provider error — try the next
                last_error = e
                logger.debug(f"synthesis model {model} unavailable: {e}")
                continue

            choices = getattr(response, "choices", None) or []
            text = ""
            if choices:
                text = getattr(getattr(choices[0], "message", None), "content", "") or ""
            if not text.strip():
                # An empty body is a dead free slot, not an answer. Keep walking.
                logger.debug(f"synthesis model {model} returned an empty body")
                continue
            return text, _normalize_usage(getattr(response, "usage", None), model)

        if last_error is not None:
            raise last_error
        raise RuntimeError("no synthesis model returned a usable completion")

    return chat


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

        verdict, idx, thesis = parse_choice(reply, len(candidates))
        if verdict == UNREADABLE:
            # OUR failure, not the agent's judgment. Free instruct models answer in prose
            # and a max_tokens cut truncates mid-JSON, so this is routine — it must fall
            # back to the deterministic pick, never surface as "none of these fit you".
            logger.info("synthesis reply unreadable; falling back to the ranked pick")
            return None, usage, "llm_error"
        if verdict == DECLINED:
            return None, usage, "declined"

        chosen = dict(candidates[idx])
        if thesis:
            chosen["thesis"] = thesis
        chosen["synthesis_model"] = model
        return chosen, usage, "chosen"

    return synthesize
