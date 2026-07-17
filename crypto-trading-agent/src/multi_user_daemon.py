"""Multi-user trading daemon — the SaaS engine.

Where `src/main.py` runs a single global bot (one analysis cycle -> one portfolio),
this daemon runs the **shared-analysis / per-user-portfolio** model (see
docs/MULTI_TENANCY.md):

    1. The user-INDEPENDENT market analysis (data -> indicators -> regime -> candidate
       setups) is computed ONCE per cycle by the orchestrator's analysis phases.
    2. Each resulting setup is fanned out to EVERY active tenant and booked into their
       OWN isolated portfolio (per-user paper engine, per-user Redis keys, per-user WS
       delivery), independently and fault-tolerantly.

Analysis/LLM cost is paid once; money and state stay strictly per tenant. This is the
process a deployment runs to serve many users from one analysis pipeline.

Tenants for a cycle = seed users (MULTI_USER_SEED_IDS, e.g. a demo/owner paper account)
UNION users who have connected exchange credentials in the vault. Connecting keys via the
onboarding flow adds a user automatically on the next cycle.

Run:  python -m src.multi_user_daemon
"""
import asyncio
import os
import signal
import sys
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from src.core.message_bus import MessageBus
from src.core.state_manager import StateManager
from src.core.orchestrator import TradingOrchestrator
from src.core.multi_user import UserRegistry, MultiUserCoordinator, UserRiskConfig
from src.agents.data_agent import DataCollectionAgent
from src.agents.analysis_agent import MarketAnalysisAgent
from src.agents.strategy_agent import StrategyGenerationAgent
from src.agents.memory_agent import MemoryAgent
from src.security.credential_vault import CredentialVault
from src.utils.pipeline_logger import PipelineLogger
from src.utils.config import get_config

load_dotenv()
plog = PipelineLogger()


class MultiUserTradingDaemon:
    """Runs shared analysis once per cycle and books each setup into every tenant."""

    def __init__(self):
        self.config = get_config()
        self.running = False

        self.message_bus: Optional[MessageBus] = None
        self.state_manager: Optional[StateManager] = None

        # Only the ANALYSIS agents run here. The single-bot Risk/Execution agents are
        # NOT started: per-user risk validation + booking is the coordinator's job.
        self.data_agent: Optional[DataCollectionAgent] = None
        self.analysis_agent: Optional[MarketAnalysisAgent] = None
        self.strategy_agent: Optional[StrategyGenerationAgent] = None
        self.memory_agent: Optional[MemoryAgent] = None

        self.orchestrator: Optional[TradingOrchestrator] = None
        self.vault: Optional[CredentialVault] = None
        self.registry: Optional[UserRegistry] = None
        self.coordinator: Optional[MultiUserCoordinator] = None
        self.engine_switch = None  # EngineSwitch, set once Redis is up
        self._loop_task: Optional[asyncio.Task] = None
        self._was_on = None  # tracks on/off transitions for one-time log lines

    # ------------------------------------------------------------------ setup
    async def initialize_infrastructure(self):
        plog.info("🔧 Initializing infrastructure...", agent="daemon", phase="startup")
        self.message_bus = MessageBus(redis_url=self.config.database.redis_url)
        await self.message_bus.connect()
        self.state_manager = StateManager()
        await self.state_manager.connect()
        from src.core.engine_switch import EngineSwitch
        self.engine_switch = EngineSwitch(self.state_manager.redis)
        plog.info("  └─ ✅ Infrastructure ready", agent="daemon")

    async def _add_agent(self, name: str, factory):
        """Construct + start one agent, tolerating failure in EITHER step.

        A missing LLM key (agent __init__ builds an embeddings client) or a momentary
        feed/broker outage at boot (the market-data WebSocket can't connect yet) must NOT
        crash the whole daemon — the orchestrator reaches agents over the message bus, so
        a missing one just makes that phase time out and run_analysis_cycle returns []
        (no setups) until the dependency recovers. Crashing would take every tenant
        offline over one flaky/unconfigured dependency. Returns the agent, or None if it
        couldn't be brought up (degraded mode).
        """
        try:
            agent = factory()
        except Exception as e:
            plog.warning(
                f"{name} could not be constructed ({type(e).__name__}: {str(e)[:120]}); "
                "running WITHOUT it (degraded — cycles stay empty until it's configured)",
                agent="daemon",
            )
            return None
        try:
            await agent.start()
        except Exception as e:
            plog.warning(
                f"{name} start failed ({type(e).__name__}: {str(e)[:120]}); continuing — "
                "it will reconnect and cycles stay empty until it recovers",
                agent="daemon",
            )
        return agent

    async def initialize_agents(self):
        """Start ONLY the shared analysis agents (data/analysis/strategy/memory)."""
        plog.info("🤖 Initializing analysis agents...", agent="daemon", phase="startup")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        database_url = os.getenv("DATABASE_URL", "sqlite:///./trading_data.db")

        # NOTE: the analysis + strategy agents read their LLM keys from get_config()
        # internally — their __init__ only takes (message_bus, state_manager).
        bus, sm = self.message_bus, self.state_manager
        self.data_agent = await self._add_agent(
            "Data Agent", lambda: DataCollectionAgent(message_bus=bus, state_manager=sm)
        )
        self.analysis_agent = await self._add_agent(
            "Analysis Agent", lambda: MarketAnalysisAgent(message_bus=bus, state_manager=sm)
        )
        self.strategy_agent = await self._add_agent(
            "Strategy Agent", lambda: StrategyGenerationAgent(message_bus=bus, state_manager=sm)
        )
        # Memory agent backs the orchestrator's regime detection (detect_regime node).
        # Its __init__ builds an embeddings client, so it needs an LLM key to construct.
        # DAEMON_DISABLE_AGENTS=memory skips it entirely — it pulls chromadb (heavy),
        # which matters on small instances (e.g. 512MB free tiers); the regime phase
        # then falls back to the analysis agent's regime estimate.
        disabled = {a.strip() for a in os.getenv("DAEMON_DISABLE_AGENTS", "").split(",") if a.strip()}
        if "memory" in disabled:
            plog.info("Memory Agent disabled via DAEMON_DISABLE_AGENTS", agent="daemon")
            self.memory_agent = None
        else:
            self.memory_agent = await self._add_agent(
                "Memory Agent",
                lambda: MemoryAgent(
                    message_bus=bus, state_manager=sm,
                    database_url=database_url, openai_api_key=openai_api_key,
                    initial_capital=float(os.getenv("INITIAL_BALANCE", "10000")),
                ),
            )
        up = [n for n, a in (("data", self.data_agent), ("analysis", self.analysis_agent),
                             ("strategy", self.strategy_agent), ("memory", self.memory_agent)) if a]
        plog.info(f"  └─ ✅ Analysis agents ready ({len(up)}/4 up: {', '.join(up) or 'none'})", agent="daemon")

    def initialize_multi_user(self):
        plog.info("👥 Initializing multi-user layer...", agent="daemon", phase="startup")
        # Traded instruments (config/env-driven): BTC + ETH + gold (PAXG) by default.
        # Analysis runs once per symbol each cycle; setups fan out to all tenants.
        self.symbols = list(self.config.trading.symbols) or ["BTCUSDT"]
        symbol = self.symbols[0]

        # Surface which LLM powers each use case (premium if keyed, else OpenRouter
        # open-source). Loud warning if nothing is configured — cycles will be empty.
        try:
            from src.utils.llm_router import LLMRouter
            router = LLMRouter(self.config.llm)
            plog.info(router.describe(), agent="daemon", phase="startup")
            if not router.any_llm_configured():
                plog.warning(
                    "No LLM key configured (set OPENROUTER_API_KEY for free open-source "
                    "models, or ANTHROPIC/OPENAI/GOOGLE for premium). Analysis, strategy "
                    "and insights are DISABLED until one is set — the daemon will run but "
                    "book nothing.",
                    agent="daemon",
                )
        except Exception as e:
            plog.warning(f"LLM router summary unavailable: {e}", agent="daemon")

        # Orchestrator provides the analysis_provider (its analysis-only cycle).
        self.orchestrator = TradingOrchestrator(
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            symbol=symbol,
            cycle_interval=int(os.getenv("CYCLE_INTERVAL", "180")),
        )

        # Vault -> discovers connected-key tenants. Optional (paper-only demo without it).
        try:
            self.vault = CredentialVault(self.config.database.postgres_url)
        except Exception as e:
            plog.warning(f"Vault unavailable ({e}); trading seed users only", agent="daemon")
            self.vault = None

        # Per-user trading mode (off/paper/manual/auto). Default paper if unavailable.
        try:
            from src.core.user_settings import UserSettingsStore
            self.settings_store = UserSettingsStore(self.config.database.postgres_url)
            mode_for = self.settings_store.mode_for
        except Exception as e:
            plog.warning(f"Settings store unavailable ({e}); all users default to paper", agent="daemon")
            self.settings_store = None
            mode_for = lambda uid: "paper"

        seed_ids = [s.strip() for s in os.getenv("MULTI_USER_SEED_IDS", "").split(",") if s.strip()]

        # Size each tenant by their SUBSCRIPTION PLAN (balance + risk limits). Falls
        # back to a flat default if the billing module can't load, so trading never
        # depends on billing being wired.
        try:
            from src.billing import plan_config
            config_for = lambda uid: plan_config(uid)
        except Exception as e:
            plog.warning(f"Billing plans unavailable ({e}); using flat default config", agent="daemon")
            default_balance = float(os.getenv("INITIAL_BALANCE", "10000"))
            config_for = lambda uid: UserRiskConfig(initial_balance=default_balance)

        self.registry = UserRegistry(
            message_bus=self.message_bus,
            state_manager=self.state_manager,
            vault=self.vault,
            config_for=config_for,
            seed_user_ids=seed_ids,
            mode_for=mode_for,
            exchange_builder=self._build_live_engine,   # Phase C: vault keys -> live engine
            # Every onboarded user (paper by default) is a tenant — no seed list needed.
            users_provider=(self.settings_store.active_user_ids if self.settings_store else None),
        )
        self.coordinator = MultiUserCoordinator(self.registry)
        plog.info(
            f"  └─ ✅ Multi-user layer ready | seed_users={len(seed_ids)} | "
            f"vault={'on' if self.vault else 'off'} | settings={'on' if self.settings_store else 'off'}",
            agent="daemon",
        )

    def _build_live_engine(self, user_id: str):
        """Build a LIVE per-user trading engine from the tenant's vault keys (Phase C).

        Returns a LiveExecutionEngine that satisfies the same interface the per-user
        OrderManager calls (execute_trade_setup / get_positions / publish_*), backed by
        the user's connected exchange (testnet-gated). Returns None → the session falls
        back to the isolated paper engine.
        """
        if self.vault is None or self.settings_store is None:
            return None
        try:
            exchange = self.settings_store.get(user_id).get("active_exchange", "bingx")
            creds = self.vault.get(user_id, exchange)
            if not creds:
                return None
            from src.execution.live_execution_engine import LiveExecutionEngine
            api_key, api_secret = creds
            return LiveExecutionEngine(
                user_id=user_id, exchange_name=exchange,
                api_key=api_key, api_secret=api_secret,
                message_bus=self.message_bus, state_manager=self.state_manager,
            )
        except Exception as e:
            plog.warning(f"[live] engine build failed for {user_id}: {e}", agent="daemon")
            return None

    # ------------------------------------------------------------------ run
    async def start(self):
        if self.running:
            return
        plog.info("🚀 Starting Multi-User Trading Daemon", agent="daemon", phase="startup")
        # Error tracking (Sentry) — no-op unless SENTRY_DSN is set.
        from src.utils.monitoring import init_monitoring
        init_monitoring("daemon")
        await self.initialize_infrastructure()
        await self.initialize_agents()
        self.initialize_multi_user()

        interval = int(os.getenv("CYCLE_INTERVAL", "180"))
        active = self.registry.active_user_ids()
        plog.info(
            f"✅ Daemon started | cycle={interval}s | active_tenants={len(active)} "
            f"| symbols={','.join(self.symbols)}",
            agent="daemon",
            phase="startup_complete",
        )
        self.running = True
        # analysis_provider = shared analysis cycle, wrapped to also PUBLISH each setup as
        # a suggestion (Signals feed) before the coordinator books it per-user.
        self._loop_task = asyncio.create_task(
            self.coordinator.run_forever(self._analysis_with_signals, interval)
        )

    async def _analysis_with_signals(self):
        """Run shared analysis for EACH traded symbol, publish setups, return them all.

        Analysis is per-symbol but user-independent, so it runs once per symbol per cycle
        (not per user); every resulting setup then fans out to all active tenants.

        GATED by the owner's AI-engine switch: while OFF, we return immediately WITHOUT
        calling the LLM — this is what protects the (free) API quota from unattended
        burn. The cycle timer keeps ticking; each tick is a cheap Redis check until the
        owner turns the engine on.
        """
        if self.engine_switch is not None:
            on = await self.engine_switch.is_on()
            if on != self._was_on:  # log only on transition, not every idle cycle
                plog.info(
                    f"🟢 AI engine ON — running analysis" if on
                    else "⏸️  AI engine OFF — analysis paused (owner turns it on to run)",
                    agent="daemon",
                )
                self._was_on = on
            if not on:
                return []

        all_setups = []
        for sym in self.symbols:
            try:
                setups = await self.orchestrator.run_analysis_cycle(sym)
            except Exception as e:
                plog.warning(f"[analysis] {sym} cycle failed: {e}", agent="daemon")
                continue
            if setups:
                await self._publish_setups(setups)
                all_setups.extend(setups)
        return all_setups

    async def _publish_setups(self, setups):
        """Broadcast each candidate setup to the Signals feed (untenanted — shared).

        The API's WS bridge subscribes to `trade_signals` and forwards these to every
        connected dashboard as `trade_setup` messages. Suggestions are identical for all
        users; only execution is per-tenant.
        """
        if not setups or not self.message_bus:
            return
        for s in setups:
            try:
                await self.message_bus.publish("trade_signals", {
                    "type": "trade_setup",
                    "payload": {
                        "symbol": s.get("symbol"),
                        "direction": s.get("direction"),
                        "entry_price": s.get("entry_price"),
                        "stop_loss": s.get("stop_loss"),
                        "take_profit_levels": s.get("take_profit_levels") or s.get("take_profits") or [],
                        "confidence_score": s.get("confidence_score", s.get("confidence")),
                        "risk_reward": s.get("risk_reward"),
                        "market_regime": s.get("market_regime"),
                        "strategy_type": s.get("strategy_type"),
                        "reasoning": s.get("reasoning") or s.get("notes"),
                        # carried through so a MANUAL execute uses the strategy's sizing
                        "recommended_position_size": s.get("recommended_position_size"),
                        "risk_amount": s.get("risk_amount"),
                    },
                }, persist=False)
            except Exception as e:
                plog.warning(f"[signals] publish failed: {e}", agent="daemon")
        plog.info(f"📡 [signals] published {len(setups)} setup suggestion(s)", agent="daemon")

    async def stop(self):
        if not self.running:
            return
        plog.info("🛑 Stopping Multi-User Trading Daemon", agent="daemon", phase="shutdown")
        self.running = False
        if self.coordinator:
            self.coordinator.stop()
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
        for agent in (self.memory_agent, self.strategy_agent, self.analysis_agent, self.data_agent):
            if agent:
                try:
                    await agent.stop()
                except Exception as e:
                    plog.warning(f"agent stop error: {e}", agent="daemon")
        if self.state_manager:
            await self.state_manager.disconnect()
        if self.message_bus:
            await self.message_bus.disconnect()
        plog.info("  └─ ✅ Daemon stopped", agent="daemon", phase="shutdown_complete")

    async def run_forever(self):
        await self.start()
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            plog.info("Received interrupt", agent="daemon")
        finally:
            await self.stop()


async def main():
    # Structured logging (LOG_JSON=true → JSON lines for aggregators).
    from src.utils.logging_setup import setup_logging
    setup_logging()
    logger.add("logs/multi_user_daemon_{time:YYYY-MM-DD}.log", rotation="1 day",
               retention="30 days", level="DEBUG")

    daemon = MultiUserTradingDaemon()

    def signal_handler(sig, frame):
        plog.info("Received shutdown signal", agent="daemon")
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await daemon.run_forever()
    except Exception as e:
        plog.error(f"Fatal error: {e}", agent="daemon")
        await daemon.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
