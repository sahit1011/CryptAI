# CryptAI rescue plan — 2026-08-24

Produced by a 9-agent full-repo audit + full-team replanning session. **Read the PDFs;
the HTML in `src/` is the editable source** (`bash src/build.sh` rebuilds via Chrome headless).

| PDF | What it decides |
|---|---|
| `01-audit-current-state.pdf` | Ground truth: what's wired, why production is suspended, the ranked defect list, LLM cost reality, quant verdict |
| `02-product-plan.pdf` | Tiers (free/lite/pro/pro-max), the 2×30-min session mechanic, honest claims, launch scope, success metrics, open founder decisions |
| `03-system-design.pdf` | Topology, three planes, slot-model state machine, demand-gated compute law, schema + API deltas |
| `04-ux-flows.pdf` | Onboarding flow, daily loop, dashboard IA, trade-focus pivot, frontend build map |
| `05-infra-free-tier.pdf` | Stack decision, $0 bandwidth ledger, the un-suspend runbook (ORDER MATTERS), secrets map, ops rhythm |
| `06-execution-roadmap.pdf` | Milestones R0–R4 with task IDs + proof gates, the engineering harness, team swimlanes |

**Working the plan:** every coding session picks ONE task ID from doc 06 (R0.2, R1.3, …),
lands it with `.claude/verify.sh` green, and demonstrates the task's stated
definition-of-done. Out-of-plan work needs a written reason in the commit.

Status at authoring: R0.1 (repo re-architecture → `_attic/`) is DONE; production is
suspended and must NOT be resumed before R0.2 merges.
