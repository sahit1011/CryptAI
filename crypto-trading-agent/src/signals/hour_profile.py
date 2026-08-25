"""The measured intraday activity profile — a backward-looking fact, never a forecast.

`hour_profile.json` is produced by `backtest-lab/study_hour_profile.py` from 24 months
of 1m bars across the traded symbols: for each UTC hour, the mean of per-symbol
z-scores of (mean volume, mean bar range / price). It ships as a static artifact
because it is a *measurement of the past*, not a live signal — regenerating it is a
deliberate quant act with a fresh date range, not something a request does.

Why this exists at all: the founder wants a "hottest hour" indicator, and the honesty
law forbids forward claims until logged data earns them. This threads that needle. The
product may say **"this hour has historically been the 1st most active of 24 (measured
over N bars, DATE–DATE)"** — checkable, sourced, past-tense. It may never say "the next
hour will be hot", and nothing here returns a prediction to make that easy.

If the profile file is missing or malformed, every accessor returns None and callers
must render "unknown". A badge that silently invents a rank is worse than no badge.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "hour_profile.json")

_cache: Optional[Dict[str, Any]] = None
_load_failed = False


def load_profile() -> Optional[Dict[str, Any]]:
    """The artifact, parsed once. None when absent/unreadable (never a fabrication)."""
    global _cache, _load_failed
    if _cache is not None:
        return _cache
    if _load_failed:
        return None
    try:
        with open(PROFILE_PATH) as f:
            data = json.load(f)
        hours = data.get("hours_utc") or {}
        if len(hours) != 24:
            raise ValueError(f"expected 24 hours, found {len(hours)}")
        _cache = data
        return _cache
    except Exception as e:
        logger.warning(f"[hour-profile] unusable ({e}); activity ranks unavailable")
        _load_failed = True
        return None


def describe_hour(now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """How active the CURRENT UTC hour has historically been.

    Returns `{hour_utc, rank, of, score, in_top_window, top_window_utc, sample}` or
    None. `rank` 1 = most active of the 24. Every number is past-tense and carries
    its provenance so a reader can audit the claim.
    """
    profile = load_profile()
    if profile is None:
        return None
    moment = now or datetime.now(timezone.utc)
    hour = moment.astimezone(timezone.utc).hour
    entry = (profile.get("hours_utc") or {}).get(str(hour))
    if not entry:
        return None
    top = sorted(profile.get("top6_hours_utc") or [])
    return {
        "hour_utc": hour,
        "rank": int(entry["rank"]),
        "of": 24,
        "score": float(entry["score"]),
        "in_top_window": hour in top,
        "top_window_utc": top,
        "sample": {
            "bars": profile.get("total_1m_bars"),
            "symbols": profile.get("symbols"),
            "from_ms": profile.get("measured_from_ms"),
            "to_ms": profile.get("measured_to_ms"),
            "metric": profile.get("metric"),
            "per_year_agreement": profile.get("top6_agreement_per_year"),
        },
        "caveat": profile.get("caveat"),
    }
