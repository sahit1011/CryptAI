"""Strategy profiles — which signal stack a metered session scans with.

Two profiles exist:

- **S2 (swing)** — today's behavior: the shared analysis pipeline's 4–12h swing
  setups. It is the default, and the absence of a `strategy` field anywhere must
  keep behaving exactly as before this module existed.
- **S1 (intraday confirmation)** — environment → location → confirmation → risk,
  per docs/plan-2026-08/orderflow-memo.md. PAPER-ONLY SCAFFOLDING behind the
  default-off `S1_ENABLED` flag: its signal math is still being validated, so no
  deployment gets it without an operator explicitly turning it on.

Resolution is fail-closed and honest: a request for a profile this deployment
does not offer raises a typed error the API maps to a 4xx, rather than silently
downgrading to S2 — a user who asked for S1 and got S2 would be trading a
different strategy than they believe, which the honesty law forbids.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Optional


class StrategyProfile(str, Enum):
    """str-valued so a profile serializes cleanly into JSON payloads and Redis."""

    S2_SWING = "s2_swing"
    S1_INTRADAY = "s1_intraday"


#: The profile every session runs when none is requested. S2 is today's behavior;
#: changing this constant is a product decision, not a config knob.
DEFAULT_PROFILE = StrategyProfile.S2_SWING

#: Request tokens accepted (lowercased). Short aliases exist because "s1"/"s2" is
#: the vocabulary the product docs and API clients use; the full enum values are
#: accepted so a value read back from Redis round-trips through resolve_profile.
_ALIASES = {
    "s2": StrategyProfile.S2_SWING,
    "s2_swing": StrategyProfile.S2_SWING,
    "s1": StrategyProfile.S1_INTRADAY,
    "s1_intraday": StrategyProfile.S1_INTRADAY,
}

#: Lifetime of the per-session strategy marker in Redis. Sessions are quota-capped
#: at 24h, so 48h outlives any legal session while guaranteeing abandoned markers
#: cannot accumulate forever (cost law: every key names its consumer and its end).
STRATEGY_KEY_TTL_SECONDS = 48 * 3600


class ProfileError(ValueError):
    """Base for strategy-profile resolution failures the API maps to a 4xx."""


class ProfileUnknown(ProfileError):
    """The requested value names no profile at all — a caller bug (422-shaped)."""


class ProfileUnavailable(ProfileError):
    """The profile exists but this deployment does not offer it (403-shaped).

    Distinct from ProfileUnknown so the API can tell the caller the truth: "s1 is
    real but not enabled here" is actionable in a way "unknown value" is not.
    """


def s1_enabled() -> bool:
    """Whether this deployment offers the S1 intraday profile. Default: no.

    Only the exact spelling `S1_ENABLED=true` (trimmed, case-insensitive) enables
    it — mirroring `_signal_plane_demanded()` in src/api/server.py. A flag guarding
    an unvalidated strategy gets one unambiguous ON spelling, not a family of
    truthy values that make an accidental enable easier.
    """
    return (os.getenv("S1_ENABLED") or "").strip().lower() == "true"


def resolve_profile(requested: Optional[str]) -> StrategyProfile:
    """Map a client-supplied strategy token to a profile, or raise a typed error.

    - None / "" / whitespace → DEFAULT_PROFILE (an absent choice is the default,
      never an error — old clients send nothing and must keep working unchanged).
    - "s2" / "s2_swing" (any case) → S2.
    - "s1" / "s1_intraday" (any case) → S1, but only when s1_enabled(); otherwise
      ProfileUnavailable.
    - anything else → ProfileUnknown, checked BEFORE availability so a garbage
      value is reported as garbage even on deployments where S1 is off.
    """
    if requested is None:
        return DEFAULT_PROFILE
    token = requested.strip().lower()
    if not token:
        return DEFAULT_PROFILE
    profile = _ALIASES.get(token)
    if profile is None:
        raise ProfileUnknown(
            f"unknown strategy '{requested}'; expected one of: "
            + ", ".join(sorted(set(_ALIASES)))
        )
    if profile is StrategyProfile.S1_INTRADAY and not s1_enabled():
        raise ProfileUnavailable(
            "strategy 's1' (intraday confirmation) is not enabled on this "
            "deployment; the default swing strategy ('s2') remains available"
        )
    return profile


def session_strategy_key(session_id: str) -> str:
    """Redis slot (under StateManager's `state:` prefix) carrying a session's profile.

    One function shared by the writer (POST /api/session/start) and any future
    reader (the daemon's session worker) so the key shape cannot drift between
    processes. Absence of the key ALWAYS means DEFAULT_PROFILE — the fail-safe
    reading, since S2 is today's behavior.
    """
    return f"session:{session_id}:strategy"
