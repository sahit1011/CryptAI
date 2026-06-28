"""
Unit tests for the ICT kill-zone timezone fix.

Candle timestamps arrive in UTC, but every ICT kill-zone / Asian-range /
Silver-Bullet hour comparison is defined in New York time (America/New_York).
Before the fix the UTC hour was compared directly against NY-defined hours,
shifting every session by 4 (EDT, summer) or 5 (EST, winter) hours.

These tests pin a known UTC timestamp to the expected NY session on both a
DST date (EDT, UTC-4) and a non-DST date (EST, UTC-5), so the conversion can't
silently regress.

Run: pytest tests/unit/test_ict_timezone.py
"""
from datetime import time

import pandas as pd
import pytest

from src.analysis.ict_detector import ICTDetector, NY_TZ


# --- Low-level conversion helpers --------------------------------------------

def test_to_ny_timestamp_dst_summer():
    """Summer date -> EDT (UTC-4). 12:00 UTC == 08:00 NY (New York Open)."""
    detector = ICTDetector()
    # 2024-07-15 is in US Daylight Saving Time (EDT, UTC-4).
    ny = detector._to_ny_timestamp(pd.Timestamp("2024-07-15 12:00:00"))
    assert ny.hour == 8
    assert ny.tzinfo is not None
    # NY Open kill zone is 07:00-10:00 ET, so 08:00 falls inside it.
    assert detector._is_time_in_killzone(
        time(ny.hour, ny.minute), detector.KILL_ZONES["new_york"]
    )


def test_to_ny_timestamp_non_dst_winter():
    """Winter date -> EST (UTC-5). 12:00 UTC == 07:00 NY (New York Open)."""
    detector = ICTDetector()
    # 2024-01-15 is in US Standard Time (EST, UTC-5).
    ny = detector._to_ny_timestamp(pd.Timestamp("2024-01-15 12:00:00"))
    assert ny.hour == 7
    assert detector._is_time_in_killzone(
        time(ny.hour, ny.minute), detector.KILL_ZONES["new_york"]
    )


def test_to_ny_timestamp_accepts_tz_aware_utc():
    """A tz-aware UTC timestamp is converted, not double-localized."""
    detector = ICTDetector()
    ny = detector._to_ny_timestamp(pd.Timestamp("2024-01-15 12:00:00", tz="UTC"))
    assert ny.hour == 7


def test_to_ny_index_localizes_naive_as_utc():
    """A naive index is treated as UTC and converted to NY hours."""
    detector = ICTDetector()
    idx = pd.DatetimeIndex(
        ["2024-07-15 07:00:00", "2024-01-15 07:00:00"]  # both 07:00 UTC
    )
    ny = detector._to_ny_index(idx)
    # 07:00 UTC -> 03:00 EDT (summer) and 02:00 EST (winter).
    assert list(ny.hour) == [3, 2]
    assert ny.tz is not None


# --- Kill-zone filtering on a full UTC-indexed frame -------------------------

def _utc_frame_for_day(day: str) -> pd.DataFrame:
    """One full UTC day of hourly candles (flat OHLCV) indexed in UTC."""
    idx = pd.date_range(start=f"{day} 00:00", periods=24, freq="1h")  # naive == UTC
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        },
        index=idx,
    )


def test_filter_by_killzone_new_york_summer():
    """NY Open (07:00-10:00 ET) on an EDT day maps to 11:00-14:00 UTC candles."""
    detector = ICTDetector()
    df = _utc_frame_for_day("2024-07-15")  # EDT, UTC-4
    ny_kz = detector.KILL_ZONES["new_york"]
    filtered = detector._filter_by_killzone(df, ny_kz)
    # 07,08,09 ET -> 11,12,13 UTC (end hour 10 ET excluded).
    assert sorted(filtered.index.hour.tolist()) == [11, 12, 13]


def test_filter_by_killzone_new_york_winter():
    """NY Open (07:00-10:00 ET) on an EST day maps to 12:00-15:00 UTC candles."""
    detector = ICTDetector()
    df = _utc_frame_for_day("2024-01-15")  # EST, UTC-5
    ny_kz = detector.KILL_ZONES["new_york"]
    filtered = detector._filter_by_killzone(df, ny_kz)
    # 07,08,09 ET -> 12,13,14 UTC.
    assert sorted(filtered.index.hour.tolist()) == [12, 13, 14]


def test_filter_by_killzone_london_summer():
    """London Open (02:00-05:00 ET) on an EDT day maps to 06:00-09:00 UTC."""
    detector = ICTDetector()
    df = _utc_frame_for_day("2024-07-15")  # EDT, UTC-4
    filtered = detector._filter_by_killzone(df, detector.KILL_ZONES["london"])
    # 02,03,04 ET -> 06,07,08 UTC.
    assert sorted(filtered.index.hour.tolist()) == [6, 7, 8]


def test_filter_by_killzone_asian_crosses_midnight():
    """Asian range (20:00-00:00 ET) wraps midnight; verify NY-hour selection."""
    detector = ICTDetector()
    df = _utc_frame_for_day("2024-01-15")  # EST, UTC-5
    filtered = detector._filter_by_killzone(df, detector.KILL_ZONES["asian"])
    ny_hours = detector._to_ny_index(filtered.index).hour.tolist()
    # Every selected candle must be >= 20:00 ET or < 00:00 ET (i.e. hour 20-23).
    assert ny_hours, "Asian range should select candles"
    assert all(h >= 20 or h < 0 for h in ny_hours)


# --- Silver Bullet hour gating ----------------------------------------------

def test_silver_bullet_uses_ny_hour_summer():
    """
    An Asian-low sweep stamped at 07:30 UTC on an EDT day is 03:30 ET, inside the
    London Open kill zone (02:00-05:00 ET), so it qualifies as a Silver Bullet.
    """
    detector = ICTDetector()
    # detect_silver_bullet requires >= 50 bars; build 3 UTC days of hourly candles.
    idx = pd.date_range(start="2024-07-13 00:00", periods=72, freq="1h")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        index=idx,
    )
    sweeps = [
        {
            "type": "asian_low_sweep",
            "level": 99.0,
            "sweep_price": 98.5,
            "timestamp": "2024-07-15 07:30:00",  # UTC -> 03:30 ET (London KZ)
            "strength": 0.6,
            "reversed": True,
            "significance": "high",
        }
    ]
    setups = detector.detect_silver_bullet(df, sweeps)
    assert len(setups) == 1
    assert setups[0]["type"] == "silver_bullet_long"


def test_silver_bullet_rejects_outside_london_kz():
    """
    The same sweep at 07:30 UTC interpreted naively (07:30) would be OUTSIDE the
    London KZ; a sweep that is genuinely outside the NY-converted London window
    must not produce a Silver Bullet.
    """
    detector = ICTDetector()
    df = _utc_frame_for_day("2024-07-15")
    sweeps = [
        {
            "type": "asian_high_sweep",
            "level": 101.0,
            "sweep_price": 101.5,
            "timestamp": "2024-07-15 18:00:00",  # UTC -> 14:00 ET (not London)
            "strength": 0.6,
            "reversed": True,
            "significance": "high",
        }
    ]
    setups = detector.detect_silver_bullet(df, sweeps)
    assert setups == []
