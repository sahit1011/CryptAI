"""Multi-user trading engine — shared analysis once, per-user portfolios.

Market analysis (data -> indicators -> regime -> candidate setups) is user-independent,
so the daemon computes it ONCE per cycle. Only RISK VALIDATION and ORDER EXECUTION are
per-user: every tenant has their own portfolio, risk config, and exchange account. This
module holds each tenant's resources (UserSession), discovers active tenants
(UserRegistry), and books one shared setup into each user's portfolio INDEPENDENTLY
(MultiUserExecutor) — fully isolated (per-user paper engine, portfolio tracker, and
Redis/WS namespacing from the earlier tenancy work). See docs/MULTI_TENANCY.md.

This is the "shared-engine-per-user-portfolio" model: efficient (analysis/LLM cost is
paid once, not per user) with strict per-tenant isolation of money and state.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from src.execution.paper_trading_engine import PaperTradingEngine
from src.execution.order_manager import OrderManager, ExecutionStrategy
from src.risk.portfolio_state_tracker import PortfolioStateTracker
from src.risk.deterministic_risk_calculator import DeterministicRiskCalculator, RiskParameters


@dataclass
class UserRiskConfig:
    """Per-tenant sizing/risk configuration."""
    initial_balance: float = 10000.0
    risk_params: Optional[RiskParameters] = None
    # Leverage the user's paper desk opens positions at. Before this existed the
    # engine silently ran its hardcoded default regardless of any preference —
    # and, worse, the value was persisted nowhere (R2.1 G1).
    leverage: int = 10


def _normalize_tps(setup: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize take-profit levels to the [{price, size}] shape execute_trade_setup wants,
    where `size` is a FRACTION of the position.

    Accepts: that shape already; AI-setup dicts carrying `percentage` (33.33 → 0.3333);
    or a list of bare prices (split evenly).
    """
    tps = setup.get("take_profit_levels") or setup.get("take_profits") or []
    if not tps:
        return []
    if isinstance(tps[0], dict):
        share = round(1.0 / len(tps), 4)
        out = []
        for tp in tps:
            size = tp.get("size")
            if size is None and tp.get("percentage") is not None:
                size = float(tp["percentage"]) / 100.0
            out.append({"price": float(tp["price"]), "size": float(size) if size else share})
        return out
    share = round(1.0 / len(tps), 4)
    return [{"price": float(p), "size": share} for p in tps]


class UserSession:
    """Per-tenant trading resources. Isolated: its own engine, portfolio, and risk calc."""

    def __init__(
        self,
        user_id: str,
        message_bus: Optional[Any] = None,
        state_manager: Optional[Any] = None,
        config: Optional[UserRiskConfig] = None,
        exchange: Optional[Any] = None,
    ):
        self.user_id = user_id
        self.message_bus = message_bus
        cfg = config or UserRiskConfig()
        # Per-user engine stamps user_id -> per-user Redis keys + per-user WS delivery.
        # A live exchange client (from the user's vault keys) can be injected as
        # `exchange`; default is an isolated paper engine.
        self.engine = exchange or PaperTradingEngine(
            initial_balance=cfg.initial_balance,
            message_bus=message_bus,
            state_manager=state_manager,
            user_id=user_id,
            leverage=cfg.leverage,
        )
        self.order_manager = OrderManager(self.engine)
        # snapshot_dir MUST be per-user: the tracker persists to a stable filename, so a
        # shared directory would have every tenant's tracker overwriting one snapshot —
        # and on restart each would hydrate from whichever tenant wrote last.
        self.portfolio = PortfolioStateTracker(
            initial_balance=cfg.initial_balance,
            state_manager=state_manager,
            snapshot_dir=f"data/snapshots/users/{user_id}",
        )
        self.risk = DeterministicRiskCalculator(self.portfolio, cfg.risk_params)
        # Closes flow back into the tracker so heat/daily-loss/trade-count limits see
        # them. Paper engine only; a live client doesn't emit this hook yet (M4 scope) —
        # its tracker positions then persist until reconcile, erring over-strict.
        if hasattr(self.engine, "on_position_closed"):
            self.engine.on_position_closed = self._on_position_closed
        # Rehydration tri-state (R2.1): None = no rehydration regime in play (tests,
        # the legacy single-bot path — booking allowed); False = a rehydration pass
        # is PENDING for this session and booking is refused until it completes
        # (persisted rows are the source of truth; trading blocked until diffed);
        # True = pass done. The daemon flips None→False at materialization.
        self.rehydrated: Optional[bool] = None

    async def rehydrate(self, trade_manager: Any) -> Any:
        """Rebuild this user's engine + risk tracker from their persisted rows.

        Fail-closed for money: on ANY failure `rehydrated` stays False and this
        user's bookings stay refused — a desk that might be missing an open
        position must not take new risk. Other users are unaffected (the daemon
        isolates per-user).
        """
        from src.core.rehydration import load_trades, rehydrate_engine

        open_rows, closed_rows = await asyncio.to_thread(
            load_trades, trade_manager, self.user_id
        )
        mirror = []
        sm = getattr(self.engine, "state_manager", None)
        if sm is not None:
            try:
                mirror = await sm.get_positions(user_id=self.user_id) or []
            except Exception:
                mirror = []  # a dead mirror is only a lost zombie report

        report = await rehydrate_engine(self.engine, open_rows, closed_rows, mirror)

        # Tracker second: reconcile from its snapshot (local-disk best-effort), then
        # overwrite its open set from the rows — position_id/opened_at must match the
        # engine's or monitors reset and the time stop measures from boot (G7).
        try:
            await self.portfolio.reconcile_on_startup(live_mode=False)
        except Exception as e:
            logger.warning(f"[rehydrate] tracker reconcile failed for {self.user_id}: {e}")
        for r in open_rows:
            try:
                await self.portfolio.add_position(
                    position_id=f"POS_{r.trade_id}",
                    symbol=str(r.symbol).upper(),
                    direction=str(r.direction).upper(),
                    entry_price=float(r.entry_price or 0.0),
                    position_size=float(r.position_size or 0.0),
                    stop_loss=float(r.stop_loss or 0.0),
                    take_profit_levels=[
                        float(p) for p in (r.take_profit_levels or [])
                        if isinstance(p, (int, float))
                    ],
                    risk_amount=float(r.risk_amount or 0.0),
                    strategy_type=r.strategy_type or "DAY_TRADE",
                    confidence_score=float(r.confidence_score or 0.0),
                    opened_at=r.entry_time,
                )
            except Exception as e:
                logger.warning(f"[rehydrate] tracker add failed for "
                               f"{self.user_id}/{r.trade_id}: {e}")

        self.rehydrated = True
        return report

    async def _on_position_closed(
        self, position_id: str, symbol: str, exit_price: float, pnl: float, reason: str
    ) -> None:
        await self.portfolio.close_position(position_id, exit_price, reason)

    async def evaluate_and_book(self, setup: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a SHARED setup against THIS user's portfolio; book it if approved.

        Returns a per-user result dict; never raises (errors are captured) so one
        tenant's failure can't abort the fan-out to others.
        """
        # Block-until-diffed (R2.1): while this session's rehydration pass is
        # pending or failed, its desk may be missing open positions — every risk
        # gate downstream (heat, position count, daily loss) would be vacuous.
        # Refusing here is the reconciliation doctrine's only money door.
        if self.rehydrated is False:
            return {"user_id": self.user_id, "approved": False,
                    "reasons": ["rehydrating — trading resumes once persisted state is restored"]}
        try:
            result = await self.risk.validate_trade_setup(
                symbol=setup["symbol"],
                direction=setup["direction"],
                entry_price=setup["entry_price"],
                stop_loss=setup["stop_loss"],
                take_profit_levels=[
                    tp["price"] if isinstance(tp, dict) else float(tp)
                    for tp in (setup.get("take_profit_levels") or [])
                ],
                recommended_position_size=setup.get("recommended_position_size", 0.0),
                risk_amount=setup.get("risk_amount", 0.0),
                confidence_score=setup.get("confidence_score", 0.0),
                market_regime=setup.get("market_regime"),
            )
            if not result.approved:
                return {"user_id": self.user_id, "approved": False,
                        "reasons": result.rejection_reasons}

            size = result.adjusted_position_size or setup.get("recommended_position_size", 0.0)
            if size <= 0:
                return {"user_id": self.user_id, "approved": False,
                        "reasons": ["non-positive position size"]}

            # Pre-flight the same-symbol case so the user gets the REAL reason. The
            # engine also refuses same-direction add-ons (its bracket would be
            # under-sized), but that path surfaces as a generic "entry order
            # rejected — no live market price or exchange error", which is simply
            # untrue here. Checking first also skips the wasted execution attempt.
            held = getattr(self.engine, "positions", {}).get(setup["symbol"])
            if held is not None:
                same_way = str(held.side).upper() == str(setup["direction"]).upper()
                if same_way:
                    return {
                        "user_id": self.user_id, "approved": False,
                        "reasons": [
                            f"already holding a {held.side} {setup['symbol']} position "
                            f"({held.quantity}) — close or scale out before adding"
                        ],
                    }

            execution = await self.order_manager.execute_trade_setup(
                symbol=setup["symbol"],
                direction=setup["direction"],
                entry_price=setup["entry_price"],
                stop_loss_price=setup["stop_loss"],
                take_profit_levels=_normalize_tps(setup),
                total_quantity=size,
                strategy=ExecutionStrategy.IMMEDIATE,
                metadata=setup.get("metadata"),
            )
            # The risk gate approved, but the EXECUTION can still fail (e.g. no
            # live price -> honest entry rejection, exchange error). Reporting
            # that as approved=True made the UI say "placed" while nothing was
            # booked — surface it as a rejection with the reason instead.
            exec_status = str(getattr(execution, "status", "") or "")
            if exec_status in ("failed", "timeout"):
                return {
                    "user_id": self.user_id, "approved": False,
                    "reasons": [
                        "execution failed — entry order rejected (no live market price or exchange error)"
                        if exec_status == "failed" else "entry order timed out unfilled",
                    ],
                }
            # Book into this user's risk tracker and log the entry to memory. Without
            # these, every later validate_trade_setup sees an empty portfolio (heat,
            # position-count, daily-loss limits all vacuous) and the memory agent's
            # exit update finds no trade row ("Trade not found").
            await self._record_booking(setup, size, execution)

            # Publish this tenant's updated portfolio (stamped with their user_id).
            try:
                await self.engine.publish_portfolio_update()
            except Exception:
                pass
            return {
                "user_id": self.user_id,
                "approved": True,
                "execution_id": getattr(execution, "execution_id", None),
                "status": getattr(execution, "status", None),
                "size": size,
            }
        except Exception as e:
            logger.exception(f"[multi-user] booking failed for {self.user_id}: {e}")
            return {"user_id": self.user_id, "approved": False, "error": str(e)}

    async def _record_booking(self, setup: Dict[str, Any], size: float, execution: Any) -> None:
        """Feed the risk tracker and the memory agent after a successful booking.

        Best-effort by design: a bookkeeping failure must not unwind a booked trade —
        the position already exists in the engine either way.

        The id must join with the close side: the paper engine's close path derives
        trade_id as position.position_id minus the "POS_" prefix, so we read the engine's
        actual position for this symbol and reuse its id for both the tracker and the
        memory entry. Live engines (no .positions dict) fall back to execution_id.
        """
        symbol = setup["symbol"]
        pos = getattr(self.engine, "positions", {}).get(symbol)
        position_id = getattr(pos, "position_id", None) or getattr(execution, "execution_id", None)
        if not position_id:
            logger.warning(f"[multi-user] no position id to record for {self.user_id}/{symbol}")
            return
        entry_price = getattr(pos, "entry_price", None) or setup["entry_price"]
        tp_levels = [
            tp["price"] if isinstance(tp, dict) else float(tp)
            for tp in (setup.get("take_profit_levels") or [])
        ]
        # Any producer can hand us a setup without a dollar risk figure; derive it from
        # the bracket so the tracker's heat/R-multiple math never sees a zero.
        risk_amount = setup.get("risk_amount", 0.0) or 0.0
        if risk_amount <= 0:
            risk_amount = size * abs(entry_price - setup["stop_loss"])

        try:
            await self.portfolio.add_position(
                position_id=position_id,
                symbol=symbol,
                direction=setup["direction"],
                entry_price=entry_price,
                position_size=size,
                stop_loss=setup["stop_loss"],
                take_profit_levels=tp_levels,
                risk_amount=risk_amount,
                strategy_type=setup.get("strategy_type", "DAY_TRADE"),
                confidence_score=setup.get("confidence_score", 0.0) or 0.0,
            )
        except Exception as e:
            logger.warning(f"[multi-user] tracker add_position failed for {self.user_id}: {e}")

        if self.message_bus is None:
            return
        trade_id = str(position_id).replace("POS_", "")
        # Bracket-leg identity for rehydration (R2.1): the row must let a restart
        # rebuild the resting SL/TP legs with their real ids, prices, and per-leg
        # QUANTITY FRACTIONS — bare TP prices lose the sizes, and an evenly-split
        # guess would mis-size every partial-TP bracket it restores.
        entry_order = getattr(execution, "entry_order", None)
        sl_order = getattr(execution, "stop_loss_order", None)
        tp_orders = list(getattr(execution, "take_profit_orders", None) or [])
        tp_order_ids = []
        for o in tp_orders:
            qty = float(getattr(o, "quantity", 0.0) or 0.0)
            tp_order_ids.append({
                "order_id": getattr(o, "order_id", None),
                "price": float(getattr(o, "price", 0.0) or 0.0),
                "size": round(qty / size, 6) if size > 0 else 0.0,
            })
        try:
            await self.message_bus.publish(
                "memory_agent_inbox",
                {
                    "id": f"log_{trade_id}",
                    "correlation_id": f"log_{trade_id}",
                    "sender": "multi_user_executor",
                    "receiver": "memory_agent",
                    "type": "log_trade",
                    "payload": {
                        "trade_id": trade_id,
                        "user_id": self.user_id,
                        "symbol": symbol,
                        "direction": setup["direction"],
                        "entry_price": entry_price,
                        "entry_time": datetime.now().isoformat(),
                        "position_size": size,
                        "stop_loss": setup["stop_loss"],
                        "take_profit_levels": tp_levels,
                        "leverage": float(getattr(pos, "leverage", 0) or 0) or None,
                        "entry_order_id": getattr(entry_order, "order_id", None),
                        "sl_order_id": getattr(sl_order, "order_id", None),
                        "tp_order_ids": tp_order_ids,
                        "risk_amount": risk_amount,
                        "strategy_type": setup.get("strategy_type", ""),
                        "confidence_score": setup.get("confidence_score", 0.0) or 0.0,
                        "confluence_count": setup.get("confluence_count", 0) or 0,
                        "market_regime": setup.get("market_regime", "") or "",
                        "atr_at_entry": setup.get("atr_at_entry", 0.0) or 0.0,
                        "smc_patterns": setup.get("smc_patterns"),
                        "ict_setups": setup.get("ict_setups"),
                    },
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(f"[multi-user] log_trade publish failed for {self.user_id}: {e}")


class UserRegistry:
    """Discovers active tenants and caches their UserSessions."""

    def __init__(
        self,
        message_bus: Optional[Any] = None,
        state_manager: Optional[Any] = None,
        vault: Optional[Any] = None,
        config_for: Optional[Callable[[str], UserRiskConfig]] = None,
        seed_user_ids: Optional[List[str]] = None,
        mode_for: Optional[Callable[[str], str]] = None,
        exchange_builder: Optional[Callable[[str], Any]] = None,
        users_provider: Optional[Callable[[], List[str]]] = None,
    ):
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.vault = vault
        self._config_for = config_for or (lambda uid: UserRiskConfig())
        self._sessions: Dict[str, UserSession] = {}
        # Always-on tenants that don't need vault credentials — e.g. a demo/owner paper
        # account. Unioned with connected-key users below.
        self._seed_user_ids = list(seed_user_ids or [])
        # Optional: every onboarded user (paper is the default), so a normal signup
        # is a paper tenant without needing the seed list. Returns [] on failure.
        self._users_provider = users_provider or (lambda: [])
        # Per-user trading mode (off | paper | manual | auto). Default paper.
        self._mode_for = mode_for or (lambda uid: "paper")
        # Optional: build a LIVE per-user engine (from vault keys) for auto+connected
        # users. Returns None to fall back to the isolated paper engine.
        self._exchange_builder = exchange_builder or (lambda uid: None)
        # Rehydration hook (R2.1). When the daemon sets this, every NEWLY materialized
        # session is marked rehydration-pending (booking refused) and handed to the
        # hook, which schedules the async rows→engine pass. Covers sessions created
        # AFTER the boot pass: a first-touch materialization mid-run, and the
        # paper↔auto mode-change rebuild — both would otherwise hand out an engine
        # that has forgotten this user's open positions.
        self.on_session_created: Optional[Callable[["UserSession"], None]] = None

    def mode_for(self, user_id: str) -> str:
        """This user's trading mode (off | paper | manual | auto)."""
        try:
            return self._mode_for(user_id) or "paper"
        except Exception:
            return "paper"

    def active_user_ids(self) -> List[str]:
        """Tenants eligible to trade this cycle.

        The union of: users who have connected exchange credentials (present in the
        vault), any explicit seed users (paper/demo accounts), and any sessions already
        materialized this run. A user connecting keys via the onboarding flow shows up
        here automatically on the next cycle.
        """
        ids = set(self._seed_user_ids) | set(self._sessions.keys())
        try:
            ids |= set(self._users_provider())  # every onboarded (mode != off) user
        except Exception as e:
            logger.warning(f"[multi-user] users_provider failed: {e}")
        if self.vault is not None:
            try:
                ids |= set(self.vault.active_user_ids())  # optional convenience on the vault
            except AttributeError:
                pass
        return sorted(ids)

    def session(self, user_id: str, exchange: Optional[Any] = None) -> UserSession:
        mode = self.mode_for(user_id)
        s = self._sessions.get(user_id)
        # Reuse the cached session unless the mode changed (paper<->auto swaps the engine)
        # or an explicit engine override was passed.
        if s is not None and exchange is None and getattr(s, "built_mode", None) == mode:
            return s
        # Choose the engine: explicit override → given; auto + connected → LIVE client
        # (from vault keys via exchange_builder); everything else → isolated paper engine.
        live_engine = exchange
        if live_engine is None and mode == "auto":
            try:
                live_engine = self._exchange_builder(user_id)
            except Exception as e:
                logger.error(f"[multi-user] live engine build failed for {user_id}: {e}")
                live_engine = None
        s = UserSession(
            user_id,
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            config=self._config_for(user_id),
            exchange=live_engine,
        )
        s.built_mode = mode
        s.is_live = live_engine is not None
        self._sessions[user_id] = s
        if self.on_session_created is not None:
            # Mark pending SYNCHRONOUSLY so there is no window where the fresh,
            # empty engine can book; the hook schedules the actual async pass.
            s.rehydrated = False
            try:
                self.on_session_created(s)
            except Exception as e:
                logger.error(f"[multi-user] rehydration hook failed for {user_id}: {e} "
                             "— session stays booking-blocked (fail-closed)")
        return s


class MultiUserExecutor:
    """Books one shared setup into every active tenant's portfolio, independently."""

    def __init__(self, registry: UserRegistry):
        self.registry = registry

    async def book_for_all(self, setup: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fan a shared setup out to each active tenant, per their trading mode.

        off → ignore; manual → suggestion only (the user places it via /api/execute-setup);
        paper → book to their paper engine; auto → book to their connected exchange (or
        paper if none). Isolated + fault-tolerant per tenant.
        """
        # Defensive: never let a malformed setup abort the fan-out.
        if not isinstance(setup, dict) or not setup.get("symbol"):
            logger.warning(f"[multi-user] skipping invalid setup: {setup!r}")
            return []
        results: List[Dict[str, Any]] = []
        skipped = 0
        for user_id in self.registry.active_user_ids():
            mode = self.registry.mode_for(user_id)
            if mode in ("off", "manual"):
                skipped += 1
                continue
            session = self.registry.session(user_id)
            r = await session.evaluate_and_book(setup)
            r["mode"] = mode
            r["live"] = getattr(session, "is_live", False)
            results.append(r)
        approved = sum(1 for r in results if r.get("approved"))
        logger.info(
            f"[multi-user] setup {setup.get('symbol')} {setup.get('direction')}: "
            f"booked {approved}/{len(results)} (skipped {skipped} off/manual)"
        )
        return results


class MultiUserCoordinator:
    """Runnable multi-user daemon primitive.

    Owns the registry + executor and drives the shared-once/book-per-user cadence. The
    daemon supplies `analysis_provider` — an async callable that runs the USER-INDEPENDENT
    market analysis pipeline (data -> indicators -> regime -> candidate setups) ONCE and
    returns a list of setup dicts. Each cycle we run it once, then fan every setup out to
    all active tenants' portfolios. This is the integration seam between the existing
    analysis pipeline (orchestrator/agents) and the per-user execution layer.
    """

    def __init__(self, registry: UserRegistry):
        self.registry = registry
        self.executor = MultiUserExecutor(registry)
        self._running = False

    async def run_cycle(
        self, analysis_provider: Callable[[], Any]
    ) -> List[List[Dict[str, Any]]]:
        """One cycle: compute shared analysis ONCE, book every setup to every tenant."""
        setups = await analysis_provider()
        if not setups:
            return []
        return [await self.executor.book_for_all(s) for s in setups]

    async def run_forever(
        self, analysis_provider: Callable[[], Any], interval_seconds: int = 180
    ) -> None:
        """Run cycles on an interval until stop() is called (the daemon loop)."""
        import asyncio
        self._running = True
        logger.info(f"[multi-user] coordinator started (interval={interval_seconds}s)")
        while self._running:
            try:
                await self.run_cycle(analysis_provider)
            except Exception as e:
                logger.error(f"[multi-user] cycle error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False
