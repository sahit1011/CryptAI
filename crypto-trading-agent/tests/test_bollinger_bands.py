"""Bollinger Bands column-mapping regression test.

Guards the bug where the middle-band selector also matched the BBB_ (bandwidth)
column, so bb_middle got overwritten with bandwidth (~0.02) and bb_width was garbage.
"""
import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators import TechnicalIndicators


def _ohlcv(n=120, base=60000.0):
    # Deterministic gently-trending series (no RNG).
    close = pd.Series([base + i * 5 + (50 if i % 7 == 0 else 0) for i in range(n)], dtype=float)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + 20,
        "low": close - 20,
        "close": close,
        "volume": pd.Series([100.0] * n),
    })


def test_bb_middle_is_between_bands_not_bandwidth():
    ind = TechnicalIndicators.calculate_all(_ohlcv())
    upper = float(ind["bb_upper"].iloc[-1])
    middle = float(ind["bb_middle"].iloc[-1])
    lower = float(ind["bb_lower"].iloc[-1])

    # Middle must be a price near the last close (~60k range), NOT a ~0.02 bandwidth.
    assert middle > 1000, f"bb_middle looks like bandwidth, not a price: {middle}"
    assert lower < middle < upper, f"band ordering wrong: {lower} < {middle} < {upper}"

    # bb_width = (upper-lower)/middle should be a small positive fraction, not blown up.
    width = float(ind["bb_width"].iloc[-1])
    assert 0 < width < 1, f"bb_width out of sane range: {width}"
