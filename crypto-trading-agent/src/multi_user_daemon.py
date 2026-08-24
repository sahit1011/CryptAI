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
import time
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
        self.monitor_supervisor = None  # MonitorSupervisor, set in start()
        self._loop_task: Optional[asyncio.Task] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._stream_task: Optional[asyncio.Task] = None  # demand-gates market streams
        self._was_on = None  # tracks on/off transitions for one-time log lines
        self._last_analysis_at = None  # paces the expensive cycle; see _analysis_with_signals
        # Default must match SESSION_CYCLE_SECONDS (session_manager.py) and render.yaml —
        # the UI's staleness check measures against the published cadence, so a divergent
        # default here makes local/dev sessions look stale against a cadence nobody uses.
        self.cycle_interval = int(os.getenv("CYCLE_INTERVAL", "180"))

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
            # One source of truth: two readings of CYCLE_INTERVAL with different
            # defaults would disagree the moment the env var is unset.
            cycle_interval=self.cycle_interval,
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
        self.initialize_session_plane()

    def _build_synthesizer(self):
        """The per-user chooser, or None to fall back to the deterministic pick.

        Returns None whenever no provider is configured — synthesis is an enhancement,
        and a session must still produce a proposal on a deployment with no LLM key.

        Uses the SYNC OpenAI client against OpenRouter deliberately: AsyncOpenAI
        misbehaves there (see strategy_agent), and `build_openai_compatible_chat` runs it
        off the event loop so one user's call cannot stall every other session's worker.
        """
        try:
            from src.core.synthesis import build_openai_compatible_chat, build_synthesizer

            api_key = getattr(self.config.llm, "openrouter_api_key", None)
            if not api_key:
                plog.warning(
                    "no OpenRouter key — setups will be picked deterministically, "
                    "identically for every user",
                    agent="daemon",
                )
                return None

            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=float(getattr(self.config.llm, "timeout", None) or 60),
            )
            # The SAME rotation the agents use. OpenRouter's free catalogue rotates and
            # 429s, so a pinned model is a single point of failure that has already made
            # this engine silently produce nothing once.
            models = list(getattr(self.config.llm, "openrouter_free_models", None) or [])
            if not models:
                plog.warning(
                    "no OpenRouter models configured; deterministic picks only",
                    agent="daemon",
                )
                return None
            plog.info(
                f"  └─ ✅ Per-user synthesis on | {len(models)} model(s), first {models[0]}",
                agent="daemon",
            )
            return build_synthesizer(
                build_openai_compatible_chat(client, models), model=models[0]
            )
        except Exception as e:
            plog.warning(
                f"synthesis unavailable ({e}); falling back to the deterministic pick",
                agent="daemon",
            )
            return None

    def initialize_session_plane(self):
        """M2 control plane: metered sessions do real work in THIS process.

        Each store is optional (matching the daemon's fault-tolerant style): a failed
        init disables the session pipeline but never takes down broadcast trading.
        The pool itself starts in start() once the loop is running.
        """
        self.session_manager = None
        self.preferences_store = None
        self.proposal_service = None
        self.setup_cache = None
        self.worker_pool = None
        # The shared signal plane is opt-in until the Rust engine has a host: wiring the
        # client against an absent engine would fail-closed EVERY session (invariant 2)
        # and starve the monitors of pulse reads. Flip SIGNAL_PLANE_ENABLED once
        # market:pulse:* is live in this Redis. Both the session pipeline and the
        # position monitors consume this one client.
        self.pulse_client = None
        if os.getenv("SIGNAL_PLANE_ENABLED", "").strip().lower() == "true":
            try:
                from src.signals.pulse_client import PulseClient
                # MessageBus exposes its client as `redis_client` (it is None until
                # connect()); `redis` is only the module alias, so reading that name
                # silently yielded None and left pulse gating permanently off.
                redis_client = getattr(self.message_bus, "redis_client", None)
                if redis_client is not None:
                    self.pulse_client = PulseClient(redis_client)
                else:
                    plog.warning(
                        "SIGNAL_PLANE_ENABLED but message bus has no redis client; "
                        "sessions and monitors will run ungated",
                        agent="daemon",
                    )
            except Exception as e:
                plog.warning(f"PulseClient unavailable ({e}); running ungated", agent="daemon")
        try:
            from src.core.preferences import PreferencesStore
            from src.core.proposals import ProposalService
            from src.core.session_manager import SessionManager
            from src.core.session_pipeline import SharedSetupCache, build_analyze_fn
            from src.core.session_worker import SessionWorkerPool

            db_url = self.config.database.postgres_url
            self.session_manager = SessionManager(db_url)
            self.preferences_store = PreferencesStore(db_url)
            self.proposal_service = ProposalService(db_url)
            self.setup_cache = SharedSetupCache()

            self.worker_pool = SessionWorkerPool(
                self.session_manager,
                self.preferences_store,
                build_analyze_fn(
                    session_manager=self.session_manager,
                    proposal_service=self.proposal_service,
                    setup_cache=self.setup_cache,
                    synthesize=self._build_synthesizer(),
                ),
                pulse_client=self.pulse_client,
                # Lets each worker read its user's open positions, so synthesis can see
                # what they already hold instead of always being told "none".
                state_manager=self.state_manager,
                # Deliberately NOT kill_switch=self.engine_switch. A started scan is
                # already authorized: the capacity gate on POST /api/session/start
                # refuses one outright (503, no row, no clock) when analysis is off, so
                # a session that exists was allowed to exist. Gating the pool as well
                # meant flipping the switch mid-scan silently stopped the workers while
                # the user's metered clock kept running — charging them for a scan that
                # could not produce anything. Capacity lost mid-scan is handled where it
                # belongs, by the tick loop, which ends the session and refunds the dead
                # time rather than starving it in place.
            )
            plog.info(
                f"  └─ ✅ Session plane ready | pulse_gating="
                f"{'on' if self.pulse_client else 'off (engine undeployed)'}",
                agent="daemon",
            )
        except Exception as e:
            plog.warning(
                f"Session plane unavailable ({e}); metered sessions will not run analysis",
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
        # Multi-user layer + the tenant command channel come up BEFORE the slow
        # agent hydration (candle backfill can take minutes): the API dispatches
        # PAPER closes over `user_commands`, and a command arriving during boot
        # must be handled, not silently dropped. (Keyed users close directly at
        # the exchange in the API process.) initialize_multi_user only needs
        # infrastructure, so this reorder is safe.
        self.initialize_multi_user()
        await self.message_bus.subscribe("user_commands", self._handle_user_command)
        await self.initialize_agents()

        # Poll fast so a new scan is noticed within seconds; _analysis_with_signals
        # enforces the real cadence and skips entirely when nobody is scanning, so a
        # short tick costs nothing when idle (run_cycle returns on empty setups).
        interval = int(os.getenv("ANALYSIS_POLL_SECONDS", "30"))
        active = self.registry.active_user_ids()
        plog.info(
            f"✅ Daemon started | poll={interval}s cadence={self.cycle_interval}s | active_tenants={len(active)} "
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
        # Price ticks make paper brackets SELF-MANAGE: resting SL/TP legs fill
        # when the live price crosses them, positions mark to market, and the
        # UI's uPnL stays current — without a human touching anything.
        self._tick_task = asyncio.create_task(self._price_tick_loop())
        # Stream gate: the DataAgent subscribes market data only while there is a
        # live consumer — a scanning session (full feed) or an open position
        # (price-only feed). Idle deployments stream nothing (R0.2).
        self._stream_task = None
        if self.data_agent is not None:
            self._stream_task = asyncio.create_task(self._stream_gate_loop())
        # Session plane: one worker per ACTIVE session (metered, per-user), plus the
        # sweeper that expires lapsed proposals and un-pauses their sessions.
        self._pool_task = None
        self._sweeper_task = None
        if self.worker_pool is not None:
            self._pool_task = asyncio.create_task(self.worker_pool.run())
            self._sweeper_task = asyncio.create_task(self._proposal_sweep_loop())
        # Position monitors — deliberately independent of the session plane above:
        # monitoring open positions is unconditional money-safety, so it starts whenever
        # the registry exists, even if the proposal/session stores failed to init.
        self._monitor_task = None
        if self.registry is not None:
            from src.core.monitor_worker import MonitorSupervisor
            self.monitor_supervisor = MonitorSupervisor(
                self.registry,
                pulse_client=self.pulse_client,
                state_manager=self.state_manager,
            )
            self._monitor_task = asyncio.create_task(self.monitor_supervisor.run())
            plog.info("  └─ ✅ Position monitors online (unmetered)", agent="daemon")

    async def _approve_proposal(self, session, user_id: str, message: dict) -> dict:
        """Approval-time re-validation, then execution through the user's own session.

        The shelf-life/price-drift/invalidation gates (ProposalService.revalidate) run
        HERE, against this process's live price — a proposal approved minutes after it
        was made is not the same trade, and the thing that decides whether it still is
        must see current prices. Refusals are honest: no live price means no fill.
        """
        # `retryable` is the API's contract for what to do with the session on refusal:
        # True → the proposal is still PROPOSED (transient condition: price drift, no
        # price feed) so the session must STAY paused and the user may retry; False →
        # the proposal is decided/absent, resume scanning. Without the flag the API
        # resumed scanning on every refusal, stranding a still-live proposal in a state
        # nothing could reach (the price_moved dead zone).
        if self.proposal_service is None or self.preferences_store is None:
            return {"approved": False, "reason": "session_plane_unavailable",
                    "retryable": True}

        proposal_id = str((message or {}).get("proposal_id") or "")
        proposal = (
            await asyncio.to_thread(self.proposal_service.get, proposal_id, user_id)
            if proposal_id
            else await asyncio.to_thread(self.proposal_service.get_pending, user_id)
        )
        if proposal is None or proposal.get("status") != "proposed":
            return {"approved": False, "reason": "no_pending_proposal",
                    "retryable": False}

        symbol = proposal["symbol"]
        prices = getattr(getattr(session, "engine", None), "current_prices", None) or {}
        price = prices.get(symbol)
        if not price or float(price) <= 0:
            return {"approved": False, "reason": "no_live_price", "retryable": True}

        prefs = await asyncio.to_thread(self.preferences_store.get, user_id)
        reval = await asyncio.to_thread(
            lambda: self.proposal_service.revalidate(
                proposal_id=proposal["proposal_id"],
                user_id=user_id,
                current_price=float(price),
                prefs=prefs,
            )
        )
        if not reval.ok:
            # revalidate marks EXPIRED/INVALIDATED itself; those are terminal. Anything
            # else (price drift, transient sizing refusal) left the row PROPOSED.
            still_proposed = (
                await asyncio.to_thread(
                    self.proposal_service.get, proposal["proposal_id"], user_id
                )
                or {}
            ).get("status") == "proposed"
            return {"approved": False, "reason": reval.reason,
                    "retryable": still_proposed}

        setup = {
            "symbol": symbol,
            "direction": proposal["direction"],
            "entry_price": proposal["entry_price"],
            "stop_loss": proposal["stop_loss"],
            "take_profit_levels": proposal["take_profit_levels"],
            "recommended_position_size": reval.position_size,
            "risk_amount": proposal["risk_amount"],
            # A None score would auto-reject at the risk gate's confidence floor; the
            # human's approval IS the confidence here (same rule as manual tickets).
            "confidence_score": (
                proposal["confidence_score"]
                if proposal.get("confidence_score") is not None else 1.0
            ),
            "market_regime": proposal.get("market_regime"),
            "strategy_type": proposal.get("strategy_type"),
            "metadata": {
                "proposal_id": proposal["proposal_id"],
                "session_id": proposal["session_id"],
            },
        }
        result = await session.evaluate_and_book(setup)

        from src.core.proposals import EXECUTED, REJECTED
        if result.get("approved"):
            await asyncio.to_thread(
                self.proposal_service.mark,
                proposal["proposal_id"], EXECUTED, result.get("execution_id"),
            )
            if reval.resized:
                result["resized"] = True
                result["original_size"] = reval.original_size
        else:
            # The trade the user approved was not available (risk gate or execution
            # refused). Mark it decided rather than leaving it to be re-approved.
            await asyncio.to_thread(
                self.proposal_service.mark, proposal["proposal_id"], REJECTED
            )
            result.setdefault(
                "reason", "; ".join(result.get("reasons") or []) or "execution_rejected"
            )
            result["retryable"] = False
        return result

    async def _sweep_once(self) -> None:
        """One sweep pass: expire lapsed proposals, then repair paused sessions.

        Restores the invariant that a pending proposal and a paused session imply each
        other. A paused session with no live proposal resumes scanning — UNLESS its own
        proposal was EXECUTED (the approve reply was lost in flight): then the trade is
        already open and the session must end as trade_opened, not resume and book a
        second one.
        """
        from src.core.session_manager import SETUP_PROPOSED, TRADE_OPENED, SessionError

        expired = await asyncio.to_thread(self.proposal_service.expire_stale)
        if expired:
            plog.info(f"[sessions] expired {expired} lapsed proposal(s)", agent="daemon")
        for session in await asyncio.to_thread(self.session_manager.active_sessions):
            if session.get("status") != SETUP_PROPOSED:
                continue
            pending = await asyncio.to_thread(
                self.proposal_service.get_pending, session["user_id"]
            )
            # get_pending returns a lapsed row marked "expired", not None.
            if pending is not None and pending.get("status") == "proposed":
                continue
            latest = await asyncio.to_thread(
                self.proposal_service.latest_for_session,
                session["user_id"], session["session_id"],
            )
            try:
                if latest is not None and latest.get("status") == "executed":
                    await asyncio.to_thread(
                        self.session_manager.approve, session["session_id"],
                        "recovered: proposal was executed",
                    )
                    await asyncio.to_thread(
                        self.session_manager.end, session["session_id"], TRADE_OPENED,
                        "trade executed — approve reply was lost; recovered by sweep",
                    )
                else:
                    await asyncio.to_thread(
                        self.session_manager.reject,
                        session["session_id"],
                        "proposal expired — resuming scan",
                    )
            except SessionError:
                pass  # racing an approve/end; the machine stays consistent

    async def _proposal_sweep_loop(self, interval_seconds: int = 30):
        while self.running:
            try:
                await self._sweep_once()
            except Exception as e:
                plog.warning(f"[sessions] sweep pass failed: {e}", agent="daemon")
            await asyncio.sleep(interval_seconds)

    async def _handle_user_command(self, message):
        """Tenant-scoped commands from the API (bus channel `user_commands`).

        `close_position` / `close_all` for PAPER accounts: those positions live in
        this process's long-lived per-user engines, so the API can't close them
        itself. Settlement runs through the engine's own reduce-only path (real
        fill/P&L bookkeeping — never a raw Redis delete of a live position). If
        the engine no longer tracks the record (daemon restarted), the stale Redis
        row is dropped explicitly and logged as unsettled — honest cleanup, not a
        fake settlement.
        """
        try:
            cmd = (message or {}).get("type")
            user_id = (message or {}).get("user_id")
            if not user_id or cmd not in (
                "close_position", "close_all", "execute_setup", "cancel_order",
                "approve_proposal",
            ):
                return
            from src.execution.paper_trading_engine import OrderSide

            session = self.registry.session(user_id) if self.registry else None
            engine = getattr(session, "engine", None)
            if engine is None or not hasattr(engine, "get_positions"):
                await self._reply_command(message, {"approved": False, "error": "engine unavailable"})
                return

            # --- execute_setup: book a manual/paper bracket in THIS process's
            # long-lived engine, so its position and resting SL/TP legs live where
            # closes settle and orders are listable. The API awaits the reply key.
            if cmd == "execute_setup":
                setup = (message or {}).get("setup")
                if not isinstance(setup, dict) or not setup.get("symbol"):
                    await self._reply_command(message, {"approved": False, "error": "malformed setup"})
                    return
                result = await session.evaluate_and_book(setup)
                await self._reply_command(message, result)
                return

            # --- approve_proposal: re-validate at the LIVE price, then execute.
            # The API owns the session state machine; this process owns prices,
            # proposals, and the user's engine — so the money decision happens here.
            if cmd == "approve_proposal":
                result = await self._approve_proposal(session, user_id, message)
                await self._reply_command(message, result)
                return

            # --- cancel_order: cancel one resting order in the engine, republish.
            if cmd == "cancel_order":
                order_id = str((message or {}).get("order_id") or "")
                symbol = str((message or {}).get("symbol") or "")
                if not order_id:
                    await self._reply_command(message, {"canceled": False, "error": "order_id required"})
                    return
                result = await engine.cancel_order(symbol or order_id, order_id)
                canceled = not (isinstance(result, dict) and result.get("error"))
                if hasattr(engine, "publish_portfolio_update"):
                    await engine.publish_portfolio_update()
                await self._reply_command(message, {
                    "canceled": canceled,
                    **({"error": result.get("error")} if isinstance(result, dict) and result.get("error") else {}),
                })
                return

            symbol = str((message or {}).get("symbol") or "").replace("-", "").upper()
            positions = engine.get_positions() or []
            targets = [
                p for p in positions
                if cmd == "close_all"
                or str(p.get("symbol", "")).replace("-", "").upper() == symbol
            ]

            if not targets:
                plog.warning(
                    f"[user_commands] {cmd}: no open position in-engine for {user_id} "
                    f"{symbol or '(all)'} — clearing stale record if present",
                    agent="daemon",
                )
                # Zombie cleanup: a record the engine no longer tracks can never
                # settle; drop it from Redis so the UI reflects reality, and
                # publish the surviving set so connected clients update live.
                if self.state_manager is not None:
                    stored = await self.state_manager.get_positions(user_id=user_id)
                    if cmd == "close_all":
                        keep = []
                    elif symbol:
                        keep = [
                            p for p in stored
                            if str(p.get("symbol", "")).replace("-", "").upper() != symbol
                        ]
                    else:
                        return
                    if len(keep) != len(stored):
                        await self.state_manager.replace_positions(keep, user_id=user_id)
                        await self.message_bus.publish("execution_status", {
                            "type": "position_update",
                            "payload": keep,
                            "user_id": user_id,
                        })
                return

            for p in targets:
                qty = abs(float(p.get("positionAmt") or 0))
                if qty <= 0:
                    continue
                side = (
                    OrderSide.SELL
                    if str(p.get("positionSide", "LONG")).upper() == "LONG"
                    else OrderSide.BUY
                )
                await engine.close_position(symbol=p.get("symbol"), side=side, quantity=qty)
                # The position is gone — its surviving bracket legs (SL/TP) must
                # go with it, or naked reduce-only orders linger and can fill
                # into a phantom position later.
                closed_symbol = str(p.get("symbol") or "")
                if hasattr(engine, "get_open_orders"):
                    for order in engine.get_open_orders() or []:
                        if str(order.get("symbol", "")) == closed_symbol and order.get("reduceOnly"):
                            try:
                                await engine.cancel_order(closed_symbol, order.get("orderId"))
                            except Exception:
                                pass
                plog.info(
                    f"[user_commands] closed {p.get('symbol')} for {user_id} (paper, user-requested)",
                    agent="daemon",
                )
            if hasattr(engine, "publish_portfolio_update"):
                await engine.publish_portfolio_update()
        except Exception as e:
            plog.error(f"[user_commands] error handling command: {e}", agent="daemon")
            try:
                await self._reply_command(message, {"approved": False, "error": "daemon error — see logs"})
            except Exception:
                pass

    async def _reply_command(self, message, result) -> None:
        """Write a command's result to its short-lived Redis reply key.

        The API polls `cmd_reply:{correlation_id}` (60s TTL) — a deliberately
        boring request/response transport that works identically whether the
        daemon runs embedded in the API process or as a separate container.
        """
        cid = (message or {}).get("correlation_id")
        if not cid or self.state_manager is None:
            return
        await self.state_manager.set(f"cmd_reply:{cid}", result, ttl=60)

    # Tick cadence: fast enough that a crossed SL/TP fills within seconds,
    # slow enough to be negligible load (a few dict scans per user).
    PRICE_TICK_INTERVAL_S = 3.0
    # Publish portfolio (mark/uPnL) even without fills every N ticks (~15s).
    PUBLISH_EVERY_N_TICKS = 5

    async def _price_tick_loop(self):
        """Feed live prices into every cached per-user PAPER engine.

        Fills/triggers whatever the price crossed (engine-native logic), sweeps
        the orphaned OCO leg after a fill, and publishes portfolio state — on
        every change immediately, and on a slow heartbeat regardless so open
        positions' uPnL stays live in the UI.

        Only sessions cached in this process tick (a daemon restart loses
        in-memory paper positions — the known hydration gap, tracked separately).
        Live/keyed engines are skipped: the EXCHANGE fills their orders.
        """
        from src.core.paper_tick import process_engine_tick, sweep_orphaned_legs

        tick = 0
        while self.running:
            try:
                await asyncio.sleep(self.PRICE_TICK_INTERVAL_S)
                tick += 1
                if self.registry is None or self.state_manager is None:
                    continue
                sessions = dict(getattr(self.registry, "_sessions", {}) or {})
                if not sessions:
                    continue
                prices = await self.state_manager.get_all_prices()
                if not prices:
                    continue
                heartbeat = tick % self.PUBLISH_EVERY_N_TICKS == 0

                for user_id, session in sessions.items():
                    engine = getattr(session, "engine", None)
                    # Paper engines only — live engines have no local order book.
                    if engine is None or not hasattr(engine, "check_limit_orders"):
                        continue
                    try:
                        changed = await process_engine_tick(engine, prices)
                        if changed:
                            swept = await sweep_orphaned_legs(engine)
                            plog.info(
                                f"[paper-tick] fills for {user_id}"
                                + (f" (+{swept} OCO leg(s) swept)" if swept else ""),
                                agent="daemon",
                            )
                        has_exposure = bool(getattr(engine, "positions", {}) or engine.get_open_orders())
                        if (changed or (heartbeat and has_exposure)) and hasattr(engine, "publish_portfolio_update"):
                            await engine.publish_portfolio_update()
                    except Exception as e:
                        plog.warning(f"[paper-tick] tick failed for {user_id}: {e}", agent="daemon")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                plog.warning(f"[paper-tick] loop error: {e}", agent="daemon")

    async def _has_scan_demand(self) -> bool:
        """Is anybody actually scanning right now?

        Analysis exists to answer a user's scan. With nobody scanning there is nothing to
        answer, so spending an LLM call is pure waste — this is what makes the free tier
        economically real. Fails CLOSED (no demand) when the session store is unavailable:
        the safe error is not spending money.
        """
        if self.session_manager is None:
            return False
        try:
            return bool(await asyncio.to_thread(self.session_manager.active_sessions))
        except Exception as e:
            plog.warning(f"[analysis] demand check failed ({e}); treating as no demand",
                         agent="daemon")
            return False

    # ------------------------------------------------------------------ stream gate
    # How often demand is re-checked. Cheap: two dict scans + one session query.
    STREAM_GATE_POLL_S = 10.0

    def _exposure_symbols(self) -> list:
        """Symbols with money at risk in any cached PAPER engine.

        These are the positions the price tick fills SL/TP for and the monitors
        watch — both read state_manager prices, which only flow while a kline
        stream is up. Live/keyed engines are excluded: the exchange fills their
        orders. Best-effort by design: an unreadable engine contributes nothing
        rather than raising.
        """
        symbols: set = set()
        sessions = dict(getattr(self.registry, "_sessions", {}) or {}) if self.registry else {}
        for session in sessions.values():
            engine = getattr(session, "engine", None)
            if engine is None or not hasattr(engine, "check_limit_orders"):
                continue
            try:
                for sym in (getattr(engine, "positions", {}) or {}):
                    symbols.add(str(sym))
                for order in engine.get_open_orders() or []:
                    sym = order.get("symbol") if isinstance(order, dict) else getattr(order, "symbol", None)
                    if sym:
                        symbols.add(str(sym))
            except Exception:
                continue
        return sorted(symbols)

    async def _stream_demand(self):
        """(profile, price_symbols) the market-data plane should serve right now.

        scan   — somebody is scanning (or the owner keeps analysis warm): the
                 analysis feed must be live.
        prices — nobody scans, but positions/resting orders exist: paper fills
                 and monitors still need prices, one light stream per symbol.
        None   — idle. Nothing runs for nobody; this is what makes the free
                 tier's bandwidth budget real (the Aug-10 suspension was this
                 rule not existing).
        """
        keep_warm = os.getenv("ANALYSIS_KEEP_WARM", "").strip().lower() == "true"
        if keep_warm or await self._has_scan_demand():
            return "scan", None
        exposed = self._exposure_symbols()
        if exposed:
            return "prices", exposed
        return None, None

    @staticmethod
    def _gate_decision(current_rank: int, desired_rank: int, lower_since, now: float, linger: float):
        """(apply_now, new_lower_since) — upgrades are immediate, downgrades linger.

        The linger exists for the same reason as the API feed's: demand often
        flaps (a session ends and the next starts a minute later; a position
        closes and the approval that reopens one is in flight), and Binance
        rate-limits control frames — churn could get the connection dropped.
        """
        if desired_rank >= current_rank:
            return True, None
        if lower_since is None:
            return False, now
        if (now - lower_since) >= linger:
            return True, None
        return False, lower_since

    async def _stream_gate_loop(self):
        """Drive the DataAgent's stream profile from live demand (R0.2)."""
        linger = float(os.getenv("STREAM_LINGER_SECONDS", "120"))
        rank = {None: 0, "prices": 1, "scan": 2}
        applied = (None, None)   # (profile, tuple(symbols))
        lower_since = None
        while self.running:
            try:
                await asyncio.sleep(self.STREAM_GATE_POLL_S)
                if self.data_agent is None:
                    continue
                profile, symbols = await self._stream_demand()
                desired = (profile, tuple(symbols or ()))
                if desired == applied:
                    lower_since = None
                    continue
                now = time.time()
                apply_now, lower_since = self._gate_decision(
                    rank[applied[0]], rank[profile], lower_since, now, linger
                )
                # Same tier but a different symbol set (a new position's symbol
                # needs its price stream NOW) — apply immediately.
                if not apply_now and rank[profile] == rank[applied[0]]:
                    apply_now, lower_since = True, None
                if apply_now:
                    await self.data_agent.set_stream_profile(profile, list(symbols or ()) or None)
                    applied = desired
            except asyncio.CancelledError:
                raise
            except Exception as e:
                plog.warning(f"[stream-gate] loop error: {e}", agent="daemon")

    async def _analysis_with_signals(self):
        """Run shared analysis for EACH traded symbol, publish setups, return them all.

        Analysis is per-symbol but user-independent, so it runs once per symbol per cycle
        (not per user); every resulting setup then fans out to all active tenants.

        DEMAND-DRIVEN. A cycle runs when at least one user is actually scanning, or when
        the owner has explicitly switched analysis on to keep setups warm. It used to run
        on a blind timer gated only by that switch, which meant the switch left on with
        nobody scanning called the LLM every cycle, forever, for nobody.

        The switch is no longer a prerequisite for a user's scan to work — that coupling
        is what let a paused switch silently burn a user's metered clock while producing
        nothing. The switch is now ONLY admission control and an emergency stop, via the
        capacity gate on POST /api/session/start: switch off means new scans are refused
        outright (503, no session row, no clock), so demand stops at the door instead of
        being starved after the meter has started. Keeping analysis warm with zero scans
        is a separate, explicit opt-in — ANALYSIS_KEEP_WARM=true — never the switch.
        """
        # KEEP-WARM IS NOT THE CAPACITY SWITCH. Tying them together made this gate
        # useless: `engine:on` must be ON for a session to be admitted at all (the 503
        # capacity gate), so reading it as "override" meant the override was true in every
        # configuration where anyone could scan — and analysis ran every cycle regardless
        # of demand. Keep-warm is its own opt-in, off by default.
        keep_warm = os.getenv("ANALYSIS_KEEP_WARM", "").strip().lower() == "true"
        demand = await self._has_scan_demand()

        if not demand and not keep_warm:
            if self._was_on is not False:  # log the transition, not every idle cycle
                plog.info(
                    "⏸️  analysis idle — nobody is scanning", agent="daemon"
                )
                self._was_on = False
            # Deliberately does NOT stamp _last_analysis_at: idle time should not count
            # against the cadence, so the first scan after a quiet spell gets a cycle
            # immediately instead of waiting out a window it spent asleep.
            return []

        # Pace the real work. The loop ticks fast so demand is noticed quickly; the
        # expensive part still runs no more often than the configured cadence.
        now = time.time()
        if self._last_analysis_at is not None and (now - self._last_analysis_at) < self.cycle_interval:
            return []
        self._last_analysis_at = now

        if self._was_on is not True:
            plog.info(
                "🟢 analysis running — " + ("keep-warm is on" if not demand
                                            else "a user is scanning"),
                agent="daemon",
            )
            self._was_on = True

        all_setups = []
        for sym in self.symbols:
            try:
                setups = await self.orchestrator.run_analysis_cycle(sym)
            except Exception as e:
                plog.warning(f"[analysis] {sym} cycle failed: {e}", agent="daemon")
                continue
            # The analysis pipeline can return None / None-entries when a cycle yields
            # no valid setup. Drop those here so they never reach publish or booking
            # (a None setup crashed evaluate_and_book: "NoneType not subscriptable").
            valid = [s for s in (setups or []) if isinstance(s, dict) and s.get("symbol")]
            if valid:
                await self._publish_setups(valid)
                all_setups.extend(valid)
                # Session workers propose from this cache — per-user judgment over
                # shared facts. Stamped so stale setups age out (session_pipeline).
                if self.setup_cache is not None:
                    self.setup_cache.put(sym, valid)
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
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except (asyncio.CancelledError, Exception):
                pass
        if getattr(self, "worker_pool", None) is not None:
            try:
                await self.worker_pool.stop()
            except Exception as e:
                plog.warning(f"worker pool stop error: {e}", agent="daemon")
        if getattr(self, "monitor_supervisor", None) is not None:
            try:
                await self.monitor_supervisor.stop()
            except Exception as e:
                plog.warning(f"monitor supervisor stop error: {e}", agent="daemon")
        for task_name in ("_pool_task", "_sweeper_task", "_monitor_task", "_stream_task"):
            task = getattr(self, task_name, None)
            if task:
                task.cancel()
                try:
                    await task
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
