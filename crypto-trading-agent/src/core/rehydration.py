"""Engine rehydration (R2.1): rebuild paper desks from Postgres after a restart.

The problem this ends: an open paper position was protected only by an in-memory
orders dict mirrored to a non-persistent Redis. Every deploy, crash, or free-tier
wake therefore orphaned open positions — the engine forgot them, the UI's close
button hit the zombie-drop branch, and the SL/TP brackets simply ceased to exist.

Doctrine (borrowed from Nautilus's reconciliation discipline, nautilus-memo.md):
**the persisted `trades` rows are the source of truth**; the Redis mirror is a
display cache to be converged, never believed; and a user's trading stays blocked
until their diff completes (the caller enforces that via `UserSession.rehydrated`).

Everything here is deliberately pure-ish (engine in, report out; the only I/O is
through the engine's own order-placement methods) so the whole flow is testable
without Redis, a bus, or Postgres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class RehydrationReport:
    """What one user's rehydration actually did — logged, and asserted in tests."""

    user_id: Optional[str]
    positions_restored: int = 0
    legs_restored: int = 0
    closed_trades: int = 0
    realized_pnl: float = 0.0
    commission_estimated: float = 0.0
    zombie_symbols: List[str] = field(default_factory=list)  # in Redis mirror, not in rows
    warnings: List[str] = field(default_factory=list)


def load_trades(trade_manager: Any, user_id: Optional[str],
                allow_unscoped: bool = False, limit: int = 10000) -> Tuple[list, list]:
    """One user's rows, split (open, closed). Open == exit_time IS NULL.

    `user_id` is REQUIRED unless `allow_unscoped=True` (the legacy single-bot
    path only): the previous restore loaded EVERY tenant's trades into whichever
    engine called it — a cross-user leak, not a bug to be re-shipped (R2.1 G6).

    Liveness is keyed on exit_time, not `status`: historical rows predate the
    status writer and would all read OPEN (G2).
    """
    if user_id is None and not allow_unscoped:
        raise ValueError("rehydration requires a user_id; unscoped loads are the "
                         "legacy single-bot path only (allow_unscoped=True)")
    rows = trade_manager.get_recent_trades(limit=limit, user_id=user_id)
    open_rows = [r for r in rows if r.exit_time is None]
    closed = [r for r in rows if r.exit_time is not None]
    return open_rows, closed


def diff_mirror(open_rows: list, mirror_positions: List[Dict[str, Any]]) -> List[str]:
    """Symbols the Redis mirror shows open that the rows do not — zombies.

    Rows win, always: the mirror is the thing that survives on the wrong side of
    a restart. Convergence itself happens when the caller publishes the engine's
    rebuilt state; this only names what is about to be dropped, so the log can
    say so before it happens.
    """
    truth = {str(r.symbol).upper() for r in open_rows}
    return sorted({
        str(p.get("symbol", "")).upper()
        for p in (mirror_positions or [])
        if str(p.get("symbol", "")).upper() and str(p.get("symbol", "")).upper() not in truth
    })


async def rehydrate_engine(engine: Any, open_rows: list, closed_rows: list,
                           mirror_positions: Optional[List[Dict[str, Any]]] = None,
                           ) -> RehydrationReport:
    """Rebuild one paper engine from its rows: balance, counters, positions, LEGS.

    The legs are the point. A restored position without its resting reduce-only
    SL/TP orders is a naked position — the exact orphan this task exists to end.
    Legs are re-placed through the engine's OWN placement methods (the same ones
    OrderManager uses live) so the tick loop fills them identically to booked ones.
    """
    from src.execution.paper_trading_engine import OrderSide, PaperPosition

    report = RehydrationReport(user_id=getattr(engine, "user_id", None))
    report.zombie_symbols = diff_mirror(open_rows, mirror_positions or [])
    if report.zombie_symbols:
        logger.warning(f"[rehydrate] {report.user_id}: dropping Redis-only zombies "
                       f"{report.zombie_symbols} — rows are the source of truth")

    # --- closed rows -> balance and lifetime counters (arithmetic lifted from the
    # legacy restore; commissions are ESTIMATED at taker on both legs because no
    # commission column exists yet — a known drift source, logged not hidden). ---
    realized = commission = 0.0
    wins = 0
    for r in closed_rows:
        pnl = float(r.pnl or 0.0)
        realized += pnl
        if pnl > 0:
            wins += 1
        notional_in = float(r.position_size or 0) * float(r.entry_price or 0)
        notional_out = float(r.position_size or 0) * float(r.exit_price or 0)
        commission += (notional_in + notional_out) * engine.taker_fee

    # --- open rows -> positions + protective legs ---
    for r in sorted(open_rows, key=lambda x: x.entry_time or 0):
        symbol = str(r.symbol).upper()
        if symbol in engine.positions:
            # One position per symbol is the engine's data model; two open rows for
            # one symbol is a ledger anomaly a restart cannot invent its way out of.
            report.warnings.append(
                f"{symbol}: multiple open rows — kept the newest, "
                f"older row {engine.positions[symbol].position_id} needs manual review"
            )
        qty = float(r.position_size or 0.0)
        entry = float(r.entry_price or 0.0)
        if qty <= 0 or entry <= 0:
            report.warnings.append(f"{r.trade_id}: unusable row (qty={qty}, entry={entry})")
            continue

        position = PaperPosition(
            symbol=symbol,
            side=str(r.direction).upper(),
            quantity=qty,
            entry_price=entry,
            current_price=entry,  # marked to market by the first price tick
            # POS_{trade_id}: the close path derives trade_id by stripping "POS_",
            # so any other convention would update the WRONG row on exit (G7).
            position_id=f"POS_{r.trade_id}",
            leverage=int(r.leverage or engine.leverage),
        )
        if r.entry_time is not None:
            position.opened_at = r.entry_time
        engine.positions[symbol] = position
        report.positions_restored += 1
        commission += qty * entry * engine.taker_fee  # entry leg was paid pre-restart

        close_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY

        # SL leg — the one order that must never be missing on a restored position.
        stop_loss = float(r.stop_loss or 0.0)
        if stop_loss > 0:
            await engine.place_stop_loss_order(
                symbol=symbol, side=close_side, quantity=qty,
                stop_price=stop_loss, reduce_only=True,
            )
            report.legs_restored += 1
        else:
            report.warnings.append(f"{r.trade_id}: open row has no stop_loss — "
                                   f"position restored UNPROTECTED, review immediately")

        # TP legs: sized dicts when the row carries them (post-R2.1 bookings),
        # else bare prices split evenly (legacy rows) — same fallback the live
        # order manager applies to sizeless levels.
        sized = [t for t in (r.tp_order_ids or []) if isinstance(t, dict) and t.get("price")]
        if not sized:
            bare = [float(p) for p in (r.take_profit_levels or [])
                    if isinstance(p, (int, float)) and float(p) > 0]
            share = round(1.0 / len(bare), 6) if bare else 0.0
            sized = [{"price": p, "size": share} for p in bare]
        for leg in sized:
            leg_qty = min(qty, qty * min(1.0, max(0.0, float(leg.get("size") or 0.0))))
            if leg_qty <= 0 or float(leg["price"]) <= 0:
                continue
            await engine.place_limit_order(
                symbol=symbol, side=close_side, quantity=leg_qty,
                price=float(leg["price"]), reduce_only=True,
            )
            report.legs_restored += 1

    # --- lifetime aggregates ---
    engine.balance = engine.initial_balance + realized - commission
    engine.total_trades = len(closed_rows)
    engine.winning_trades = wins
    engine.total_commission = commission
    engine.peak_balance = max(engine.balance, engine.initial_balance)
    if engine.peak_balance > 0:
        drawdown = (engine.peak_balance - engine.balance) / engine.peak_balance
        engine.max_drawdown = max(engine.max_drawdown, drawdown)

    report.closed_trades = len(closed_rows)
    report.realized_pnl = realized
    report.commission_estimated = commission

    logger.info(
        f"[rehydrate] {report.user_id}: {report.positions_restored} position(s) + "
        f"{report.legs_restored} leg(s) restored, {report.closed_trades} closed trades "
        f"(P&L ${realized:+,.2f}), balance ${engine.balance:,.2f}"
        + (f", {len(report.warnings)} warning(s)" if report.warnings else "")
    )
    for w in report.warnings:
        logger.warning(f"[rehydrate] {report.user_id}: {w}")
    return report
