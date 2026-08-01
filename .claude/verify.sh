#!/usr/bin/env bash
# CryptAI verification gate — the Stop hook runs this before Claude may finish.
# Exit 0 only when the repo is in a shippable state.
#
# Branch note: the real project lives on `v2` (111 commits), not `main` (8).
# Verified on v2, 2026-08-01: frontend typecheck clean, 52/52 unit tests pass.
#
# Scoped to what passes TODAY. Deliberately excluded:
#   - `npm run build`      : works (~60s), too slow for a per-turn gate. Run before push.
#   - backend pytest       : needs Python 3.12 + ta-lib C lib. Enable the block below
#                            once `.venv` exists — CI proves it passes with mocked
#                            Redis/Postgres, so no Docker is required for unit tests.
#   - integration tests    : opt-in, need live Redis + Postgres.
# Widen as those become true. Do not weaken it to get green.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# Hooks, cron, and CI spawn this with a minimal PATH and never source a shell rc,
# so resolve the Node toolchain here instead of trusting the caller's environment.
# The fnm `default` alias path is stable across Node version upgrades.
for d in "$HOME/.local/share/fnm/aliases/default/bin" "$HOME/.local/bin" /opt/homebrew/bin; do
  [ -d "$d" ] || continue
  case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH

command -v npx >/dev/null 2>&1 || {
  echo "  ✗ FAILED: npx not found on PATH — Node toolchain missing or fnm default alias unset"
  echo "    try: fnm default lts-latest"
  exit 1
}

fail=0
# Quiet on success: this runs on every turn, so passing steps print one line.
# Failing steps print the tail of their real output, which is what Claude needs.
step() {
  local label=$1; shift
  local out
  if out=$("$@" 2>&1); then
    echo "  ✓ $label"
  else
    echo "  ✗ FAILED: $label"
    tail -40 <<<"$out"
    fail=1
  fi
}

# ── Frontend (Next.js 16) ────────────────────────────────────
if [ -d frontend/node_modules ]; then
  step "frontend typecheck"  bash -c 'cd frontend && npx tsc --noEmit'
  step "frontend unit tests" bash -c 'cd frontend && npx vitest run'
else
  echo "  ⊘ frontend deps not installed (run: cd frontend && npm install)"
fi

# ── Backend (Python 3.12) ────────────────────────────────────
# Import smoke catches broken imports, syntax errors, and bad top-level side
# effects. pytest runs the hermetic suite (everything under tests/ except the
# opt-in tests/integration, mocked Redis/Postgres per pytest.ini) — 309 tests in
# ~6s. It was 213 until 2026-08-02, when pytest.ini's testpaths was widened from a
# two-entry allowlist that silently excluded ~17 files at tests/ root.
#
# Env is pinned to the fail-safe combination so a gate run can never touch a
# real exchange, mirroring ci.yml.
BE=crypto-trading-agent
BE_ENV=(ENVIRONMENT=test LOG_LEVEL=WARNING ENABLE_EXECUTION=false
        LIVE_TRADING_CONFIRMED=false USE_TESTNET=true)
if [ -x "$BE/.venv/bin/pytest" ]; then
  step "backend import smoke" env -C "$BE" "${BE_ENV[@]}" \
    .venv/bin/python -c "import src.api.server"
  step "backend tests"        env -C "$BE" "${BE_ENV[@]}" \
    .venv/bin/pytest -q
else
  echo "  ⊘ backend venv missing — see CLAUDE.md 'Backend setup' to enable this gate"
fi

if [ $fail -ne 0 ]; then
  echo ""
  echo "Verification FAILED. Fix the root cause — never delete a failing test,"
  echo "loosen an assertion, or disable a risk gate to get green."
fi
exit $fail
