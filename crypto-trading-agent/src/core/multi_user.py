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
from dataclasses import dataclass
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
        cfg = config or UserRiskConfig()
        # Per-user engine stamps user_id -> per-user Redis keys + per-user WS delivery.
        # A live exchange client (from the user's vault keys) can be injected as
        # `exchange`; default is an isolated paper engine.
        self.engine = exchange or PaperTradingEngine(
            initial_balance=cfg.initial_balance,
            message_bus=message_bus,
            state_manager=state_manager,
            user_id=user_id,
        )
        self.order_manager = OrderManager(self.engine)
        self.portfolio = PortfolioStateTracker(
            initial_balance=cfg.initial_balance, state_manager=state_manager
        )
        self.risk = DeterministicRiskCalculator(self.portfolio, cfg.risk_params)

    async def evaluate_and_book(self, setup: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a SHARED setup against THIS user's portfolio; book it if approved.

        Returns a per-user result dict; never raises (errors are captured) so one
        tenant's failure can't abort the fan-out to others.
        """
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
