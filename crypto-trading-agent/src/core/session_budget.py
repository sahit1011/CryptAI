"""Per-session LLM spend metering.

The session cost cap was enforced from the day `SessionManager` landed, but nothing fed
it — `llm_cost_micros` stayed at zero, so the cap guarded a number that never moved. This
module closes that loop: it converts token usage into money and books it against the
session, which is what makes the cap real.

# Two design rules

**An unknown model is charged at a HIGH rate, never zero.** Charging zero for a model
missing from the table would let any unbudgeted model bypass the cap completely — add a
new provider, and the safety net silently stops existing. Unknown models are billed at
the most expensive tier we know of, so the failure mode is "stopped too early", which is
recoverable, rather than "spent without limit", which is not.

**Prices are overrides-first.** `LLM_PRICING_OVERRIDES` (JSON in the environment) is
consulted before the built-in table, so a price change never requires a deploy. The
built-in table is a floor, not the source of truth.

Costs are integer micro-USD throughout. Money is never a float here — the workspace rule
applies to spend just as much as to trade sizing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from loguru import logger

#: Multiplier on the base input rate for tokens served from the prompt cache.
CACHE_READ_MULTIPLIER = 0.1
#: Multiplier for writing the 5-minute cache. The 1h TTL is 2.0; we use the 5m default.
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class Pricing:
    """USD per 1,000,000 tokens."""

    input_per_mtok: float
    output_per_mtok: float


#: Anthropic list prices, verified 2026-08-02 against the claude-api reference.
#:
#: Sonnet 5 carries an introductory rate ($2/$10) through 2026-08-31; the standard rate is
#: used here deliberately. For a spend CAP, over-estimating cost stops the session early,
#: which is the safe direction — under-estimating overspends real money.
ANTHROPIC_PRICING: Dict[str, Pricing] = {
    "claude-fable-5": Pricing(10.0, 50.0),
    "claude-mythos-5": Pricing(10.0, 50.0),
    "claude-opus-5": Pricing(5.0, 25.0),
    "claude-opus-4-8": Pricing(5.0, 25.0),
    "claude-opus-4-7": Pricing(5.0, 25.0),
    "claude-opus-4-6": Pricing(5.0, 25.0),
    "claude-sonnet-5": Pricing(3.0, 15.0),
    "claude-sonnet-4-6": Pricing(3.0, 15.0),
    "claude-haiku-4-5": Pricing(1.0, 5.0),
}

#: Charged for any model not in the table or the overrides. Deliberately set at the most
#: expensive tier we know of rather than an average — see the module note.
UNKNOWN_MODEL_PRICING = Pricing(10.0, 50.0)


def _overrides() -> Dict[str, Pricing]:
    """Prices from `LLM_PRICING_OVERRIDES`, so a rate change needs no deploy.

    Shape: {"model-id": {"input": 3.0, "output": 15.0}}. A malformed value is logged and
    ignored rather than raised — a bad override must not take the engine down, and the
    built-in table plus the unknown-model fallback still bound spend.
    """
    raw = os.getenv("LLM_PRICING_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM_PRICING_OVERRIDES is not valid JSON; ignoring")
        return {}

    out: Dict[str, Pricing] = {}
    for model, entry in (parsed or {}).items():
        try:
            out[str(model)] = Pricing(float(entry["input"]), float(entry["output"]))
        except (KeyError, TypeError, ValueError):
            logger.warning(f"LLM_PRICING_OVERRIDES entry for {model!r} is malformed; ignoring")
    return out


def pricing_for(model: str) -> Pricing:
    """Price for a model. Overrides win; unknown models get the expensive fallback."""
    key = (model or "").strip()
    override = _overrides().get(key)
    if override is not None:
        return override
    known = ANTHROPIC_PRICING.get(key)
    if known is not None:
        return known

    # Prefix match so a dated snapshot (claude-opus-5-20260101) inherits its family's
    # price rather than falling through to the expensive unknown tier.
    for prefix, price in ANTHROPIC_PRICING.items():
        if key.startswith(prefix):
            return price

    logger.warning(
        f"no pricing for model {key!r}; charging the conservative fallback "
        f"(${UNKNOWN_MODEL_PRICING.input_per_mtok}/${UNKNOWN_MODEL_PRICING.output_per_mtok} "
        f"per Mtok). Add it to ANTHROPIC_PRICING or LLM_PRICING_OVERRIDES."
    )
    return UNKNOWN_MODEL_PRICING


def cost_micros(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> int:
    """Cost of one LLM call in integer micro-USD.

    Cache-read tokens bill at a tenth of the input rate and cache-write tokens at 1.25x,
    so a caching-heavy workload is not charged as if every token were fresh — the cap
    would otherwise fire far too early for exactly the workloads caching is meant to help.

    Rounds UP. A sub-micro-dollar call costs 1 micro rather than 0, so a tight loop of
    tiny calls still advances the meter instead of being free forever.
    """
    price = pricing_for(model)

    def clamp(n: int) -> int:
        return max(0, int(n or 0))

    total_usd = (
        clamp(input_tokens) * price.input_per_mtok
        + clamp(output_tokens) * price.output_per_mtok
        + clamp(cache_read_tokens) * price.input_per_mtok * CACHE_READ_MULTIPLIER
        + clamp(cache_write_tokens) * price.input_per_mtok * CACHE_WRITE_MULTIPLIER
    ) / 1_000_000.0

    micros = total_usd * 1_000_000.0
    if micros <= 0:
        return 0
    # Ceiling without float rounding surprises.
    return max(1, int(micros) + (1 if micros % 1 else 0))


def total_tokens(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> int:
    return sum(max(0, int(n or 0)) for n in
               (input_tokens, output_tokens, cache_read_tokens, cache_write_tokens))


class SessionBudget:
    """Books LLM spend against one session and reports whether it may continue.

    Usage at a call site:

        if not budget.can_spend():
            return  # session already over one of its meters
        response = call_llm(...)
        budget.record_response(model, response.usage)

    The manager cannot stop a caller that never asks — `can_spend()` before the call is
    what enforces the cap; `record_response()` after it is what keeps the accounting
    honest. Both are needed.
    """

    def __init__(self, session_manager, session_id: str):
        self.sessions = session_manager
        self.session_id = session_id

    def can_spend(self) -> bool:
        """Whether the session is still live under BOTH meters.

        Calls `tick()`, so this also enforces the clock — a caller that checks before
        every LLM call cannot overrun its metered time by more than one cycle.
        """
        from src.core.session_manager import ENDED, SessionError

        try:
            state = self.sessions.tick(self.session_id)
        except SessionError as e:
            logger.warning(f"budget check failed for {self.session_id}: {e}")
            return False  # fail closed
        return state.get("status") != ENDED

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> dict:
        """Book one call's usage. Returns the session state after the charge."""
        micros = cost_micros(
            model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        )
        tokens = total_tokens(
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
        )
        return self.sessions.record_llm_usage(self.session_id, tokens, micros)

    def record_response(self, model: str, usage) -> dict:
        """Book usage straight off an Anthropic SDK response's `usage` object.

        Reads attributes defensively: a provider that omits a cache field must degrade to
        charging zero for that component, not raise inside the metering path and lose the
        whole charge.
        """
        def get(name: str) -> int:
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(name)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        return self.record(
            model,
            input_tokens=get("input_tokens"),
            output_tokens=get("output_tokens"),
            cache_read_tokens=get("cache_read_input_tokens"),
            cache_write_tokens=get("cache_creation_input_tokens"),
        )
