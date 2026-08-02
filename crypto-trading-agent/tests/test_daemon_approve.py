"""The daemon-side approve path: revalidate at the LIVE price, execute, mark.

Exercises MultiUserTradingDaemon._approve_proposal — the money decision — on a stub
host (no Redis, no agents): real ProposalService/PreferencesStore over SQLite, a real
UserSession with an isolated paper engine, injected clock.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.core.multi_user import UserRiskConfig, UserSession
from src.core.preferences import PreferencesStore
from src.core.proposals import (
    EXECUTED,
    PROPOSED,
    REASON_PRICE_MOVED,
    ProposalService,
)
from src.multi_user_daemon import MultiUserTradingDaemon

USER = "user-aaa"
START = datetime(2026, 8, 2, 10, 0, 0)

SETUP = {
    "symbol": "BTCUSDT",
    "direction": "LONG",
    "entry_price": 64000.0,
    "stop_loss": 62000.0,
    "take_profit_levels": [68000.0],
    "confidence_score": 0.8,
}


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def host(tmp_path, clock):
    """A stub daemon carrying only what _approve_proposal reads."""
    return SimpleNamespace(
        proposal_service=ProposalService(f"sqlite:///{tmp_path}/pr.db", now_fn=clock),
        preferences_store=PreferencesStore(f"sqlite:///{tmp_path}/p.db"),
    )


@pytest.fixture
def session():
    return UserSession(USER, config=UserRiskConfig(initial_balance=10_000.0))


def _proposal(host):
    prefs = host.preferences_store.get(USER)
    proposal = host.proposal_service.create(
        user_id=USER, session_id="sess-1", setup=SETUP, prefs=prefs
    )
    assert proposal is not None
    return proposal


async def _seed_price(session, price, symbol="BTCUSDT"):
    await session.engine.check_limit_orders(symbol, price)


@pytest.mark.asyncio
async def test_approve_executes_at_live_price_and_marks_executed(host, session, clock):
    proposal = _proposal(host)
    await _seed_price(session, 64010.0)  # within drift tolerance of entry

    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, USER, {"proposal_id": proposal["proposal_id"]}
    )

    assert result["approved"] is True
    assert len(session.engine.get_positions()) == 1
    stored = host.proposal_service.get(proposal["proposal_id"], USER)
    assert stored["status"] == EXECUTED
    # And the risk tracker saw the booking (the M1 wiring, working here end-to-end).
    assert await session.portfolio.get_position_count() == 1


@pytest.mark.asyncio
async def test_price_drift_refuses_the_fill(host, session, clock):
    proposal = _proposal(host)
    await _seed_price(session, 70000.0)  # ~9% from entry — far beyond tolerance

    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, USER, {"proposal_id": proposal["proposal_id"]}
    )

    assert result["approved"] is False
    assert result["reason"] == REASON_PRICE_MOVED
    assert result["retryable"] is True  # the API must keep the session paused
    assert session.engine.get_positions() == []
    # Not consumed: price can come back; the shelf life is the real deadline.
    assert host.proposal_service.get(proposal["proposal_id"], USER)["status"] == PROPOSED


@pytest.mark.asyncio
async def test_no_live_price_means_no_fill(host, session):
    proposal = _proposal(host)  # engine never seeded with a price

    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, USER, {"proposal_id": proposal["proposal_id"]}
    )

    assert result["approved"] is False
    assert result["reason"] == "no_live_price"
    assert result["retryable"] is True
    assert session.engine.get_positions() == []


@pytest.mark.asyncio
async def test_expired_proposal_is_refused_and_marked(host, session, clock):
    proposal = _proposal(host)
    await _seed_price(session, 64010.0)
    clock.advance(10 * 60)  # far past the 180s shelf life

    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, USER, {"proposal_id": proposal["proposal_id"]}
    )

    assert result["approved"] is False
    assert result["reason"] == "expired"
    assert result["retryable"] is False  # terminal: the API resumes scanning
    assert session.engine.get_positions() == []
    assert host.proposal_service.get(proposal["proposal_id"], USER)["status"] == "expired"


@pytest.mark.asyncio
async def test_cross_tenant_proposal_id_does_not_resolve(host, session):
    """A proposal id belonging to another tenant must behave as if it does not exist."""
    proposal = _proposal(host)  # owned by USER
    await _seed_price(session, 64010.0)

    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, "user-mallory", {"proposal_id": proposal["proposal_id"]}
    )
    # Mallory has no pending proposal of her own, and USER's id must not resolve.
    assert result["approved"] is False
    assert result["reason"] == "no_pending_proposal"
    assert host.proposal_service.get(proposal["proposal_id"], USER)["status"] == PROPOSED


@pytest.mark.asyncio
async def test_session_plane_unavailable_fails_closed(session):
    host = SimpleNamespace(proposal_service=None, preferences_store=None)
    result = await MultiUserTradingDaemon._approve_proposal(
        host, session, USER, {"proposal_id": "x"}
    )
    assert result["approved"] is False
    assert result["reason"] == "session_plane_unavailable"


# --- the sweeper: restores "pending proposal <=> paused session" -----------------

def _sweep_host(tmp_path, clock):
    from src.core.session_manager import SessionManager

    return SimpleNamespace(
        proposal_service=ProposalService(f"sqlite:///{tmp_path}/pr.db", now_fn=clock),
        preferences_store=PreferencesStore(f"sqlite:///{tmp_path}/p.db"),
        session_manager=SessionManager(
            f"sqlite:///{tmp_path}/s.db", daily_quota_seconds=1800, now_fn=clock
        ),
    )


@pytest.mark.asyncio
async def test_sweep_resumes_a_paused_session_whose_proposal_lapsed(tmp_path, clock):
    host = _sweep_host(tmp_path, clock)
    s = host.session_manager.start(USER)
    proposal = host.proposal_service.create(
        user_id=USER, session_id=s["session_id"],
        setup=SETUP, prefs=host.preferences_store.get(USER),
    )
    assert proposal is not None
    host.session_manager.propose(s["session_id"])
    clock.advance(10 * 60)  # proposal lapses; clock was paused so no time metered

    await MultiUserTradingDaemon._sweep_once(host)

    assert host.session_manager.get_active(USER)["status"] == "scanning"


@pytest.mark.asyncio
async def test_sweep_closes_a_session_whose_proposal_executed(tmp_path, clock):
    """The lost-reply case from the sweeper's side: proposal EXECUTED, session still
    paused. Resuming would let the session book a second trade; it must end as
    trade_opened instead."""
    from src.core.proposals import EXECUTED
    from src.core.session_manager import TRADE_OPENED

    host = _sweep_host(tmp_path, clock)
    s = host.session_manager.start(USER)
    proposal = host.proposal_service.create(
        user_id=USER, session_id=s["session_id"],
        setup=SETUP, prefs=host.preferences_store.get(USER),
    )
    host.session_manager.propose(s["session_id"])
    host.proposal_service.mark(proposal["proposal_id"], EXECUTED, "TRADE-7")

    await MultiUserTradingDaemon._sweep_once(host)

    assert host.session_manager.get_active(USER) is None
    ended = host.session_manager.get(s["session_id"])
    assert ended["status"] == "ended"
    assert ended["end_reason"] == TRADE_OPENED


@pytest.mark.asyncio
async def test_sweep_leaves_a_live_proposal_alone(tmp_path, clock):
    host = _sweep_host(tmp_path, clock)
    s = host.session_manager.start(USER)
    host.proposal_service.create(
        user_id=USER, session_id=s["session_id"],
        setup=SETUP, prefs=host.preferences_store.get(USER),
    )
    host.session_manager.propose(s["session_id"])

    await MultiUserTradingDaemon._sweep_once(host)

    assert host.session_manager.get_active(USER)["status"] == "setup_proposed"
