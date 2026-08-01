# Signal engine — validation findings

> Generated 2026-08-02 from `eval/evaluate.py` and `eval/walkforward.py` against live
> Binance 1h klines. Reproduce with `cargo build --release --bin backtest` then
> `python eval/walkforward.py`. Raw output: `eval/walkforward_results.json`.

## Verdict in one line

**The tradability score validates as a short-horizon filter. The regime label does not
validate as a directional signal, and must not be used as one.**

---

## 1. Tradability score — VALIDATED (short horizon only)

| | BTC | XAUT |
|---|---|---|
| IC vs abs forward return, 4 bars | **+0.083** (t +3.66) | **+0.096** (t +2.52) |
| Same, after volatility normalisation | +0.084 | +0.085 |
| 12 bars | +0.082 (t +2.07) | +0.056 (t +0.84) |
| 24 bars | +0.088 (t +1.58) | +0.006 (t +0.06) |
| 72 bars | −0.033 | −0.064 |

Two things make this credible rather than an artifact:

- **It survives volatility normalisation essentially unchanged.** Realised volatility is
  strongly autocorrelated, so any score containing a volatility term trivially "predicts"
  the size of the next move. Dividing the forward move by the volatility already
  observable at decision time removes that. The IC barely moves, so the information is
  not just volatility clustering rediscovering itself.
- **t-statistics use effective sample size** (n/h), not raw n. The first version of this
  analysis reported t +7.76 where the honest figure is +1.58.

**Actionable consequence: the signal has a 4–12 hour half-life.** That should drive the
session cadence and the holding period, not a number picked for feeling right.

## 2. Regime label as a direction call — NOT VALIDATED

### The in-sample result that looked good

Adding variance-ratio veto power over trend labels appeared to fix a wrong-signed
classifier:

| 24-bar regime IC | before | after |
|---|---|---|
| BTCUSDT | −0.034 | **+0.077** |
| XAUTUSDT | −0.195 | **−0.056** |

### It does not survive out of sample

Six instruments never examined while building the fix, same parameters, same binary:

| Symbol | baseline IC | treatment IC | delta |
|---|---|---|---|
| ETHUSDT | −0.086 | −0.038 | +0.048 |
| SOLUSDT | −0.033 | −0.060 | −0.027 |
| BNBUSDT | −0.032 | +0.014 | +0.046 |
| XRPUSDT | −0.034 | −0.093 | −0.059 |
| ADAUSDT | −0.066 | −0.055 | +0.011 |
| LINKUSDT | +0.029 | −0.040 | −0.069 |

**Mean improvement −0.008, paired t −0.40, 3 of 6 improved.** A coin flip.

The development symbols improved by +0.111 and +0.139; the best held-out symbol managed
+0.048. That gap between in-sample and out-of-sample improvement is the signature of
having chosen the rule after looking at the data.

### Three independent reasons to disbelieve the in-sample result

**a) The tuned parameter is inert.** Sweeping `vr_mean_reversion_max` from 0.85 to 1.00
produces *byte-identical* IC, Sharpe, and trade counts on both development symbols. The
threshold does nothing across the range it was "tuned" in — `vr_trend_min = 1.0` (the
theoretical random-walk value, never fitted) is doing all the work. What looked like a
calibrated rule is a single unfitted inequality plus a knob with no effect.

**b) Fold-level results are noise.** Per contiguous time fold, treatment IC on BTC runs
+0.149, −0.230, *insufficient trades*, +0.216. Several folds on several symbols cannot
produce an IC at all because the rule emits too few trend labels to measure. A metric
that cannot be computed in a quarter of the sample is not a metric.

**c) The apparent "wrong-signed classifier" is largely one market period.** Fold 3
baseline IC across all eight instruments: −0.130, −0.340, −0.371, −0.221, +0.001, −0.215,
−0.200, −0.260. Seven of eight sharply negative *in the same window*. This is a
market-wide regime that punished trend-following everywhere, not a property of the
classifier that a per-symbol threshold could fix. Full-sample IC is dominated by it.

### What was kept, and why

The variance-ratio machinery stays, and `MeanReverting` remains a regime. Not because it
improved directional accuracy — it did not — but because it is a **descriptive** output
grounded in an actual hypothesis test, and the per-user reasoning plane can use "this
market is statistically mean-reverting" to pick a strategy. That claim is about market
behaviour and is independently testable; the discarded claim was that the label predicts
direction.

**The regime label is a description, not a recommendation.** No consumer may read
`TrendingUp` as "go long". Direction is synthesised per-user, which is what
`docs/MULTI_TENANCY.md` said before any of this was measured.

## 3. Methodology bugs found and fixed in this harness

Both were in the first version of `evaluate.py`, and both inflated results:

1. **Overlapping windows compounded as an equity curve.** A 24-bar forward return
   computed at every bar, then `cumprod`-ed, counts each holding period 24 times. It
   produced annualised Sharpes of −18 and −99% drawdowns — impossible numbers that were
   the tell. Fixed with non-overlapping sampling.
2. **t-statistics assumed independent observations** when consecutive ones shared 23 of
   24 bars, inflating every t by roughly √24. Fixed with effective sample size n/h.

## 4. What has NOT been tested

- **Funding, open interest, spread, and depth are held constant.** Klines carry no such
  history, so `positioning` and `book_quality` contribute a constant offset and none of
  their variation is validated. Two of six factors are therefore unmeasured.
- **No transaction costs, slippage, or funding charges** in any figure above.
- **Structure detection (ICT/SMC) is not implemented**, so `structure` is empty
  throughout and contributes nothing.
- **One year, one asset class, one venue.** Every instrument is a Binance USDT pair and
  the sample covers a single broad market period.
- **Deflated Sharpe is 0.00 everywhere.** After correcting for the number of
  configurations tried, no strategy variant here shows skill.

## 5. What to do next

1. **Do not ship a directional recommendation.** The filter is the validated product.
2. **Re-run this after the ingest layer lands**, with real funding/OI/spread/depth, so
   the two unmeasured factors can be evaluated.
3. **Calibrate weights against `pulse_snapshots`** once live data accumulates — the
   current weights in `Weights::default()` remain an uncalibrated prior.
4. Treat any future classifier change the same way: development symbols, held-out
   symbols, parameter sweep, fold stability. The in-sample number will always look
   better.
