"""OCO (one-cancels-other) management tests for ExecutionAgent._on_leg_fill_oco.

Isolated: the handler only touches exchange.cancel_order, order_tracker.untrack_order,
and order_manager.active_executions, so we build a bare agent shell with stand-ins.
"""
from types import SimpleNamespace

import pytest

from src.execution.execution_agent import ExecutionAgent


class _FakeExchange:
    def __init__(self):
        self.cancelled = []

    async def cancel_order(self, symbol, order_id):
        self.cancelled.append(order_id)
        return True


def _agent_shell():
    a = ExecutionAgent.__new__(ExecutionAgent)  # skip heavy __init__
    a.exchange = _FakeExchange()
    a.order_tracker = SimpleNamespace(untrack_order=lambda oid: None)
    a.order_manager = SimpleNamespace(active_executions={})
    return a


def _order(oid):
    return SimpleNamespace(order_id=oid)


def _exec(sl, tps):
    return SimpleNamespace(
        symbol="BTC-USDT",
        stop_loss_order=_order(sl) if sl else None,
        take_profit_orders=[_order(t) for t in tps],
    )


@pytest.mark.asyncio
async def test_stop_loss_fill_cancels_all_take_profits():
    a = _agent_shell()
    a.order_manager.active_executions["e1"] = _exec("SL1", ["TP1", "TP2"])
    await a._on_leg_fill_oco(_order("SL1"))
    assert set(a.exchange.cancelled) == {"TP1", "TP2"}


@pytest.mark.asyncio
async def test_single_take_profit_fill_cancels_stop_loss():
    a = _agent_shell()
    a.order_manager.active_executions["e1"] = _exec("SL1", ["TP1"])
    await a._on_leg_fill_oco(_order("TP1"))
    assert a.exchange.cancelled == ["SL1"]


@pytest.mark.asyncio
async def test_partial_multi_tp_fill_keeps_stop_loss():
    # With multiple TPs, one TP filling does NOT cancel the SL — the remaining
    # position must stay protected.
    a = _agent_shell()
    a.order_manager.active_executions["e1"] = _exec("SL1", ["TP1", "TP2"])
    await a._on_leg_fill_oco(_order("TP1"))
    assert a.exchange.cancelled == []


@pytest.mark.asyncio
async def test_entry_or_unknown_fill_does_nothing():
    a = _agent_shell()
    a.order_manager.active_executions["e1"] = _exec("SL1", ["TP1"])
    await a._on_leg_fill_oco(_order("ENTRY-or-unknown"))
    assert a.exchange.cancelled == []
