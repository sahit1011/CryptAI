"""Per-session analysis workers — the replacement for the global engine switch.

Today's daemon runs one loop for the whole deployment: an owner flips `engine:on`, and
every tenant receives the same broadcast setups. This module makes analysis per-user and
per-session, which is what `docs/MULTI_TENANCY.md` calls for and what makes the metered
session mean anything.

# Category 3, not category 2

A `SessionWorker` is a per-session instance (see the three categories in
`docs/MULTI_TENANCY.md`). The pool is the category-2 singleton that discovers sessions
and drives their workers. **You need a worker per ACTIVE SESSION, not per registered
user** — at 1,000 users perhaps 30 sessions are live at once, so this is tens of asyncio
tasks, not thousands of processes.

# What is injected, and why

`analyze_fn` is a callback rather than a hard dependency on the orchestrator. The agent
pipeline is M3's job; this module owns the *lifecycle* — budget gating, spend
attribution, the audit trail, pulse staleness, and failure isolation. Keeping them
separate means the lifecycle is testable without an LLM, and M3 can slot in the real
pipeline without touching any of it.

# The kill switch stays

The owner's global `engine:on` switch is retained as an EMERGENCY STOP, not as the normal
gate. Sessions decide who runs; the switch decides whether anyone does. Losing the
ability to halt every tenant at once would be a real regression, so per-user metering
adds a gate rather than replacing one.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from loguru import logger

from src.core.session_budget import SessionBudget
from src.core.session_manager import DEFAULT_CYCLE_SECONDS as _DEFAULT_CYCLE_SECONDS
from src.core.session_manager import (
    ENDED,
    SCANNING,
    SessionError,
    configured_cycle_seconds,
)

#: Seconds between cycles within one session. A metered 30-minute session at this cadence
#: is ~10 cycles, which is what makes the minute quota correspond to real LLM spend.
#:
#: Defined in `session_manager` and re-exported here, NOT duplicated: the API publishes
#: this same number as `expected_cycle_seconds` so the client can judge heartbeat
#: staleness against the interval the server genuinely paces on. Two copies would drift
#: the moment either was tuned, and the UI would start calling a healthy engine dead.
DEFAULT_CYCLE_SECONDS = _DEFAULT_CYCLE_SECONDS


#: How often the pool re-discovers sessions. Faster than the cycle so a session that
#: starts mid-cycle does not wait a full cadence for its first pass.
DEFAULT_DISCOVERY_SECONDS = 5

#: A pulse older than this is refused. Invariant 2 in docs/MULTI_TENANCY.md: the shared
#: plane is a single point of failure for every tenant, so consumers fail CLOSED rather
#: than synthesising setups from stale market facts.
DEFAULT_MAX_PULSE_AGE_MS = 15_000

#: Result of one cycle, for logging and tests.
CYCLE_RAN = "ran"
CYCLE_SKIPPED_BUDGET = "skipped_budget"
CYCLE_SKIPPED_STALE = "skipped_stale_pulse"
CYCLE_SKIPPED_NOT_SCANNING = "skipped_not_scanning"
CYCLE_FAILED = "failed"

#: (setups, usage) — usage is any object or dict with token fields, or None.
AnalyzeFn = Callable[[Dict[str, Any]], Awaitable[tuple]]


class SessionWorker:
    """Runs metered analysis cycles for one session until it ends.

    Ordering inside a cycle is deliberate:

    1. **Budget first.** `can_spend()` enforces both meters *before* any LLM call. A
       caller that checks afterwards has already spent the money.
    2. **Pulse staleness second.** Refuse stale market facts before doing work on them.
    3. **Analyse.**
    4. **Record spend even when the call fails.** A request that errored after the
       provider billed it still cost money; skipping the charge on the error path is how
       a cap silently leaks.
    """

    def __init__(
        self,
        session_manager,
        preferences_store,
        session: Dict[str, Any],
        analyze_fn: AnalyzeFn,
        pulse_client=None,
        cycle_seconds: Optional[int] = None,
        max_pulse_age_ms: int = DEFAULT_MAX_PULSE_AGE_MS,
        state_manager=None,
    ):
        self.sessions = session_manager
        self.preferences = preferences_store
        self.session_id = session["session_id"]
        self.user_id = session["user_id"]
        self.analyze_fn = analyze_fn
        self.pulse_client = pulse_client
        self.cycle_seconds = cycle_seconds or configured_cycle_seconds()
        self.max_pulse_age_ms = max_pulse_age_ms
        self.budget = SessionBudget(session_manager, self.session_id)
        self.state_manager = state_manager
        self.cycles_run = 0

    async def _open_positions(self) -> list:
        """This user's live positions, for portfolio-aware selection. Best-effort.

        Returns [] when unavailable — a book we cannot read must degrade to "we don't
        know what you hold", never to a failed cycle on the user's metered time.
        """
        if self.state_manager is None:
            return []
        try:
            return await self.state_manager.get_positions(user_id=self.user_id) or []
        except Exception as e:
            logger.debug(f"could not read positions for {self.user_id}: {e}")
            return []

    # -- one cycle -----------------------------------------------------------

    async def run_cycle(self) -> str:
        """Run a single metered cycle. Returns one of the CYCLE_* constants."""
        # 1. Both meters, before spending anything.
        if not self.budget.can_spend():
            return CYCLE_SKIPPED_BUDGET

        state = self.sessions.get(self.session_id) or {}
        if state.get("status") != SCANNING:
            # Paused on a proposal, executing, or ended. Not an error — the clock is
            # stopped and there is nothing to analyse.
            return CYCLE_SKIPPED_NOT_SCANNING

        prefs = await asyncio.to_thread(self.preferences.get, self.user_id)
        symbols = self._universe(prefs)

        pulses = await self._fresh_pulses(symbols)
        if pulses is None:
            self.sessions.log_agent_step(
                self.session_id,
                "signal_plane",
                "market data unavailable or stale — refusing to analyse",
            )
            return CYCLE_SKIPPED_STALE

        context = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "preferences": prefs,
            "pulses": pulses,
            "symbols": symbols,
            # The trading style chosen at session start; the pipeline overlays it on the
            # persona (goal_horizon + a tighter R:R floor). None keeps the persona.
            "channel": state.get("channel"),
            # What they already hold. Without this the synthesis prompt renders
            # "already holding: none" for everyone and can offer a setup that doubles or
            # opposes a live position — portfolio-aware selection was the point.
            "open_positions": await self._open_positions(),
        }

        usage = None
        try:
            setups, usage = await self.analyze_fn(context)
        except Exception as e:
            logger.warning(f"analysis failed for session {self.session_id}: {e}")
            self.sessions.log_agent_step(
                self.session_id, "analysis", f"cycle failed: {e}"
            )
            return CYCLE_FAILED
        finally:
            # Spend is booked even on the failure path: a request that errored after the
            # provider billed it still cost real money, and skipping the charge there is
            # exactly how a cap leaks.
            if usage is not None:
                try:
                    self.budget.record_response(
                        (usage.get("model") if isinstance(usage, dict) else None)
                        or "unknown",
                        usage,
                    )
                except SessionError as e:
                    logger.warning(f"could not record spend for {self.session_id}: {e}")

        self.cycles_run += 1
        self.sessions.record_cycle(self.session_id)
        self.sessions.log_agent_step(
            self.session_id,
            "analysis",
            f"cycle complete — {len(setups or [])} candidate setup(s)",
            {"symbols": symbols, "setups": len(setups or [])},
        )
        return CYCLE_RAN

    # -- helpers -------------------------------------------------------------

    def _universe(self, prefs: Dict[str, Any]) -> List[str]:
        from src.core.preferences import universe_for

        return universe_for(prefs, self.default_universe())

    @staticmethod
    def default_universe() -> List[str]:
        import os

        raw = os.getenv("PLATFORM_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
        return [s.strip().upper() for s in raw.split(",") if s.strip()]

    async def _fresh_pulses(self, symbols: List[str]) -> Optional[Dict[str, Any]]:
        """Fresh pulses for the universe, or None if the shared plane is unusable.

        Returns None rather than an empty dict when nothing is fresh — "no market data"
        and "market data says nothing is tradable" must not look the same to the caller.

        With no pulse client configured the check is skipped entirely: the signal engine
        is not deployed yet, and blocking every session on a service that does not exist
        would make the whole control plane untestable in the current deployment.
        """
        if self.pulse_client is None:
            return {}

        try:
            pulses = await self.pulse_client.get_many(symbols)
        except Exception as e:
            logger.warning(f"pulse read failed for session {self.session_id}: {e}")
            return None

        return pulses if pulses else None

    # -- loop ----------------------------------------------------------------

    async def run(self, shutdown: Optional[asyncio.Event] = None) -> None:
        """Cycle until the session ends or shutdown is requested."""
        logger.info(f"session worker started for {self.user_id} ({self.session_id})")
        try:
            while True:
                if shutdown is not None and shutdown.is_set():
                    return

                result = await self.run_cycle()
                if result == CYCLE_SKIPPED_BUDGET:
                    logger.info(
                        f"session {self.session_id} exhausted a meter; worker stopping"
                    )
                    return

                state = self.sessions.get(self.session_id) or {}
                if state.get("status") == ENDED:
                    return

                try:
                    if shutdown is not None:
                        await asyncio.wait_for(shutdown.wait(), timeout=self.cycle_seconds)
                        return  # shutdown fired during the wait
                    else:
                        await asyncio.sleep(self.cycle_seconds)
                except asyncio.TimeoutError:
                    pass  # normal cadence
        except asyncio.CancelledError:
            logger.info(f"session worker cancelled for {self.session_id}")
            raise
        finally:
            logger.info(
                f"session worker finished for {self.user_id} "
                f"({self.cycles_run} cycles)"
            )


class SessionWorkerPool:
    """Discovers active sessions and keeps one worker per session alive.

    Category-2 singleton: one process, iterating tenants, holding no per-tenant state
    between passes. Reaping is by session id, so a worker whose session ended is dropped
    on the next discovery pass without needing the worker to report anything.
    """

    def __init__(
        self,
        session_manager,
        preferences_store,
        analyze_fn: AnalyzeFn,
        pulse_client=None,
        cycle_seconds: Optional[int] = None,
        discovery_seconds: int = DEFAULT_DISCOVERY_SECONDS,
        kill_switch=None,
        state_manager=None,
    ):
        self.sessions = session_manager
        self.preferences = preferences_store
        self.analyze_fn = analyze_fn
        self.pulse_client = pulse_client
        self.cycle_seconds = cycle_seconds or configured_cycle_seconds()
        self.discovery_seconds = discovery_seconds
        self.kill_switch = kill_switch
        self.state_manager = state_manager
        self.workers: Dict[str, asyncio.Task] = {}
        self._shutdown = asyncio.Event()

    async def _kill_switch_open(self) -> bool:
        """Whether the owner's emergency stop permits work.

        Retained from the pre-session design deliberately. Sessions decide WHO runs; this
        decides whether ANYONE does. Losing the ability to halt every tenant at once
        would be a real regression. Fails OPEN when unconfigured (no switch means no
        emergency stop, not a permanent halt) and CLOSED when the check itself errors.
        """
        if self.kill_switch is None:
            return True
        try:
            return bool(await self.kill_switch.is_on())
        except Exception as e:
            logger.error(f"kill switch unreadable ({e}); halting work to be safe")
            return False

    async def discover_once(self) -> int:
        """One discovery pass: reap finished workers, spawn missing ones.

        Returns the number of live workers after the pass.
        """
        # Reap first, so a session that ended frees its slot before we count.
        for session_id, task in list(self.workers.items()):
            if task.done():
                self.workers.pop(session_id, None)
                exc = task.exception() if not task.cancelled() else None
                if exc is not None:
                    logger.warning(f"session worker {session_id} died: {exc}")

        if not await self._kill_switch_open():
            return len(self.workers)

        try:
            active = await asyncio.to_thread(self.sessions.active_sessions)
        except Exception as e:
            logger.error(f"session discovery failed: {e}")
            return len(self.workers)

        for session in active:
            session_id = session["session_id"]
            if session_id in self.workers:
                continue
            worker = SessionWorker(
                self.sessions,
                self.preferences,
                session,
                self.analyze_fn,
                pulse_client=self.pulse_client,
                cycle_seconds=self.cycle_seconds,
                state_manager=self.state_manager,
            )
            self.workers[session_id] = asyncio.get_running_loop().create_task(
                worker.run(self._shutdown)
            )
            logger.info(f"spawned worker for session {session_id}")

        return len(self.workers)

    async def run(self) -> None:
        """Discovery loop. Runs until `stop()`."""
        logger.info("session worker pool started")
        while not self._shutdown.is_set():
            try:
                await self.discover_once()
            except Exception as e:
                # Never let the pool die — it is the only thing spawning workers.
                logger.error(f"discovery pass failed: {e}")
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self.discovery_seconds
                )
            except asyncio.TimeoutError:
                pass
        logger.info("session worker pool stopped")

    async def stop(self, timeout: float = 10.0) -> None:
        """Signal shutdown and wait for workers to finish their current cycle."""
        self._shutdown.set()
        tasks = list(self.workers.values())
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        self.workers.clear()
