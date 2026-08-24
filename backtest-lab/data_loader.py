"""Monthly kline zips -> numpy column arrays, hermetically dull on purpose.

Binance USDT-M futures kline CSV columns (data.binance.vision archive):
open_time, open, high, low, close, volume, close_time, quote_volume, count,
taker_buy_volume, taker_buy_quote_volume, ignore. Newer dumps ship a header row,
older ones don't — sniffed per file, never assumed.
"""
from __future__ import annotations

import glob
import os
import zipfile

import numpy as np
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")

COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]
KEEP = ["open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"]


def load(symbol: str, tf: str) -> dict:
    """All months of one symbol/timeframe as {col: np.ndarray}, time-sorted, deduped."""
    paths = sorted(glob.glob(os.path.join(RAW_DIR, f"{symbol}-{tf}-*.zip")))
    if not paths:
        raise FileNotFoundError(f"no archives for {symbol} {tf} under {RAW_DIR}")

    frames = []
    for p in paths:
        with zipfile.ZipFile(p) as z:
            inner = z.namelist()[0]
            with z.open(inner) as f:
                first = f.readline().decode()
            header = 0 if first.split(",")[0].strip() == "open_time" else None
            with z.open(inner) as f:
                df = pd.read_csv(f, header=header, names=None if header == 0 else COLS,
                                 usecols=KEEP)
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)

    # sanity: timestamps must be milliseconds and the grid must be regular enough
    ts = df["open_time"].to_numpy(dtype=np.int64)
    assert ts[0] > 1e12 and ts[0] < 1e13, f"open_time not in ms: {ts[0]}"
    step_ms = {"1m": 60_000, "1h": 3_600_000}[tf]
    gaps = int((np.diff(ts) != step_ms).sum())
    total = len(ts) - 1
    assert gaps < total * 0.001, f"{symbol} {tf}: {gaps}/{total} irregular steps"

    out = {c: df[c].to_numpy(dtype=np.float64) for c in KEEP if c != "open_time"}
    out["open_time"] = ts
    out["gaps"] = gaps
    return out
