"""The calibration log finally has a writer (R1.5, FR-SIGNAL-3).

pulse_snapshots had a table, five indexes, and a schema-parity test — and zero
writers, for months: the tested-but-unwired trap on the one table the entire quant
evidence plan depends on. These tests pin the writer against a REAL database schema
(sqlite in-memory, built from the models) and REAL Pulse dataclasses, so neither a
model drift nor a pulse-shape drift can pass silently.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.pulse_snapshots import PulseSnapshotWriter
from src.data.data_models import Base, PulseSnapshot
from src.signals.pulse_client import Pulse


def real_pulse(**over) -> Pulse:
    base = dict(
        v=1, symbol="BTCUSDT", ts=1_700_000_000_000, feed_ts=1_700_000_000_000,
        regime="Ranging", tradability=64, vetoes=[],
        factors={"liquidity_window": 1.0}, structure={}, context={"spread_bps": 0.5},
        reference_price=67000.0,
    )
    base.update(over)
    return Pulse(**base)


class FakePulseClient:
    def __init__(self, pulses):
        self.pulses = pulses

    async def get_many(self, symbols):
        return self.pulses


@pytest.fixture
def db():
    # StaticPool + check_same_thread=False: the writer inserts via asyncio.to_thread,
    # and a default-pooled in-memory sqlite would hand that thread a FRESH empty db.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[PulseSnapshot.__table__])
    return sessionmaker(bind=engine)


def make_writer(db, pulses):
    return PulseSnapshotWriter(db, FakePulseClient(pulses), ["BTCUSDT", "ETHUSDT"], interval_s=1)


@pytest.mark.asyncio
async def test_a_real_pulse_lands_as_a_complete_calibration_row(db):
    writer = make_writer(db, {"BTCUSDT": real_pulse()})

    assert await writer.write_once() == 1

    session = db()
    row = session.query(PulseSnapshot).one()
    assert row.symbol == "BTCUSDT"
    assert row.tradability == 64
    assert row.regime == "Ranging"
    assert row.vetoes == []
    assert row.factors == {"liquidity_window": 1.0}
    assert row.reference_price == pytest.approx(67000.0)
    # Without a reference price and timestamp the score is unfalsifiable — the
    # docstring's own words. Both must always be present.
    assert row.pulse_ts is not None
    session.close()


@pytest.mark.asyncio
async def test_a_dead_feed_is_not_resampled(db):
    """A pulse recomputed over stale facts has a fresh ts but the same feed_ts —
    logging copies inflates the calibration sample without adding information."""
    writer = make_writer(db, {"BTCUSDT": real_pulse()})

    assert await writer.write_once() == 1
    assert await writer.write_once() == 0  # same feed_ts — deduped

    writer.pulse_client.pulses = {"BTCUSDT": real_pulse(feed_ts=1_700_000_300_000, ts=1_700_000_300_000)}
    assert await writer.write_once() == 1  # feed moved — sampled again

    session = db()
    assert session.query(PulseSnapshot).count() == 2
    session.close()


@pytest.mark.asyncio
async def test_unfalsifiable_pulses_are_refused(db):
    """No reference price or no feed timestamp = log spam, not calibration data."""
    writer = make_writer(db, {
        "BTCUSDT": real_pulse(reference_price=0.0),
        "ETHUSDT": real_pulse(symbol="ETHUSDT", feed_ts=0),
    })
    assert await writer.write_once() == 0


@pytest.mark.asyncio
async def test_vetoed_pulses_are_logged_too(db):
    """Vetoed windows are exactly the negative examples calibration needs —
    filtering them out would bias every forward-return comparison."""
    writer = make_writer(db, {"BTCUSDT": real_pulse(vetoes=["StaleFeed"], tradability=0)})

    assert await writer.write_once() == 1
    session = db()
    row = session.query(PulseSnapshot).one()
    assert row.tradability == 0 and row.vetoes == ["StaleFeed"]
    session.close()


@pytest.mark.asyncio
async def test_a_read_failure_writes_nothing_and_does_not_raise(db):
    class ExplodingClient:
        async def get_many(self, symbols):
            raise ConnectionError("redis gone")

    writer = PulseSnapshotWriter(db, ExplodingClient(), ["BTCUSDT"])
    assert await writer.write_once() == 0
