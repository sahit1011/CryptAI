# Memo — NautilusTrader: adopt offline, borrow patterns, never in prod (2026-08-24)

Evaluated: nautilustrader.io + github.com/nautechsystems/nautilus_trader (v1.231.0,
LGPL-3.0-or-later, ~27.6k stars, bi-weekly releases, Rust core + Python API).
Method: 4-agent research panel (docs + GitHub + PyPI) grounded against our code and plans.

## The verdict in one paragraph

Nautilus's headline pitch — nanosecond low-latency execution — solves a problem we do not
have (180s cadence, human approval, 4–12h holds). What it *actually* offers us is the thing
we're missing most: a **credible trade-level backtesting lab** (deflated Sharpe 0.00 = we
have zero trade-level evidence for the setup/direction/exit layers). License is safe
(LGPL, server-side use ≠ distribution, no obligations). Footprint is disqualifying for
production: ~60–190 MB wheels, docs state a 4-core/8GB minimum, we run on 512MB and just
evicted chromadb. And it has **no BingX or Delta India adapters** — new adapters must be
written in Rust, in-tree, a nine-phase effort per venue: a fork, not a dependency.
So: **ADOPT offline-only as the backtest lab · BORROW four design patterns into our own
code · REJECT for anything in the production image or execution path.**

## ADOPT — the offline backtest lab (founder's Mac / CI, separate venv, pinned 1.x)

Hard rule: `nautilus_trader` never enters the deployed image's requirements.

What makes it genuinely fit: bar-execution mode turns each bar into 4 synthetic updates
(O→H→L→C, with adaptive ordering by which extreme is nearer the open) — directly
addressing the stop-and-target-in-same-bar ambiguity that decides bracket backtests;
`order_factory.bracket()` is literally our proposal shape; funding is simulated via
user-supplied `FundingRateUpdate` (FINDINGS §6: no validated figure includes funding —
first-order for 4–12h perp holds); maker/taker fees + margin accounts modeled; our
pulses replay as documented CustomData; `BacktestNode(configs=[...])` gives windowed
walk-forward; Portfolio statistics emit the per-trade PnL/Sharpe/drawdown evidence our
IC-level harness cannot. Execution on 1m bars, signals on 1h/4h.

**First three targets** (in order of cheapness × value):
1. **Monitor-parameter sweep** — `evaluate_position` is already a pure function with
   hand-set priors (lock 0.8%, give-back 0.5%, tradability ≤25×3, 4h/12h time stops)
   that have never met historical data. Needs candles only.
2. **Absorption-proxy pre-validation** — the orderflow memo's A/B, run offline first on
   1m taker-buy-volume klines. If it shows nothing offline, the live A/B isn't built.
3. **Deterministic setup-layer backtest** — the pure chain (SMC/ICT zones →
   TradeSetupBuilder → safety gate → sizer → bracket) with funding/fees/**TDS as a
   parameterized scenario knob**, walk-forward, held-out symbols, deflated Sharpe. Split
   out the "fabricated default ±0.5% zone" trades as a control — today a setup can exist
   with no structural basis at all (strategy_agent.py:1322).

**Not backtestable, by design:** the LLM synthesis layer (non-deterministic, per-user).
Its evidence comes from the live proposal→outcome ledger (R1.5), never from this lab.
Effort: ~3–7 focused days. Data prep: bulk-download 1–2y Binance 1m/1h klines (free) —
our live 500-candle window is statistically useless. Placement: **quant-track sibling of
R1.5**, parallel to backend R1/R2 — it displaces no launch task and can never substitute
for the six-weeks-live + compliance real-money gate.

## BORROW-PATTERN — four things to implement in OUR code (no dependency)

1. **Reconciliation discipline** (their strongest subsystem): block trading until venue
   order/position reports are fetched and diffed against persisted state; apply fill
   economics only when reports prove a coherent position transition, else flag for human
   review; run continuous in-flight checks, not just at startup. → folds into R2.1
   (rehydration) and R2.3 (focus-lock source of truth).
2. **RiskEngine's enumerated pre-trade checklist with typed denial reasons** (precision,
   bounds, GTD expiry, notional caps, balance impact, and *reduce-only-must-not-increase-
   position* — the exact invariant our old rollback bug violated). ~200-line pure
   function in the approve→revalidate→execute path.
3. **OCO honesty**: sibling cancel is best-effort and a both-legs-fill race is normal —
   never assume venue cascade; OUO-style quantity sync on partial fills is the concrete
   fix for our partial-fill bracket class.
4. **WS client patterns** for our gated Binance client: buffered-delta + REST-snapshot
   rebuild on every reconnect (never trust a resumed stream), 3-missed-heartbeat
   dead-peer detection with per-endpoint reconnect, client-side token buckets paced
   ahead of venue accounting.

Their architecture (MessageBus/Cache/Engines/Portfolio) maps ~1:1 onto what we hand-built
— treat that as validation of our design, not a reason to swap it.

## REJECT

- **Any production embedding** — 512MB vs their 4-core/8GB stated minimum; one-LiveNode-
  per-process fights our single-service topology.
- **Live execution / adapters** — BingX and Delta India are absent; two Rust in-tree
  adapters ≫ hardening our existing ~200-line ccxt-style ones. Replacing scar-tissue
  money-safety code pre-launch violates the money law.
- **TWAP execution algos** — no market-impact problem at $10k desks on liquid perps, and
  slicing multiplies order count (fee/TDS drag).
- **v2.0 (Rust-first rewrite) churn** — pin 1.x; revisit after their v2 stabilizes.

## Found while grounding — our own bugs, independent of any Nautilus decision

File as tickets now (they bite R1.5's falsifiability ledger and live paper trading):
1. **`exit_reason` is fabricated** ("TP_HIT if pnl>0 else SL_HIT",
   paper_trading_engine.py:546,568) — corrupts every outcome-attribution query the
   evidence plan depends on.
2. **Same-direction add-on fills are silently dropped** (position unchanged, commission
   still charged, order booked FILLED — `_update_position` handles only the closing case).
3. Docstring claims "market impact / order book depth simulation" that does not exist;
   slippage is unseeded `random.uniform` (non-reproducible runs); margin is checked at
   entry only and never reserved across positions.
