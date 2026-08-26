"""The daily LLM request budget (R1.6): requests are the currency, not dollars.

On all-:free routing the dollar cap is structurally inert ($0.00 every call); the
provider's DAILY REQUEST CAP is what actually kills a deployment, and nothing tracked
it. These tests pin the full triangle: attempts are counted where requests DEPART
(including failed rotation attempts — each one spent a request), the counter flushes
to a Redis daily key, and exhaustion refuses new scans at the capacity gate while the
daemon skips shared cycles. The rail fails toward NOT blocking: a broken budget must
never become a second outage.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils.llm_request_budget import LlmRequestBudget, day_key, drain_pending, record_attempt
from src.utils.openrouter_rotation import complete_with_rotation
from src.multi_user_daemon import MultiUserTradingDaemon


@pytest.fixture(autouse=True)
def clean_counter():
    drain_pending()
    yield
    drain_pending()


# --------------------------------------------------------------------------- #
# attempts are counted where requests depart
# --------------------------------------------------------------------------- #

def test_every_rotation_attempt_is_counted_even_failures():
    """A dead-primary day multiplies the prompt by every retry — the budget must see
    each departure, not just the success."""
    calls = {"n": 0}

    class FlakyClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    if calls["n"] < 3:
                        raise RuntimeError("429 slow down")
                    msg = MagicMock()
                    msg.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
                    return msg

    content, model = complete_with_rotation(
        FlakyClient(), ["m1", "m2", "m3"], [{"role": "user", "content": "hi"}]
    )
    assert model == "m3"
    assert drain_pending() == 3  # two failures + one success, all counted


def test_total_rotation_failure_still_counts_every_attempt():
    class DeadClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("provider gone")

    with pytest.raises(RuntimeError):
        complete_with_rotation(DeadClient(), ["m1", "m2"], [{"role": "user", "content": "hi"}])
    assert drain_pending() == 2


# --------------------------------------------------------------------------- #
# the flush + the day key
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_flush_moves_the_delta_into_the_daily_key():
    redis = AsyncMock()
    b = LlmRequestBudget(redis)
    record_attempt(7)

    assert await b.flush() == 7
    redis.incrby.assert_awaited_once_with(day_key(), 7)
    redis.expire.assert_awaited_once()
    assert await b.flush() == 0  # drained


@pytest.mark.asyncio
async def test_a_failed_flush_keeps_the_delta_for_retry():
    redis = AsyncMock()
    redis.incrby.side_effect = ConnectionError("redis gone")
    b = LlmRequestBudget(redis)
    record_attempt(5)

    assert await b.flush() == 0
    assert drain_pending() == 5  # nothing lost — next flush retries


# --------------------------------------------------------------------------- #
# exhaustion refuses — and fails toward NOT blocking
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exhausted_at_the_cap_and_not_below(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_REQUEST_CAP", "100")
    redis = AsyncMock()
    b = LlmRequestBudget(redis)

    redis.get.return_value = "99"
    assert await b.exhausted() is False
    redis.get.return_value = "100"
    assert await b.exhausted() is True


@pytest.mark.asyncio
async def test_a_broken_budget_never_blocks(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_REQUEST_CAP", "1")
    redis = AsyncMock()
    redis.get.side_effect = ConnectionError("redis gone")
    assert await LlmRequestBudget(redis).exhausted() is False


@pytest.mark.asyncio
async def test_capacity_gate_refuses_with_the_named_reason(monkeypatch):
    from src.api import server as srv

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_DAILY_REQUEST_CAP", "10")
    monkeypatch.delenv("SIGNAL_PLANE_ENABLED", raising=False)
    fake_redis = AsyncMock()
    fake_redis.get.return_value = "10"
    sm = MagicMock()
    sm.redis = fake_redis
    monkeypatch.setattr(srv, "state_manager", sm)
    monkeypatch.setattr(srv, "_engine_switch", lambda: None)

    result = await srv._analysis_capacity()
    assert result["available"] is False
    assert result["reason"] == srv.CAPACITY_LLM_BUDGET


@pytest.mark.asyncio
async def test_daemon_skips_the_shared_cycle_when_exhausted():
    """The third side of the triangle: even with live scan demand, an exhausted budget
    spends nothing — the cycle returns empty before any orchestrator work."""
    d = MultiUserTradingDaemon.__new__(MultiUserTradingDaemon)
    d._has_scan_demand = AsyncMock(return_value=True)  # live demand — the hard case
    d.llm_budget = MagicMock()
    d.llm_budget.exhausted = AsyncMock(return_value=True)
    d._budget_was_exhausted = False
    d._was_on = None
    d.orchestrator = None  # proceeding past the gate would crash — proof it doesn't

    import os
    os.environ.pop("ANALYSIS_KEEP_WARM", None)
    assert await d._analysis_with_signals() == []
    assert d._budget_was_exhausted is True
