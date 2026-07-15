"""orchestrator.run_analysis_cycle — the multi-user daemon's analysis_provider seam.

Verifies the analysis-only path runs the shared phases and honors the graph's gates
(error short-circuit, volatile-regime skip) WITHOUT touching the single-bot
risk/execute/log nodes. The four node methods are stubbed so no Redis/agents/network
are needed — we're testing the sequencing + gates that run_analysis_cycle adds.
"""
from unittest.mock import MagicMock

import pytest

from src.core.orchestrator import TradingOrchestrator

SETUP = {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": 64000.0,
         "stop_loss": 62000.0, "recommended_position_size": 0.05}


def _orch():
    # __init__ only stores refs + compiles the graph; it never calls the bus/state,
    # so plain mocks are enough to construct it.
    return TradingOrchestrator(message_bus=MagicMock(), state_manager=MagicMock(),
                               symbol="BTCUSDT")


def _stub_nodes(orch, *, regime="TRENDING_BULLISH", setups=(SETUP,), error_at=None):
    """Replace the 4 analysis nodes with async stubs that mutate state like the real ones."""
    async def collect(state):
        if error_at == "collect":
            state["errors"].append("data fetch failed")
        else:
            state["market_data"] = {"price": 64000.0}
            state["candles"] = {"15m": [{"close": 64000.0}]}
        return state

    async def analyze(state):
        if error_at == "analyze":
            state["errors"].append("analysis failed")
        else:
            state["analysis_result"] = {"trend": "up"}
        return state

    async def detect(state):
        if error_at == "regime":
            state["errors"].append("regime failed")
        else:
            state["regime"] = {"regime": regime}
        return state

    async def strategies(state):
        state["opportunities"] = list(setups)
        return state

    orch._collect_data_node = collect
    orch._analyze_market_node = analyze
    orch._detect_regime_node = detect
    orch._generate_strategies_node = strategies


@pytest.mark.asyncio
async def test_happy_path_returns_setups():
    orch = _orch()
    _stub_nodes(orch, setups=(SETUP,))
    setups = await orch.run_analysis_cycle()
    assert setups == [SETUP]


@pytest.mark.asyncio
async def test_volatile_regime_skips_strategy_generation():
    orch = _orch()
    _stub_nodes(orch, regime="volatile")  # gate must skip -> no setups
    assert await orch.run_analysis_cycle() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["collect", "analyze", "regime"])
async def test_error_short_circuits(stage):
    orch = _orch()
    _stub_nodes(orch, error_at=stage)
    assert await orch.run_analysis_cycle() == []


@pytest.mark.asyncio
async def test_no_opportunities_returns_empty():
    orch = _orch()
    _stub_nodes(orch, setups=())
    assert await orch.run_analysis_cycle() == []


@pytest.mark.asyncio
async def test_never_raises_on_node_exception():
    orch = _orch()

    async def boom(state):
        raise RuntimeError("collector exploded")

    orch._collect_data_node = boom
    # Must swallow and return [] so one bad cycle can't take the daemon down.
    assert await orch.run_analysis_cycle() == []
