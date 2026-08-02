"""Per-position monitors — the trade doesn't fall asleep after it opens.

The vision's point 6: once a trade is on, a per-user monitor keeps watching it against
changing conditions and decides stay-in vs book-and-exit, instead of firing the order and
waiting for a static SL/TP to resolve.

# What this is, in the three-category model (docs/MULTI_TENANCY.md)

`PositionMonitorWorker` is a **category-3** instance — one per OPEN POSITION, not per
session. `MonitorSupervisor` is the **category-2** singleton that discovers open positions
across tenants and keeps one monitor alive per position.

# Unmetered and unconditional (invariant 8)

A monitor is money-safety, not billing. It runs regardless of session state, quota, or the
owner's engine switch: a session ending — or its quota lapsing — while a position is open
must NEVER stop the monitor. It lives as long as the position does.

# What it adds over the static bracket

The paper engine's own tick loop already fills a resting SL/TP when price crosses it. The
monitor is the DYNAMIC layer on top: it exits early when the *thesis* — not just the price
level — has broken. Its gates are deterministic and, deliberately, never map regime to a
trade direction (the signal engine's own eval refuted that out of sample). They are:

- **Time stop** — a scalp still open hours later is a broken thesis; close it.
- **Profit give-back** — once a position has run far enough into profit, surrender only a
  bounded slice of that peak before booking it.
- **Deteriorating conditions** — when the shared pulse vetoes the symbol or tradability
  collapses for several checks running, the clean-trade window is gone; step aside.

The LLM re-synthesis path (FR-MONITOR-3: re-poll the analysis and reason about it) is a
pluggable follow-up; this module owns the lifecycle and the deterministic gates so both are
testable without an LLM or a live market.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

# -- decision core (pure, testable) ------------------------------------------

HOLD = "hold"
EXIT = "exit"

REASON_TIME_STOP = "time_stop"
REASON_PROFIT_PROTECT = "profit_protect"
REASON_CONDITIONS = "conditions_deteriorated"

#: Max hold before a time stop fires, by trading horizon. Keyed on the persona's
#: goal_horizon AND the tracker's strategy_type labels, which historically differ.
DEFAULT_MAX_HOLD_SECONDS: Dict[str, int] = {
    "scalp": 30 * 60,
    "SCALP": 30 * 60,
    "intraday": 4 * 3600,
    "DAY_TRADE": 4 * 3600,
    "day_trade": 4 * 3600,
    "swing": 3 * 24 * 3600,
    "SWING": 3 * 24 * 3600,
    "position": 14 * 24 * 3600,
    "POSITION": 14 * 24 * 3600,
}
DEFAULT_HORIZON_FALLBACK_SECONDS = 4 * 3600


@dataclass(frozen=True)
class MonitorConfig:
    #: Favorable return the position must reach before the give-back guard arms.
    lock_profit_pct: float = 0.008          # 0.8%
    #: Give-back from the favorable peak that triggers a protective exit.
    giveback_pct: float = 0.005             # 0.5%
    #: Pulse tradability at or below this counts as an adverse read.
    min_tradability: float = 25.0
    #: Consecutive adverse pulse reads before stepping aside.
    adverse_exit_checks: int = 3
    max_hold_seconds: Optional[Dict[str, int]] = None

    def max_hold_for(self, horizon: Optional[str]) -> int:
        table = self.max_hold_seconds or DEFAULT_MAX_HOLD_SECONDS
        return table.get(horizon or "", DEFAULT_HORIZON_FALLBACK_SECONDS)


@dataclass
class MonitorState:
    #: Best favorable return seen so far (peak of favorable excursion).
    peak_fav: float = 0.0
    #: Consecutive adverse pulse reads.
    adverse_streak: int = 0


@dataclass(frozen=True)
class MonitorDecision:
    action: str  # HOLD | EXIT
    reason: str = ""


def favorable_return(direction: str, entry_price: float, current_price: float) -> float:
    """Signed return in the position's favor (positive = winning), as a fraction."""
    if entry_price <= 0:
        return 0.0
    if str(direction).upper() == "LONG":
        return (current_price - entry_price) / entry_price
    return (entry_price - current_price) / entry_price


def _pulse_adverse(pulse: Optional[Dict[str, Any]], config: MonitorConfig) -> bool:
    """True when the shared plane says this symbol is not a clean place to be.

    Deliberately direction-blind: a veto or collapsed tradability means "the conditions
    for a clean trade are gone", never "price will go down". A missing/stale pulse is NOT
    adverse — the monitor must not exit on data it cannot see (fail-open on the pulse gate
    specifically; the position's own SL still protects it).
    """
    if not pulse:
        return False
    if pulse.get("vetoes"):
        return True
    tradability = pulse.get("tradability")
    return tradability is not None and float(tradability) <= config.min_tradability


def evaluate_position(
    *,
    direction: str,
    entry_price: float,
    current_price: float,
    opened_at: Optional[datetime],
    now: datetime,
    horizon: Optional[str],
    pulse: Optional[Dict[str, Any]],
    state: MonitorState,
    config: MonitorConfig,
) -> tuple[MonitorDecision, MonitorState]:
    """Decide hold vs exit for one open position. Pure; returns the next state too.

    Gate order is by decisiveness: a broken time thesis and a protected profit both beat
    "conditions look shaky". None of the gates reads regime as a direction.
    """
    fav = favorable_return(direction, entry_price, current_price)
    peak_fav = max(state.peak_fav, fav)
    adverse = _pulse_adverse(pulse, config)
    adverse_streak = state.adverse_streak + 1 if adverse else 0
    next_state = MonitorState(peak_fav=peak_fav, adverse_streak=adverse_streak)

    if opened_at is not None:
        held = (now - opened_at).total_seconds()
        if held > config.max_hold_for(horizon):
            return MonitorDecision(EXIT, REASON_TIME_STOP), next_state

    if peak_fav >= config.lock_profit_pct and fav <= peak_fav - config.giveback_pct:
        return MonitorDecision(EXIT, REASON_PROFIT_PROTECT), next_state

    if adverse_streak >= config.adverse_exit_checks:
        return MonitorDecision(EXIT, REASON_CONDITIONS), next_state

    return MonitorDecision(HOLD), next_state


# -- the worker --------------------------------------------------------------

DEFAULT_POLL_SECONDS = 15

CHECK_HELD = "hold"
CHECK_EXITED = "exit"
CHECK_CLOSED = "closed"     # position already gone (SL/TP filled, or a prior exit)
CHECK_SKIPPED = "skipped"   # no live price yet — cannot evaluate this tick


@dataclass
class _Snapshot:
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    current_price: float
    opened_at: Optional[datetime]
    horizon: Optional[str]


class PositionMonitorWorker:
    """Watches one open position until it closes. Unmetered; independent of any session."""

    def __init__(
        self,
        session,
        symbol: str,
        pulse_client=None,
        config: Optional[MonitorConfig] = None,
        poll_seconds: int = DEFAULT_POLL_SECONDS,
        now_fn=None,
    ):
        self.session = session
        self.symbol = str(symbol).upper()
        self.pulse_client = pulse_client
        self.config = config or MonitorConfig()
        self.poll_seconds = poll_seconds
        self._now = now_fn or datetime.now
        self.state = MonitorState()
        self.checks = 0

    # -- data -----------------------------------------------------------------

    def _snapshot(self) -> Optional[_Snapshot]:
        """Normalized view of the position, or None once it is gone.

        Liveness + live price come from the engine (its tick loop is the source of truth
        for whether the position still exists). Thesis metadata (opened_at, horizon)
        comes from the risk tracker, which was fed at booking; when it is absent we still
        monitor, just without the time stop.
        """
        engine = getattr(self.session, "engine", None)
        if engine is None or not hasattr(engine, "get_positions"):
            return None
        pos = next(
            (p for p in engine.get_positions()
             if str(p.get("symbol", "")).upper() == self.symbol),
            None,
        )
        if pos is None:
            return None

        position_id = pos.get("position_id")
        tracked = getattr(getattr(self.session, "portfolio", None), "positions", {}).get(
            position_id
        )

        prices = getattr(engine, "current_prices", None) or {}
        current = prices.get(self.symbol)
        if current is None:
            current = _to_float(pos.get("markPrice"))

        return _Snapshot(
            symbol=self.symbol,
            direction=str(pos.get("positionSide") or getattr(tracked, "direction", "") or "LONG"),
            quantity=abs(_to_float(pos.get("positionAmt"))),
            entry_price=_to_float(pos.get("entryPrice")) or getattr(tracked, "entry_price", 0.0),
            current_price=_to_float(current),
            opened_at=getattr(tracked, "opened_at", None),
            horizon=getattr(tracked, "strategy_type", None),
        )

    async def _pulse(self) -> Optional[Dict[str, Any]]:
        """Fresh pulse for the symbol, or None. Staleness is fail-open HERE (the monitor
        must not stop on missing data); the veto gate simply doesn't fire without one."""
        if self.pulse_client is None:
            return None
        try:
            pulse = await self.pulse_client.get_or_none(self.symbol)
        except Exception:
            return None
        if pulse is None:
            return None
        return pulse if isinstance(pulse, dict) else getattr(pulse, "__dict__", None)

    # -- one check ------------------------------------------------------------

    async def check_once(self) -> str:
        snap = self._snapshot()
        if snap is None:
            return CHECK_CLOSED
        if not snap.current_price or snap.current_price <= 0 or snap.quantity <= 0:
            return CHECK_SKIPPED

        self.checks += 1
        pulse = await self._pulse()
        decision, self.state = evaluate_position(
            direction=snap.direction,
            entry_price=snap.entry_price,
            current_price=snap.current_price,
            opened_at=snap.opened_at,
            now=self._now(),
            horizon=snap.horizon,
            pulse=pulse,
            state=self.state,
            config=self.config,
        )
        if decision.action == EXIT:
            await self._exit(snap, decision.reason)
            return CHECK_EXITED
        return CHECK_HELD

    async def _exit(self, snap: _Snapshot, reason: str) -> None:
        """Reduce-only market close of the whole position. The engine's own close hook
        settles P&L and flows the close into the risk tracker (M1 wiring)."""
        from src.execution.paper_trading_engine import OrderSide

        side = OrderSide.SELL if snap.direction.upper() == "LONG" else OrderSide.BUY
        logger.info(
            f"[monitor] exiting {self.session.user_id} {self.symbol} "
            f"({snap.quantity} @ {snap.current_price}) — {reason}"
        )
        try:
            await self.session.engine.close_position(self.symbol, side, snap.quantity)
        except Exception as e:
            logger.warning(f"[monitor] exit failed for {self.symbol}: {e}")

    # -- loop -----------------------------------------------------------------

    async def run(self, shutdown: Optional[asyncio.Event] = None) -> None:
        logger.info(f"[monitor] watching {self.session.user_id} {self.symbol}")
        try:
            while True:
                if shutdown is not None and shutdown.is_set():
                    return
                result = await self.check_once()
                if result in (CHECK_CLOSED, CHECK_EXITED):
                    return
                try:
                    if shutdown is not None:
                        await asyncio.wait_for(shutdown.wait(), timeout=self.poll_seconds)
                        return
                    await asyncio.sleep(self.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(f"[monitor] released {self.session.user_id} {self.symbol}")


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# -- the supervisor ----------------------------------------------------------

DEFAULT_DISCOVERY_SECONDS = 5


class MonitorSupervisor:
    """Keeps one PositionMonitorWorker alive per open position, across all tenants.

    Category-2 singleton: one process, iterating tenants, holding no per-position state
    between passes. Discovery is idempotent — a monitor already running for a position is
    left alone; one whose position closed has its task reaped. On boot it therefore
    reconciles against whatever positions the engines actually hold (FR-MONITOR-4).

    Deliberately NOT gated by the engine switch or by sessions: monitoring is
    unconditional money-safety.
    """

    def __init__(
        self,
        registry,
        pulse_client=None,
        config: Optional[MonitorConfig] = None,
        poll_seconds: int = DEFAULT_POLL_SECONDS,
        discovery_seconds: int = DEFAULT_DISCOVERY_SECONDS,
    ):
        self.registry = registry
        self.pulse_client = pulse_client
        self.config = config or MonitorConfig()
        self.poll_seconds = poll_seconds
        self.discovery_seconds = discovery_seconds
        self.monitors: Dict[str, asyncio.Task] = {}
        self._shutdown = asyncio.Event()

    @staticmethod
    def _key(user_id: str, symbol: str) -> str:
        return f"{user_id}:{str(symbol).upper()}"

    async def discover_once(self) -> int:
        # Reap first, so a position that closed frees its slot before we re-scan.
        for key, task in list(self.monitors.items()):
            if task.done():
                self.monitors.pop(key, None)
                exc = task.exception() if not task.cancelled() else None
                if exc is not None:
                    logger.warning(f"[monitor] worker {key} died: {exc}")

        try:
            user_ids = await asyncio.to_thread(self.registry.active_user_ids)
        except Exception as e:
            logger.error(f"[monitor] tenant discovery failed: {e}")
            return len(self.monitors)

        for user_id in user_ids:
            try:
                session = self.registry.session(user_id)
            except Exception as e:
                logger.warning(f"[monitor] session load failed for {user_id}: {e}")
                continue
            engine = getattr(session, "engine", None)
            if engine is None or not hasattr(engine, "get_positions"):
                continue
            for pos in engine.get_positions():
                symbol = str(pos.get("symbol", "")).upper()
                if not symbol:
                    continue
                key = self._key(user_id, symbol)
                if key in self.monitors:
                    continue
                worker = PositionMonitorWorker(
                    session, symbol,
                    pulse_client=self.pulse_client,
                    config=self.config,
                    poll_seconds=self.poll_seconds,
                )
                self.monitors[key] = asyncio.get_running_loop().create_task(
                    worker.run(self._shutdown)
                )
                logger.info(f"[monitor] spawned {key}")

        return len(self.monitors)

    async def run(self) -> None:
        logger.info("[monitor] supervisor started")
        while not self._shutdown.is_set():
            try:
                await self.discover_once()
            except Exception as e:
                logger.error(f"[monitor] discovery pass failed: {e}")
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self.discovery_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("[monitor] supervisor stopped")

    async def stop(self, timeout: float = 10.0) -> None:
        self._shutdown.set()
        tasks = list(self.monitors.values())
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        self.monitors.clear()
