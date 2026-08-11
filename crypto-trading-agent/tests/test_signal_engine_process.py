"""The signal-engine child process is a nice-to-have, never a dependency.

It ships inside the API image on free-tier deploys, so its failure modes must stay
contained: a missing binary or a crash-looping engine means the pulse plane is offline
(sessions run ungated — the documented no-op), never a degraded or down API.
"""
import asyncio
import os

import pytest

from src.core import signal_engine_process as sep


@pytest.mark.asyncio
async def test_missing_binary_returns_quietly():
    """No binary (every local/dev environment, and any image built without the Rust
    stage) must return immediately rather than raise into the API's startup."""
    os.environ.pop("SIGNAL_ENGINE_BIN", None)
    if sep._binary_path() is not None:
        pytest.skip("a real signal-engine binary is installed here")
    await asyncio.wait_for(sep.run_signal_engine(asyncio.Event()), timeout=5)


@pytest.mark.asyncio
async def test_explicit_missing_path_is_not_used(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGNAL_ENGINE_BIN", str(tmp_path / "nope"))
    assert sep._binary_path() is None
    await asyncio.wait_for(sep.run_signal_engine(asyncio.Event()), timeout=5)


@pytest.mark.asyncio
async def test_runs_a_real_child_and_forwards_its_output(monkeypatch, tmp_path):
    """Happy path with a stand-in binary: the child runs and its stdout is pumped."""
    script = tmp_path / "fake-engine"
    script.write_text("#!/bin/sh\necho 'pulse published'\nsleep 30\n")
    script.chmod(0o755)
    monkeypatch.setenv("SIGNAL_ENGINE_BIN", str(script))

    seen = []
    monkeypatch.setattr(sep.logger, "info", lambda m, *a, **k: seen.append(str(m)))

    shutdown = asyncio.Event()
    task = asyncio.create_task(sep.run_signal_engine(shutdown))
    await asyncio.sleep(0.6)          # let it spawn and emit a line
    shutdown.set()
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=10)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    # No settling sleep here on purpose. This used to need one, because the supervisor
    # left the subprocess transport for the GC to close and its __del__ then fired after
    # the loop had torn down ("Event loop is closed") — a flake that failed whichever
    # test happened to be running at collection time, not this one. run_signal_engine
    # now closes the transport itself, so teardown is deterministic and a sleep would
    # only hide a regression.

    assert any("signal engine started" in m for m in seen)
    assert any("pulse published" in m for m in seen), seen


@pytest.mark.asyncio
async def test_a_crashing_engine_is_retried_with_backoff_not_a_tight_loop(monkeypatch, tmp_path):
    """A binary that exits instantly must NOT be respawned in a tight loop — on a 512MB
    free instance that would burn the CPU the API needs."""
    script = tmp_path / "crashing-engine"
    script.write_text("#!/bin/sh\nexit 1\n")
    script.chmod(0o755)
    monkeypatch.setenv("SIGNAL_ENGINE_BIN", str(script))
    monkeypatch.setattr(sep, "_BACKOFF_START_S", 3600)  # first backoff far exceeds the test

    starts = []
    orig = asyncio.create_subprocess_exec

    async def counting(*a, **k):
        starts.append(a[0])
        return await orig(*a, **k)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counting)

    shutdown = asyncio.Event()
    task = asyncio.create_task(sep.run_signal_engine(shutdown))
    await asyncio.sleep(0.8)
    shutdown.set()
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=10)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    # Exactly one attempt: it crashed, then waited on the (long) backoff instead of
    # immediately respawning.
    assert len(starts) == 1, f"expected one spawn before backoff, got {len(starts)}"


@pytest.mark.asyncio
async def test_a_dying_engine_still_gets_its_last_words_logged(monkeypatch, tmp_path):
    """A crashing child's final stdout must survive its exit.

    On a free instance the engine is the component most likely to die of resource
    limits, so the line it writes on the way out is the one worth having; `rc=1` alone
    says nothing.

    Honest scope: this pins the requirement, it is NOT a regression test. Checked against
    the old cancel-on-exit supervisor and it passed there too — the pump is already
    scheduled and reads the buffered line before the cancel lands, so the race it loses
    is one this test cannot reliably provoke. The defect that fix actually closes is the
    leaked subprocess transport, which surfaces as a GC-timed "Event loop is closed"
    charged to an unrelated test.
    """
    script = tmp_path / "dying-engine"
    script.write_text("#!/bin/sh\necho 'redis connection refused'\nexit 1\n")
    script.chmod(0o755)
    monkeypatch.setenv("SIGNAL_ENGINE_BIN", str(script))
    monkeypatch.setattr(sep, "_BACKOFF_START_S", 3600)  # park on backoff after one crash

    seen = []
    monkeypatch.setattr(sep.logger, "info", lambda m, *a, **k: seen.append(str(m)))

    shutdown = asyncio.Event()
    task = asyncio.create_task(sep.run_signal_engine(shutdown))
    await asyncio.sleep(0.8)
    shutdown.set()
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=10)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    assert any("redis connection refused" in m for m in seen), seen
