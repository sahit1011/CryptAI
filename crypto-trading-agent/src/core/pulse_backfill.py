"""Forward-return backfill for the pulse calibration log (R1.5c, FR-SIGNAL-3).

The writer records what the engine CLAIMED (tradability at time t, at a reference
price); this job records what the market DID (returns 15m/1h/4h later, and the best/
worst excursion within the hour). Together they make the score falsifiable: if
high-score windows do not produce better risk-adjusted forward returns than low-score
ones, the score is decoration and the weights must change.

Catch-up-able by design: a row is evaluated once, whenever all its windows have
elapsed — an outage delays evaluation, never loses it (unlike snapshots themselves).
The price source is the same REST klines the rest of the system uses; one 15m-candle
fetch per symbol per run covers every pending row.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

DEFAULT_INTERVAL_S = 3600.0
#: All horizons must have elapsed before a row is evaluated (4h max + one 15m bar of
#: slack so the closing candle itself is closed).
EVALUATION_LAG_MS = (4 * 60 + 15) * 60 * 1000
#: Rows per run — bounds one run's work; the next run picks up the rest.
BATCH_LIMIT = 500

HORIZONS_MS = {"fwd_return_15m": 15 * 60_000, "fwd_return_1h": 60 * 60_000, "fwd_return_4h": 240 * 60_000}
MFE_WINDOW_MS = 60 * 60_000


def compute_forward_returns(
    reference_price: float,
    pulse_ts_ms: int,
    candles: List[Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    """Pure: forward returns + 1h MFE/MAE from 15m candles ({ts_ms, high, low, close}).

    `ts_ms` is each candle's CLOSE time. A horizon's return uses the first candle
    closing at/after pulse_ts + horizon; returns None when the data cannot cover the
    4h window — an unevaluatable row must stay NULL, never be half-filled.
    """
    if reference_price <= 0 or not candles:
        return None
    rows = sorted(candles, key=lambda c: c["ts_ms"])

    def close_at(target_ms: int) -> Optional[float]:
        for c in rows:
            if c["ts_ms"] >= target_ms:
                return float(c["close"])
        return None

    out: Dict[str, float] = {}
    for column, horizon in HORIZONS_MS.items():
        close = close_at(pulse_ts_ms + horizon)
        if close is None:
            return None
        out[column] = (close - reference_price) / reference_price

    window = [c for c in rows if pulse_ts_ms < c["ts_ms"] <= pulse_ts_ms + MFE_WINDOW_MS]
    if not window:
        return None
    out["max_favorable_1h"] = (max(float(c["high"]) for c in window) - reference_price) / reference_price
    out["max_adverse_1h"] = (min(float(c["low"]) for c in window) - reference_price) / reference_price
    return out


class PulseBackfillJob:
    def __init__(self, session_factory, candle_fetcher, interval_s: float = DEFAULT_INTERVAL_S):
        """`candle_fetcher(symbol, since_ms, until_ms)` -> list of 15m-candle dicts."""
        self.session_factory = session_factory
        self.fetch_candles = candle_fetcher
        self.interval_s = interval_s

    def _pending(self):
        from src.data.data_models import PulseSnapshot

        cutoff = datetime.fromtimestamp(
            (now_ms() - EVALUATION_LAG_MS) / 1000, tz=timezone.utc
        )
        session = self.session_factory()
        try:
            rows = (
                session.query(PulseSnapshot)
                .filter(PulseSnapshot.evaluated_at.is_(None))
                .filter(PulseSnapshot.pulse_ts < cutoff)
                .order_by(PulseSnapshot.pulse_ts.asc())
                .limit(BATCH_LIMIT)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "pulse_ts_ms": int(r.pulse_ts.replace(tzinfo=timezone.utc).timestamp() * 1000),
                    "reference_price": float(r.reference_price),
                }
                for r in rows
            ]
        finally:
            session.close()

    def _apply(self, row_id: int, computed: Dict[str, float]) -> None:
        from src.data.data_models import PulseSnapshot

        session = self.session_factory()
        try:
            session.query(PulseSnapshot).filter(PulseSnapshot.id == row_id).update(
                {**computed, "evaluated_at": datetime.now(timezone.utc)}
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def backfill_once(self) -> int:
        pending = await asyncio.to_thread(self._pending)
        if not pending:
            return 0

        evaluated = 0
        by_symbol: Dict[str, List[dict]] = {}
        for row in pending:
            by_symbol.setdefault(row["symbol"], []).append(row)

        for symbol, rows in by_symbol.items():
            since = min(r["pulse_ts_ms"] for r in rows)
            until = max(r["pulse_ts_ms"] for r in rows) + EVALUATION_LAG_MS
            try:
                candles = await self.fetch_candles(symbol, since, until)
            except Exception as e:
                logger.warning(f"[pulse-backfill] candle fetch failed for {symbol}: {e}")
                continue
            for row in rows:
                computed = compute_forward_returns(
                    row["reference_price"], row["pulse_ts_ms"], candles or []
                )
                if computed is None:
                    continue  # stays NULL; a later run with fuller data picks it up
                try:
                    await asyncio.to_thread(self._apply, row["id"], computed)
                    evaluated += 1
                except Exception as e:
                    logger.warning(f"[pulse-backfill] update failed for row {row['id']}: {e}")

        if evaluated:
            logger.info(f"[pulse-backfill] evaluated {evaluated} snapshot(s)")
        return evaluated

    async def run(self, running=lambda: True) -> None:
        logger.info(f"[pulse-backfill] job started (every {self.interval_s:.0f}s)")
        while running():
            try:
                await asyncio.sleep(self.interval_s)
                await self.backfill_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[pulse-backfill] loop error: {e}")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
