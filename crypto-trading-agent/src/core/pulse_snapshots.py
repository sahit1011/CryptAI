"""The pulse calibration log writer (R1.5, FR-SIGNAL-3).

`pulse_snapshots` existed for months with a table, five indexes, a schema-parity test —
and ZERO writers: the repo's signature tested-but-unwired trap, live again. Every claim
the quant plan makes (temporal re-validation of the tradability weights, learned hot
hours, the real-money evidence memo) is blocked until rows accumulate. This closes it.

Sampling, not firehose: the engine publishes per symbol every ~5s, but the score's
validated horizon is 4-12 HOURS — a 5-minute sample carries all the calibration
information while keeping the free 500MB Postgres honest (~30MB per 90 days at three
symbols, vs ~2.7GB unsampled). A dead feed is deduped by `feed_ts`: recomputed pulses
over stale facts would otherwise fill the log with copies that inflate sample size
without adding information.

Forward-return columns stay NULL here — the backfill job (separate, catch-up-able)
fills them once each window has elapsed. Losing an hour of backfill costs nothing;
losing an hour of snapshots is unrecoverable, which is why the writer ships with the
engine enable itself.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

DEFAULT_INTERVAL_S = 300.0


class PulseSnapshotWriter:
    def __init__(
        self,
        session_factory,
        pulse_client,
        symbols: List[str],
        interval_s: float = DEFAULT_INTERVAL_S,
    ):
        """`session_factory`: a zero-arg callable returning a SQLAlchemy Session."""
        self.session_factory = session_factory
        self.pulse_client = pulse_client
        self.symbols = [s.upper() for s in symbols]
        self.interval_s = interval_s
        self._last_feed_ts: Dict[str, int] = {}

    @classmethod
    def from_database_url(cls, database_url: str, pulse_client, symbols: List[str],
                          interval_s: float = DEFAULT_INTERVAL_S) -> "PulseSnapshotWriter":
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.utils.db import pool_kwargs

        engine = create_engine(database_url, **pool_kwargs())
        return cls(sessionmaker(bind=engine), pulse_client, symbols, interval_s)

    # -- pure-ish helpers ------------------------------------------------------

    @staticmethod
    def _as_dict(pulse: Any) -> Optional[Dict[str, Any]]:
        if isinstance(pulse, dict):
            return pulse
        try:
            return dataclasses.asdict(pulse)
        except TypeError:
            d = getattr(pulse, "__dict__", None)
            return dict(d) if d else None

    def rows_to_write(self, pulses: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The subset of this sample worth persisting, deduped by feed freshness."""
        rows: List[Dict[str, Any]] = []
        for symbol, raw in pulses.items():
            pulse = self._as_dict(raw)
            if not pulse:
                continue
            feed_ts = int(pulse.get("feed_ts") or 0)
            reference_price = pulse.get("reference_price")
            if feed_ts <= 0 or not reference_price:
                # An unfalsifiable row (no timestamp or no price) is log spam, not data.
                continue
            if self._last_feed_ts.get(symbol) == feed_ts:
                continue  # dead/unchanged feed — a copy adds sample size, not information
            self._last_feed_ts[symbol] = feed_ts
            rows.append({
                "symbol": symbol.upper(),
                "pulse_ts": datetime.fromtimestamp(int(pulse.get("ts") or feed_ts) / 1000, tz=timezone.utc),
                "schema_version": int(pulse.get("v") or 1),
                "regime": str(pulse.get("regime") or "Unknown"),
                "tradability": int(pulse.get("tradability") or 0),
                "vetoes": pulse.get("vetoes") or [],
                "factors": pulse.get("factors") or {},
                "context": pulse.get("context") or {},
                "reference_price": float(reference_price),
            })
        return rows

    # -- I/O -------------------------------------------------------------------

    def _insert(self, rows: List[Dict[str, Any]]) -> None:
        from src.data.data_models import PulseSnapshot

        session = self.session_factory()
        try:
            session.add_all([PulseSnapshot(**row) for row in rows])
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def write_once(self) -> int:
        """One sample: read fresh pulses, persist the new ones. Returns rows written."""
        try:
            pulses = await self.pulse_client.get_many(self.symbols)
        except Exception as e:
            logger.warning(f"[pulse-log] read failed: {e}")
            return 0
        rows = self.rows_to_write(pulses or {})
        if not rows:
            return 0
        try:
            await asyncio.to_thread(self._insert, rows)
        except Exception as e:
            logger.warning(f"[pulse-log] insert failed ({len(rows)} rows): {e}")
            return 0
        return len(rows)

    async def run(self, running=lambda: True) -> None:
        logger.info(
            f"[pulse-log] calibration writer started ({len(self.symbols)} symbols, "
            f"every {self.interval_s:.0f}s)"
        )
        while running():
            try:
                await asyncio.sleep(self.interval_s)
                wrote = await self.write_once()
                if wrote:
                    logger.debug(f"[pulse-log] {wrote} snapshot(s) written")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[pulse-log] loop error: {e}")
