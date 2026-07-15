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
        self._loop_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ setup
    async def initialize_infrastructure(self):
        plog.info("🔧 Initializing infrastructure...", agent="daemon", phase="startup")
        self.message_bus = MessageBus(redis_url=self.config.database.redis_url)
        await self.message_bus.connect()
        self.state_manager = StateManager()
        await self.state_manager.connect()
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
        symbol = os.getenv("TRADING_SYMBOL", "BTCUSDT")

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
        )
        self.coordinator = MultiUserCoordinator(self.registry)
        plog.info(
            f"  └─ ✅ Multi-user layer ready | seed_users={len(seed_ids)} | "
            f"vault={'on' if self.vault else 'off'}",
            agent="daemon",
        )

    # ------------------------------------------------------------------ run
    async def start(self):
        if self.running:
            return
        plog.info("🚀 Starting Multi-User Trading Daemon", agent="daemon", phase="startup")
        await self.initialize_infrastructure()
        await self.initialize_agents()
        self.initialize_multi_user()

        interval = int(os.getenv("CYCLE_INTERVAL", "180"))
        active = self.registry.active_user_ids()
        plog.info(
            f"✅ Daemon started | cycle={interval}s | active_tenants={len(active)} "
            f"| symbol={self.orchestrator.symbol}",
            agent="daemon",
            phase="startup_complete",
        )
        self.running = True
        # analysis_provider = the orchestrator's shared, user-independent analysis cycle.
        self._loop_task = asyncio.create_task(
            self.coordinator.run_forever(self.orchestrator.run_analysis_cycle, interval)
        )

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
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level="INFO",
    )
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
