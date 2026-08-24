"""Forward-return backfill (R1.5c): the half of the calibration loop that records
what the market DID after each scored pulse.

The math is pure and pinned first; the job is then exercised against a real schema
(sqlite in-memory) with a fake candle source — young rows untouched, incomplete data
stays NULL rather than half-filled, evaluated rows never re-evaluated.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.pulse_backfill import PulseBackfillJob, compute_forward_returns
from src.data.data_models import Base, PulseSnapshot

T0 = 1_700_000_000_000  # pulse time, ms


def bars(start_ms, count, close=100.0, high=101.0, low=99.0, step_ms=900_000):
    """`count` 15m candles whose CLOSE times start at start_ms."""
    return [
        {"ts_ms": start_ms + i * step_ms, "high": high, "low": low, "close": close}
        for i in range(count)
    ]


# --------------------------------------------------------------------------- #
# the pure math
# --------------------------------------------------------------------------- #

def test_forward_returns_read_the_first_close_at_or_after_each_horizon():
    candles = bars(T0 + 900_000, 20, close=110.0)
    out = compute_forward_returns(100.0, T0, candles)
    assert out is not None
    for col in ("fwd_return_15m", "fwd_return_1h", "fwd_return_4h"):
        assert out[col] == pytest.approx(0.10)


def test_mfe_and_mae_come_from_the_first_hour_only():
    inside = bars(T0 + 900_000, 4, close=100.0, high=105.0, low=97.0)      # first hour
    later = bars(T0 + 5 * 900_000, 16, close=100.0, high=150.0, low=50.0)  # after it
    out = compute_forward_returns(100.0, T0, inside + later)
    assert out["max_favorable_1h"] == pytest.approx(0.05)
    assert out["max_adverse_1h"] == pytest.approx(-0.03)


def test_incomplete_windows_evaluate_to_none_never_half_filled():
    # Only 1h of candles: the 4h horizon cannot be answered.
    assert compute_forward_returns(100.0, T0, bars(T0 + 900_000, 4)) is None
    assert compute_forward_returns(100.0, T0, []) is None
    assert compute_forward_returns(0.0, T0, bars(T0 + 900_000, 20)) is None


# --------------------------------------------------------------------------- #
# the job against a real schema
# --------------------------------------------------------------------------- #

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[PulseSnapshot.__table__])
    return sessionmaker(bind=engine)


def snapshot_row(pulse_ts, **over):
    row = dict(
        symbol="BTCUSDT", pulse_ts=pulse_ts, schema_version=1, regime="Ranging",
        tradability=60, vetoes=[], factors={}, context={}, reference_price=100.0,
    )
    row.update(over)
    return PulseSnapshot(**row)


@pytest.mark.asyncio
async def test_old_rows_are_evaluated_and_young_rows_wait(db):
    old_ts = datetime.now(timezone.utc) - timedelta(hours=6)
    young_ts = datetime.now(timezone.utc) - timedelta(minutes=30)
    session = db()
    session.add_all([snapshot_row(old_ts), snapshot_row(young_ts)])
    session.commit()
    session.close()

    async def fetcher(symbol, since_ms, until_ms):
        return bars(since_ms + 900_000, 24, close=105.0)

    job = PulseBackfillJob(db, fetcher)
    assert await job.backfill_once() == 1

    session = db()
    old = session.query(PulseSnapshot).filter(PulseSnapshot.pulse_ts == old_ts.replace(tzinfo=None)).one()
    assert old.evaluated_at is not None
    assert old.fwd_return_1h == pytest.approx(0.05)
    young = session.query(PulseSnapshot).filter(PulseSnapshot.evaluated_at.is_(None)).one()
    assert young.fwd_return_1h is None
    session.close()

    # Idempotent: the evaluated row is never picked up again.
    assert await job.backfill_once() == 0


@pytest.mark.asyncio
async def test_insufficient_candles_leave_the_row_pending(db):
    old_ts = datetime.now(timezone.utc) - timedelta(hours=6)
    session = db()
    session.add(snapshot_row(old_ts))
    session.commit()
    session.close()

    async def thin_fetcher(symbol, since_ms, until_ms):
        return bars(since_ms + 900_000, 2)  # cannot cover 4h

    job = PulseBackfillJob(db, thin_fetcher)
    assert await job.backfill_once() == 0

    session = db()
    row = session.query(PulseSnapshot).one()
    assert row.evaluated_at is None and row.fwd_return_15m is None
    session.close()
