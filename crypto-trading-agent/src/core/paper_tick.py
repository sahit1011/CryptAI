"""Paper-engine price ticks — the piece that makes paper brackets SELF-MANAGE.

The paper engine has always known how to fill a crossed limit order and trigger
a stop (PaperTradingEngine.check_limit_orders) — but nothing fed it live prices,
so resting SL/TP legs sat inert until a human closed the position. The daemon's
price-tick loop calls these helpers every few seconds with the live price map:

  - process_engine_tick: pushes each symbol's price into the engine (fills /
    triggers whatever crossed, marks open positions to market) and reports
    whether anything actually changed.
  - sweep_orphaned_legs: OCO hygiene — when a fill closes a position, the
    surviving reduce-only leg (the SL after a TP fill, or vice versa) must be
    canceled, or it can later fill into a phantom position.

Free functions (not daemon methods) so they run against a bare in-memory
engine in unit tests — no bus, no Redis.
"""
from typing import Any, Dict, Tuple

from loguru import logger


def _engine_snapshot(engine: Any) -> Tuple[int, int, int]:
    """A cheap change-detector: (open positions, open orders, settled trades)."""
    return (
        len(getattr(engine, "positions", {}) or {}),
        len(engine.get_open_orders() or []),
        int(getattr(engine, "total_trades", 0) or 0),
    )


async def process_engine_tick(engine: Any, prices: Dict[str, float]) -> bool:
    """Push live prices into one paper engine; True when a fill/trigger happened.

    Every symbol's price is fed (not just held ones): check_limit_orders also
    refreshes engine.current_prices, which market orders need for honest fills.
    Open positions are marked to market so published uPnL is current.
    """
    if not prices:
        return False

    before = _engine_snapshot(engine)

    for symbol, raw_price in prices.items():
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        sym = str(symbol).upper()

        # Fills crossed LIMIT orders, triggers crossed STOP/TP orders, and
        # refreshes the engine's price map — all engine-native behavior.
        await engine.check_limit_orders(sym, price)

        position = (getattr(engine, "positions", {}) or {}).get(sym)
        if position is not None and hasattr(position, "update_pnl"):
            position.update_pnl(price)

    return _engine_snapshot(engine) != before


async def sweep_orphaned_legs(engine: Any) -> int:
    """Cancel reduce-only orders whose position is gone (OCO hygiene).

    Returns how many legs were swept. Never raises — one stuck cancel must not
    stall the tick loop.
    """
    swept = 0
    try:
        open_symbols = set((getattr(engine, "positions", {}) or {}).keys())
        for order in engine.get_open_orders() or []:
            symbol = str(order.get("symbol", ""))
            if order.get("reduceOnly") and symbol not in open_symbols:
                try:
                    await engine.cancel_order(symbol, order.get("orderId"))
                    swept += 1
                except Exception as e:
                    logger.warning(f"[paper-tick] sweep failed for {order.get('orderId')}: {e}")
    except Exception as e:
        logger.warning(f"[paper-tick] sweep error: {e}")
    return swept
