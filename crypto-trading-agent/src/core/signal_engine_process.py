"""Run the Rust signal engine as a child process of the API.

The shared signal plane is a separate binary (`signal-engine`), and
`docs/MULTI_TENANCY.md` describes it as its own always-on service. Render's free tier
allows only web services and meters instance-hours across all of them, so a second
always-on service is both disallowed and would risk suspending the backend. Hosting the
engine elsewhere would also cost it INTERNAL Redis access — it would have to reach the
production Redis over the public internet.

So it rides along here, supervised, exactly as the multi-user daemon does under
RUN_DAEMON_IN_API=true. When the deployment can afford a dedicated worker, delete the
call site and run the same binary standalone; nothing else changes, because the contract
between the planes is the Redis pulse, not the process layout.

Failure policy: the engine is a NICE-TO-HAVE for the API. If the binary is missing or
keeps crashing, the API and the daemon must keep serving — a dead pulse plane means
sessions run ungated (the documented no-op), never that the product goes down.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Optional

from loguru import logger

DEFAULT_BINARY = "/usr/local/bin/signal-engine"

#: Restart backoff bounds. A crash-looping engine must not spin the CPU on a 512MB free
#: instance, so backoff grows to a minute rather than retrying tightly.
_BACKOFF_START_S = 5
_BACKOFF_MAX_S = 60

#: How long to keep reading a dead child's stdout before giving up on it. Short: the
#: child has already exited, so EOF is imminent unless a grandchild inherited the pipe.
_DRAIN_TIMEOUT_S = 5


def _binary_path() -> Optional[str]:
    explicit = os.getenv("SIGNAL_ENGINE_BIN")
    if explicit:
        return explicit if os.path.exists(explicit) else None
    found = shutil.which("signal-engine")
    if found:
        return found
    return DEFAULT_BINARY if os.path.exists(DEFAULT_BINARY) else None


async def _pump_logs(stream: asyncio.StreamReader) -> None:
    """Forward the child's output into our logger so Render shows one stream."""
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", "replace").rstrip()
        if text:
            logger.info(f"[signal-engine] {text}")


async def _close_out(pump: Optional[asyncio.Task], proc) -> None:
    """Read a finished child's last lines, then release its pipes.

    The demonstrated bug is the transport, not the pump. Cancelling the pump — which is
    what this used to do — races the child's final stdout, which is the reason it died;
    measured, the reader usually wins that race, so treat this half as hardening rather
    than a fixed defect.

    Leaving the pump cancelled also leaves the subprocess transport unfinished, and that
    part is not theoretical. The transport then closes from
    `__del__` at GC time instead, which is nondeterministic: if the event loop has shut
    down by then it raises `RuntimeError: Event loop is closed` from whatever happens to
    be running. Under supervision each respawn leaked another one.

    The close is in a `finally` so it still runs when this is called from a cancelled
    supervisor — the drain's first `await` re-raises immediately in that case, and the
    pipes must be released anyway.
    """
    try:
        if pump is not None and not pump.done():
            try:
                await asyncio.wait_for(pump, timeout=_DRAIN_TIMEOUT_S)
            except asyncio.TimeoutError:
                pass
    finally:
        if pump is not None:
            pump.cancel()
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            try:
                transport.close()
            except Exception:  # pragma: no cover - closing must never mask the exit
                pass


async def run_signal_engine(shutdown: Optional[asyncio.Event] = None) -> None:
    """Supervise the engine until shutdown. Never raises into the caller."""
    binary = _binary_path()
    if binary is None:
        logger.warning(
            "signal engine binary not found; the pulse plane stays offline "
            "(sessions run ungated — a designed no-op)"
        )
        return

    # The engine reads REDIS_URL/SYMBOLS/TICK_MS/RUST_LOG from the environment, which the
    # service already provides; SYMBOLS defaults to a liquid set inside the binary.
    env = dict(os.environ)
    env.setdefault("RUST_LOG", "info")

    backoff = _BACKOFF_START_S
    while not (shutdown is not None and shutdown.is_set()):
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            logger.error(f"could not start signal engine ({e}); pulse plane offline")
            return

        logger.info(f"signal engine started (pid {proc.pid}) — publishing market:pulse:*")
        pump = asyncio.create_task(_pump_logs(proc.stdout)) if proc.stdout else None
        try:
            rc = await proc.wait()
        except asyncio.CancelledError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except (asyncio.TimeoutError, Exception):
                proc.kill()
            raise
        finally:
            await _close_out(pump, proc)

        if shutdown is not None and shutdown.is_set():
            return
        # A clean exit is still unexpected for an always-on engine — restart either way.
        logger.warning(f"signal engine exited (rc={rc}); restarting in {backoff}s")
        try:
            if shutdown is not None:
                await asyncio.wait_for(shutdown.wait(), timeout=backoff)
                return
            await asyncio.sleep(backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, _BACKOFF_MAX_S)
