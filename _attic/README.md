# _attic — retired files, kept for reference

Moved here 2026-08-24 during the repo re-architecture (see `docs/plan-2026-08/`).
Every file was reference-checked before moving: nothing in `src/`, `tests/`, CI,
Docker builds, or the canonical docs points at anything in here. Git history is
preserved (moves, not deletes).

**Nothing in here runs, ships, or is documentation of the current system.**
Restore a file with `git mv _attic/<dir>/<file> <original-location>` if it turns
out to be needed.

| Dir | What | Why retired |
|---|---|---|
| `root-docs/` | Jan-2026 doc generation (SETUP, guides, troubleshooting) + websocket test HTML + debug scripts | Superseded by `docs/PRD_CURRENT_STATE.md`, `docs/HLD.md`, `docs/ARCHITECTURE.md` |
| `docs/` | Old PRD/spec/taskmanager generation | Superseded by the same canonical set |
| `cta-docs/` | 12-file fix-summary citation island + stale MULTI_TENANCY duplicate | Referenced only each other; root `docs/MULTI_TENANCY.md` is the live contract |
| `cta-scripts/` | 44 loose one-off scripts — incl. **destructive** ones (`nuclear_clear_positions.py`, `delete_all_trades.py`, …) that used to ship in the production Docker image | Superseded by the guarded `crypto-trading-agent/scripts/admin.py` CLI; removed from the image |
| `src-dead/` | `event_coordinator.py` (the "always-running 300s loop" — actually never constructed), `health_monitor.py`, `cycle_state.py`, `multi_context_analyzer.py`, `dual_context_llm_builder.py`, `ict_detector_CLEAN.py` | Zero importers from any entrypoint or test (verified by audit 2026-08-24) |
| `frontend/` | `test-websocket.js` | Dev-only probe, referenced only by retired docs |
| `agent-notes/` | `.agent/` scratch notes | Historical working notes |

⚠️ **Never run anything from `cta-scripts/` against production state.** The safe
path for every operation they performed is `python3.12 scripts/admin.py <cmd> --confirm`.
