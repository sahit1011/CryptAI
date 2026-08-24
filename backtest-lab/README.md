# backtest-lab — offline quant experiments (never ships)

The offline evidence bench from `docs/plan-2026-08/nautilus-memo.md`. Hard rules:

- **Nothing here enters the production image.** The repo-root `.dockerignore`
  excludes `backtest-lab/`; keep it that way. `data/` and `results/` are gitignored.
- Experiments import strategy math **from the backend source**
  (`crypto-trading-agent/src/strategy/…`) — the lab validates the exact code that
  ships, never a reimplementation.
- Results are evidence, not marketing: every summary states its assumptions and
  what it could NOT measure.

## Contents

- `download_klines.sh` — 2024-08…2026-07 Binance USDT-M perp monthly klines
  (1m + 1h; BTC/ETH/SOL) from the free public archive into `data/raw/`.
- `data_loader.py` — zips → numpy column arrays (header-sniffing, ms timestamps).
- `study_s1_ab.py` — **the S1 entry-confirmation A/B** (see below). Runs on the
  backend venv (`crypto-trading-agent/.venv` — pandas/numpy only, no new deps).

## The S1 A/B (first experiment)

Question: at a deep-retracement band touch (0.705–0.886 of the last 1h impulse),
does requiring **absorption → dominance flip** on 1m taker-delta before entering
beat entering at the touch (today's behavior)?

Three arms decompose the effect:

1. `control_all` — enter at the band edge on every touch (product today).
2. `control_confirmed` — same touch-entry, but only on touches that later
   confirmed (isolates the *selection* effect of the filter).
3. `treatment` — enter at the flip close with the stop behind the absorption low
   (selection + *execution* effect).

Mechanics: brackets at 1.5R and 2R; same-1m-bar stop+target resolves to **stop**
(pessimistic); 8h time stop at close; taker fees 0.05%/side; zero slippage for
BOTH arms (generous to control — it assumes a resting limit at the edge fills).
One event at a time per symbol; a band re-arms only when a new 1h swing forms.
Default `S1Params` only — no threshold sweeps in v1, so no multiplicity garden.

Known limitations (v1): no funding, no TDS scenario, no environment stage
(funding/OI regime), fixed default thresholds. Nautilus-based trade-level
backtests (monitor sweep, full setup layer) are the next phase, in their own venv.

Run: `crypto-trading-agent/.venv/bin/python backtest-lab/study_s1_ab.py`
