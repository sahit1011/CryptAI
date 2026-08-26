"""R1.6b — the analysis prompt is compact by construction, not by hope.

The old path dumped the whole context as indent=2 JSON (~270KB / ~67k tokens per
call, mostly raw candles the indicator/SMC sections already summarized). These
tests pin the new contract: candles render as a stats line + recent CSV rows,
detector lists cap at the newest few WITH an explicit omission marker (silent
truncation is a lie), and every provider tier goes through the one shared
renderer so the shrink cannot regress in one path only.
"""
import inspect
from datetime import datetime, timedelta, timezone

from src.analysis.llm_context_builder import (
    LIST_CAP,
    RECENT_BARS_IN_PROMPT,
    _slim,
    render_user_message,
)

BASE = datetime(2026, 8, 24, 20, 0, tzinfo=timezone.utc)


def _bars(n, step_min=60):
    out = []
    for i in range(n):
        px = 64000.0 + i
        out.append({
            "t": (BASE - timedelta(minutes=step_min * (n - i))).isoformat(),
            "o": px, "h": px + 120.25, "l": px - 95.5, "c": px + 40.0, "v": 1200 + i,
        })
    return out


def _context(bars_per_tf=300):
    structs = [
        {"type": "order_block", "top": 64000.0 + i * 10.123456, "bottom": 63900.0,
         "timestamp": (BASE - timedelta(hours=i)).isoformat(), "strength": 0.512345}
        for i in range(10)
    ]
    return {
        "current_data": {"1h": _bars(bars_per_tf), "4h": _bars(bars_per_tf, 240)},
        "indicators": {"1h": {"rsi": {"current": 55.2}}},
        "smc_analysis": {"1h": {"order_blocks": structs}},
        "ict_analysis": {"1h": {"liquidity_sweeps": structs[:2]}},
        "patterns": {"1h": {"patterns": []}},
        "historical_context": {"recent_trades": []},
        "task_instructions": "OUTPUT JSON as specified.",
    }


def test_old_candles_are_summarized_not_dumped():
    msg = render_user_message(_context(bars_per_tf=300))
    bars = _bars(300)

    assert bars[-1]["t"][:16] in msg                 # newest bar shipped raw
    # the oldest bar appears in the span header ("300 bars, <oldest> → <newest>")
    # but never as a CSV data row (rows are "<ts>,<open>,...")
    assert bars[0]["t"][:16] in msg
    assert bars[0]["t"][:16] + "," not in msg
    assert msg.count("\n64") <= 2 * RECENT_BARS_IN_PROMPT + 4  # CSV rows, not 600 JSON objects
    # the window's information survives as stats: high/low/net over ALL 300 bars
    assert f"{max(b['h'] for b in bars):.10g}" in msg
    assert f"{min(b['l'] for b in bars):.10g}" in msg


def test_the_whole_message_stays_bounded():
    # The old renderer produced ~270,000 bytes from this same shape. Anything within
    # an order of magnitude of that again is a regression, whatever caused it.
    msg = render_user_message(_context(bars_per_tf=500))
    assert len(msg.encode()) < 40_000
    assert msg.rstrip().endswith("OUTPUT JSON as specified.")  # instructions survive


def test_detector_lists_cap_with_an_explicit_marker():
    slimmed = _slim([{"i": i} for i in range(10)])
    assert len(slimmed) == LIST_CAP + 1
    assert slimmed[0] == f"(+{10 - LIST_CAP} earlier entries omitted)"
    assert slimmed[-1] == {"i": 9}  # the NEWEST entries are the ones kept


def test_slim_rounds_for_display_without_destroying_prices():
    out = _slim({"top": 64010.123456, "strength": 0.512345, "ts": BASE.isoformat()})
    assert out["top"] == 64010.12          # cents kept
    assert out["strength"] == 0.5123       # ratios keep 4 decimals
    assert out["ts"] == "2026-08-24T20:00"  # ISO tail trimmed


def test_every_provider_tier_uses_the_shared_renderer():
    """Three tiers, one renderer — a size regression cannot hide in one path."""
    from src.agents.analysis_agent import MarketAnalysisAgent

    for method in ("_call_claude_analysis", "_call_openrouter_analysis", "_call_groq_analysis"):
        src = inspect.getsource(getattr(MarketAnalysisAgent, method))
        assert "render_user_message(safe_context)" in src, method
        assert "indent=2" not in src, f"{method} still dumps indented JSON"
