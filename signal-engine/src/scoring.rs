//! Regime classification and the tradability score.
//!
//! Three stages, in order, and the order is the design:
//!
//! 1. **Veto gates.** Absolute. Any veto zeroes the score regardless of how good
//!    everything else looks. A weighted sum can always be dragged positive by a few
//!    strong components, so a beautiful trend printed on a blown-out spread would score
//!    well without this stage. Vetoes are the cliff; factors are the gradient.
//! 2. **Weighted factors.** Six components chosen to measure *different* things.
//!    Weighting by indicator count rather than by independent information is the
//!    confluence-inflation bug this design exists to avoid — six indicators that all
//!    measure trend are one signal, not six.
//! 3. **Regime classification.** Orthogonal to the score: regime says how the market is
//!    behaving, tradability says whether to deploy risk into it. A clean downtrend is
//!    highly tradable; a violent chop is not, whatever direction it is nominally in.
//!
//! # The weights are guesses
//!
//! [`Weights::default`] is a prior, not a finding. Nothing here has been calibrated
//! against forward returns yet. That is what `pulse_snapshots` in the database exists
//! for: log every score, backfill realised returns, then check whether high-score
//! windows actually produce better risk-adjusted outcomes than low-score ones. Until
//! that has run, treat the absolute number as ordinal at best. A scorer nobody can
//! falsify is decoration.

use crate::indicators::{
    atr, correlation, efficiency_ratio, ema, percentile_rank, returns, Candle,
};
use crate::pulse::{Context, Factors, Level, Pulse, Regime, Structure, Veto};
use crate::quant::{variance_ratio, VarianceRatio};

/// One timeframe's bars. `label` is the wire name, e.g. `"1h"`.
#[derive(Debug, Clone)]
pub struct TimeframeData {
    pub label: &'static str,
    /// Weight in the multi-timeframe trend vote. Higher timeframes carry more.
    pub weight: f64,
    pub candles: Vec<Candle>,
}

/// Everything the scorer needs about one symbol at one instant. Pure input: the scorer
/// performs no I/O and no clock reads, so a given snapshot always scores identically.
/// That determinism is what makes the differential tests against the Python oracle
/// meaningful.
#[derive(Debug, Clone)]
pub struct MarketSnapshot {
    pub symbol: String,
    /// Wall clock at scoring time (epoch millis).
    pub now_ms: i64,
    /// Timestamp of the newest market event incorporated (epoch millis).
    pub feed_ts: i64,
    /// Ascending by duration, e.g. 5m, 15m, 1h, 4h.
    pub timeframes: Vec<TimeframeData>,
    pub funding_rate: f64,
    /// Fractional change in open interest over the last hour.
    pub oi_delta_1h: f64,
    pub spread_bps: f64,
    pub depth_usd: f64,
    /// BTC closes aligned with this symbol's primary timeframe, for correlation.
    pub btc_closes: Vec<f64>,
}

/// Relative importance of each factor. See the module note: these are a prior.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Weights {
    pub trend_alignment: f64,
    pub volatility_band: f64,
    pub efficiency_ratio: f64,
    pub liquidity_window: f64,
    pub positioning: f64,
    pub book_quality: f64,
}

impl Default for Weights {
    fn default() -> Self {
        // Rationale for the ordering, pending calibration:
        // - efficiency_ratio and trend_alignment carry the most, because whether the
        //   market is actually going somewhere dominates everything else.
        // - volatility_band matters but is a hump, so it is easy to over-weight.
        // - book_quality and liquidity_window are execution-quality terms: they rarely
        //   make a setup good, they frequently make one unaffordable.
        // - positioning is the smallest because its extreme cases are already vetoed;
        //   this term only shapes the approach to that cliff.
        Self {
            trend_alignment: 0.25,
            volatility_band: 0.15,
            efficiency_ratio: 0.25,
            liquidity_window: 0.10,
            positioning: 0.10,
            book_quality: 0.15,
        }
    }
}

impl Weights {
    fn total(&self) -> f64 {
        self.trend_alignment
            + self.volatility_band
            + self.efficiency_ratio
            + self.liquidity_window
            + self.positioning
            + self.book_quality
    }
}

/// Thresholds and periods. Tunable without touching the scoring logic.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ScoringConfig {
    pub max_spread_bps: f64,
    pub min_depth_usd: f64,
    pub max_feed_age_ms: i64,
    pub max_abs_funding: f64,
    pub atr_period: usize,
    pub er_period: usize,
    pub ema_fast: usize,
    pub ema_slow: usize,
    /// How many recent ATR observations define the volatility distribution.
    pub vol_percentile_window: usize,
    /// Centre of the tradable volatility band, as a percentile.
    pub vol_band_center: f64,
    /// Width of the tradable volatility band (Gaussian sigma, in percentile units).
    pub vol_band_sigma: f64,
    /// Depth at which book quality is considered perfect.
    pub target_depth_usd: f64,
    /// |EMA fast - slow| below this fraction of price counts as no direction.
    pub trend_deadband_pct: f64,
    /// Aggregation period for the variance ratio test.
    pub vr_q: usize,
    /// Trailing returns used for the variance ratio.
    pub vr_window: usize,
    /// A variance ratio below this labels the market mean-reverting and suppresses every
    /// trend label. Set just under 1.0 (a pure random walk) so only a real reverting
    /// tendency trips it.
    pub vr_mean_reversion_max: f64,
    /// A trend label additionally requires the variance ratio to be at least this — the
    /// chart alone is not allowed to assert persistence.
    pub vr_trend_min: f64,
    /// Bars of confirmation either side of a swing pivot. Larger means fewer, more
    /// significant swings and more lag before one is confirmed.
    pub swing_lookback: usize,
    /// Cap on published levels of each kind, most recent first. Bounds the pulse payload.
    pub max_levels_per_kind: usize,
    pub weights: Weights,
}

impl Default for ScoringConfig {
    fn default() -> Self {
        Self {
            max_spread_bps: 8.0,
            min_depth_usd: 50_000.0,
            max_feed_age_ms: 15_000,
            max_abs_funding: 0.0015, // 0.15% per interval is already extreme
            atr_period: 14,
            er_period: 20,
            ema_fast: 21,
            ema_slow: 55,
            vol_percentile_window: 200,
            vol_band_center: 0.55,
            vol_band_sigma: 0.18,
            target_depth_usd: 500_000.0,
            trend_deadband_pct: 0.0005,
            vr_q: 4,
            vr_window: 400,
            vr_mean_reversion_max: 0.95,
            vr_trend_min: 1.00,
            swing_lookback: 3,
            max_levels_per_kind: 10,
            weights: Weights::default(),
        }
    }
}

/// Outcome of scoring one snapshot.
#[derive(Debug, Clone)]
pub struct Scored {
    pub pulse: Pulse,
    /// Signed net trend direction across timeframes, `-1.0..=1.0`. Not published on the
    /// pulse — the regime label carries direction on the wire — but useful for tests
    /// and diagnostics.
    pub net_direction: f64,
}

/// Score one symbol.
pub fn score(snapshot: &MarketSnapshot, cfg: &ScoringConfig) -> Scored {
    let mut vetoes = Vec::new();

    // ---- stage 1: hard gates -------------------------------------------------
    if snapshot.now_ms.saturating_sub(snapshot.feed_ts) > cfg.max_feed_age_ms {
        vetoes.push(Veto::StaleFeed);
    }
    if snapshot.spread_bps > cfg.max_spread_bps {
        vetoes.push(Veto::SpreadTooWide);
    }
    if snapshot.depth_usd < cfg.min_depth_usd {
        vetoes.push(Veto::InsufficientDepth);
    }
    if snapshot.funding_rate.abs() > cfg.max_abs_funding {
        vetoes.push(Veto::FundingExtreme);
    }

    // ---- stage 2: factors ----------------------------------------------------
    let primary = primary_timeframe(snapshot);
    let closes: Vec<f64> = primary
        .map(|tf| tf.candles.iter().map(|c| c.close).collect())
        .unwrap_or_default();

    let (trend_alignment, net_direction) = trend(snapshot, cfg);

    let er = primary
        .and_then(|_| efficiency_ratio(&closes, cfg.er_period))
        .unwrap_or(0.0);

    let (atr_pct, atr_percentile) = volatility(primary, cfg);
    let volatility_band = hump(atr_percentile, cfg.vol_band_center, cfg.vol_band_sigma);

    let liquidity_window = session_liquidity(snapshot.feed_ts);
    let positioning = positioning_score(snapshot, cfg);
    let book_quality = book_quality_score(snapshot, cfg);

    // Insufficient history is a veto, not a low score: a confident number computed from
    // a 3-candle window is worse than no number at all.
    let has_history = primary
        .map(|tf| tf.candles.len() > cfg.atr_period.max(cfg.er_period).max(cfg.ema_slow))
        .unwrap_or(false);
    if !has_history {
        vetoes.push(Veto::InsufficientHistory);
    }

    let factors = Factors {
        trend_alignment,
        volatility_band,
        efficiency_ratio: er,
        liquidity_window,
        positioning,
        book_quality,
    };

    let raw = weighted_score(&factors, &cfg.weights);

    // ---- stage 3: regime -----------------------------------------------------
    // Log returns over the trailing window, for the variance ratio test. Log rather than
    // simple returns because the test's null is additive random walk.
    let vr_returns: Vec<f64> = {
        let start = closes.len().saturating_sub(cfg.vr_window);
        closes
            .get(start..)
            .unwrap_or(&closes)
            .windows(2)
            .filter_map(|w| {
                let prev = *w.first()?;
                let cur = *w.get(1)?;
                (prev > 0.0 && cur > 0.0).then(|| (cur / prev).ln())
            })
            .collect()
    };
    let vr = variance_ratio(&vr_returns, cfg.vr_q);
    let regime = classify(
        er,
        trend_alignment,
        net_direction,
        atr_percentile,
        vr.as_ref(),
        cfg,
    );

    // Market structure from the primary timeframe. Absolute ATR (not the percentage) is
    // what scales the order-block displacement threshold.
    let reference_price_for_atr = closes.last().copied().unwrap_or(0.0);
    let atr_abs = atr_pct / 100.0 * reference_price_for_atr;
    let structure = primary
        .map(|tf| build_structure(&tf.candles, atr_abs, reference_price_for_atr, cfg))
        .unwrap_or_default();

    let btc_correlation_30d = {
        let sym_returns = returns(&closes);
        let btc_returns = returns(&snapshot.btc_closes);
        let n = sym_returns.len().min(btc_returns.len());
        if n >= 2 {
            let a: Vec<f64> = sym_returns.iter().rev().take(n).copied().collect();
            let b: Vec<f64> = btc_returns.iter().rev().take(n).copied().collect();
            correlation(&a, &b).unwrap_or(0.0)
        } else {
            0.0
        }
    };

    let reference_price = closes.last().copied().unwrap_or(0.0);

    let context = Context {
        atr_pct,
        atr_percentile_30d: atr_percentile,
        funding_rate: snapshot.funding_rate,
        oi_delta_1h: snapshot.oi_delta_1h,
        spread_bps: snapshot.spread_bps,
        btc_correlation_30d,
    };

    let pulse = Pulse::new(
        snapshot.symbol.clone(),
        snapshot.now_ms,
        snapshot.feed_ts,
        regime,
        raw,
        vetoes,
        factors,
        structure,
        context,
        reference_price,
    );

    Scored {
        pulse,
        net_direction,
    }
}

/// Convert a detected structure map into the wire shape.
///
/// Levels are capped to the ones NEAREST current price. A symbol in a long range
/// accumulates hundreds of unfilled gaps and swing clusters; publishing them all would
/// bloat every pulse, and publishing an arbitrary subset is worse — only levels price can
/// plausibly reach matter for a decision now.
///
/// Selecting by position in the vector was wrong and shipped briefly: `liquidity_pools`
/// sorts its output by PRICE, so "the last N" meant the ten highest-priced pools. Live
/// output on 2026-08-02 published pools at 77,640 while BTC traded at 62,530 — 25% away
/// and worthless. Distance from price is the only ordering that means the same thing for
/// every level kind.
fn build_structure(
    candles: &[Candle],
    atr_abs: f64,
    current_price: f64,
    cfg: &ScoringConfig,
) -> Structure {
    let map = crate::structure::analyze(candles, atr_abs, cfg.swing_lookback);
    let cap = cfg.max_levels_per_kind;

    let nearest = |mut v: Vec<Level>| -> Vec<Level> {
        if current_price > 0.0 {
            // Distance to the level's nearest edge; zero when price is inside it.
            v.sort_by(|a, b| {
                let d = |l: &Level| {
                    if current_price < l.low {
                        l.low - current_price
                    } else if current_price > l.high {
                        current_price - l.high
                    } else {
                        0.0
                    }
                };
                d(a).total_cmp(&d(b))
            });
        }
        v.truncate(cap);
        v
    };

    Structure {
        htf_bias: map.bias.map(|b| b.to_string()),
        swing_high: map.swings.iter().rev().find(|s| s.is_high).map(|s| s.price),
        swing_low: map
            .swings
            .iter()
            .rev()
            .find(|s| !s.is_high)
            .map(|s| s.price),
        order_blocks: nearest(
            map.order_blocks
                .iter()
                .map(|ob| Level {
                    low: ob.low,
                    high: ob.high,
                    timeframe: Some(if ob.bullish { "bullish" } else { "bearish" }.to_string()),
                })
                .collect(),
        ),
        fvgs: nearest(
            map.fvgs
                .iter()
                .map(|g| Level {
                    low: g.low,
                    high: g.high,
                    timeframe: Some(if g.bullish { "bullish" } else { "bearish" }.to_string()),
                })
                .collect(),
        ),
        liquidity_pools: nearest(map.liquidity_pools),
        key_levels: nearest(
            map.swings
                .iter()
                .map(|s| Level {
                    low: s.price,
                    high: s.price,
                    timeframe: Some(if s.is_high { "swing_high" } else { "swing_low" }.to_string()),
                })
                .collect(),
        ),
    }
}

/// Highest-weight timeframe with usable data — the one factor calculations anchor to.
fn primary_timeframe(snapshot: &MarketSnapshot) -> Option<&TimeframeData> {
    snapshot
        .timeframes
        .iter()
        .filter(|tf| !tf.candles.is_empty())
        .max_by(|a, b| a.weight.total_cmp(&b.weight))
}

/// Multi-timeframe EMA-stack agreement.
///
/// Returns `(magnitude, net_direction)`. Magnitude is direction-agnostic — a clean
/// downtrend is as tradable as a clean uptrend — and lives in `0.0..=1.0`. Direction
/// carries the sign for regime classification.
///
/// Timeframes that lack enough history contribute nothing rather than voting zero: an
/// absent opinion must not be counted as disagreement.
fn trend(snapshot: &MarketSnapshot, cfg: &ScoringConfig) -> (f64, f64) {
    let mut weighted_sum = 0.0;
    let mut weight_total = 0.0;

    for tf in &snapshot.timeframes {
        let closes: Vec<f64> = tf.candles.iter().map(|c| c.close).collect();
        let (Some(fast), Some(slow)) = (ema(&closes, cfg.ema_fast), ema(&closes, cfg.ema_slow))
        else {
            continue;
        };
        let Some(price) = closes.last() else { continue };
        if *price <= 0.0 {
            continue;
        }

        let separation = (fast - slow) / price;
        let direction = if separation.abs() < cfg.trend_deadband_pct {
            0.0
        } else if separation > 0.0 {
            1.0
        } else {
            -1.0
        };

        weighted_sum += direction * tf.weight;
        weight_total += tf.weight;
    }

    if weight_total <= f64::EPSILON {
        return (0.0, 0.0);
    }
    let net = weighted_sum / weight_total;
    (net.abs().clamp(0.0, 1.0), net.clamp(-1.0, 1.0))
}

/// Current ATR as a fraction of price, plus its percentile against its own recent
/// distribution.
///
/// Percentile rather than an absolute threshold because 2% daily range is calm for one
/// symbol and extreme for another — an absolute cutoff would be wrong for both.
fn volatility(primary: Option<&TimeframeData>, cfg: &ScoringConfig) -> (f64, f64) {
    let Some(tf) = primary else { return (0.0, 0.5) };

    let Some(current_atr) = atr(&tf.candles, cfg.atr_period) else {
        return (0.0, 0.5);
    };
    let price = tf.candles.last().map(|c| c.close).unwrap_or(0.0);
    if price <= 0.0 {
        return (0.0, 0.5);
    }
    let atr_pct = current_atr / price * 100.0;

    // Rolling ATR history: recompute over expanding suffixes of the window.
    let n = tf.candles.len();
    let start = n.saturating_sub(cfg.vol_percentile_window);
    let mut history = Vec::new();
    let mut idx = start + cfg.atr_period + 1;
    while idx <= n {
        if let Some(window) = tf.candles.get(start..idx) {
            if let Some(a) = atr(window, cfg.atr_period) {
                let p = window.last().map(|c| c.close).unwrap_or(0.0);
                if p > 0.0 {
                    history.push(a / p * 100.0);
                }
            }
        }
        idx += 1;
    }

    // With no distribution to compare against, claim the neutral midpoint rather than
    // inventing an extreme in either direction.
    let percentile = percentile_rank(&history, atr_pct).unwrap_or(0.5);
    (atr_pct, percentile)
}

/// Gaussian hump: peaks at `center`, falls off either side.
///
/// The volatility factor is the one non-monotonic component. Too quiet means no movement
/// to capture; too wild means stop-hunt territory. Treating volatility as monotonic —
/// "more is better" or "less is better" — is the most common way a volatility term makes
/// a scorer actively worse.
fn hump(x: f64, center: f64, sigma: f64) -> f64 {
    if sigma <= f64::EPSILON || x.is_nan() {
        return 0.0;
    }
    let z = (x - center) / sigma;
    (-0.5 * z * z).exp().clamp(0.0, 1.0)
}

/// Session liquidity from the clock. Deterministic, no market data needed.
///
/// The London-New York overlap is when size can actually be moved; the late-Asia hours
/// are when stops get picked off in thin books.
fn session_liquidity(ts_ms: i64) -> f64 {
    let hour = ((ts_ms / 3_600_000) % 24 + 24) % 24;
    match hour {
        12..=15 => 1.00, // London-NY overlap
        16..=20 => 0.85, // New York
        7..=11 => 0.80,  // London
        21..=23 => 0.45, // NY close into Asia
        0..=2 => 0.40,   // Asia open
        _ => 0.55,       // Asia mid-session
    }
}

/// How crowded the trade is. Low when positioning is one-sided.
///
/// Extreme funding is already a veto; this term shapes the approach to that cliff.
/// Rising open interest alongside stretched funding is the specific pattern that
/// precedes liquidation cascades, so the two compound rather than average.
fn positioning_score(snapshot: &MarketSnapshot, cfg: &ScoringConfig) -> f64 {
    if cfg.max_abs_funding <= f64::EPSILON {
        return 1.0;
    }
    let funding_stretch = (snapshot.funding_rate.abs() / cfg.max_abs_funding).clamp(0.0, 1.0);

    // Crowding worsens when open interest is building into stretched funding.
    let oi_amplifier = if snapshot.oi_delta_1h > 0.0 {
        1.0 + snapshot.oi_delta_1h.clamp(0.0, 1.0)
    } else {
        1.0
    };

    (1.0 - (funding_stretch * oi_amplifier).clamp(0.0, 1.0)).clamp(0.0, 1.0)
}

/// Execution quality of the book. Bounded by its *worse* dimension, not the average —
/// a deep book with a blown-out spread is not half-good, it is expensive.
fn book_quality_score(snapshot: &MarketSnapshot, cfg: &ScoringConfig) -> f64 {
    let spread = if cfg.max_spread_bps <= f64::EPSILON {
        0.0
    } else {
        1.0 - (snapshot.spread_bps.max(0.0) / cfg.max_spread_bps).clamp(0.0, 1.0)
    };
    let depth = if cfg.target_depth_usd <= f64::EPSILON {
        0.0
    } else {
        (snapshot.depth_usd.max(0.0) / cfg.target_depth_usd).clamp(0.0, 1.0)
    };
    spread.min(depth)
}

fn weighted_score(f: &Factors, w: &Weights) -> f64 {
    let total = w.total();
    if total <= f64::EPSILON {
        return 0.0;
    }
    let sum = f.trend_alignment * w.trend_alignment
        + f.volatility_band * w.volatility_band
        + f.efficiency_ratio * w.efficiency_ratio
        + f.liquidity_window * w.liquidity_window
        + f.positioning * w.positioning
        + f.book_quality * w.book_quality;
    (sum / total * 100.0).clamp(0.0, 100.0)
}

/// Regime is orthogonal to tradability: it describes behaviour, not opportunity.
fn classify(
    er: f64,
    alignment: f64,
    direction: f64,
    vol_percentile: f64,
    vr: Option<&VarianceRatio>,
    cfg: &ScoringConfig,
) -> Regime {
    // Violent and directionless beats every other label — this is the state that looks
    // like opportunity on a chart and is not.
    if vol_percentile > 0.90 && er < 0.30 {
        return Regime::VolatileChop;
    }

    let looks_trending = er >= 0.35 && alignment >= 0.5;

    match vr {
        // Reverting underneath: never emit a trend label, however clean the stack looks.
        Some(v) if v.ratio < cfg.vr_mean_reversion_max => Regime::MeanReverting,
        // Persistent enough to back a directional call.
        Some(v) if looks_trending && v.ratio >= cfg.vr_trend_min => {
            if direction > 0.0 {
                Regime::TrendingUp
            } else {
                Regime::TrendingDown
            }
        }
        // Chart says trend, the variance ratio will not confirm it. Abstain.
        Some(_) => Regime::Ranging,
        // No variance ratio (too little history): fall back to the chart, since a
        // missing test is not evidence of mean reversion.
        None if looks_trending => {
            if direction > 0.0 {
                Regime::TrendingUp
            } else {
                Regime::TrendingDown
            }
        }
        None => Regime::Ranging,
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn candles_from(closes: &[f64], range: f64) -> Vec<Candle> {
        closes
            .iter()
            .enumerate()
            .map(|(i, c)| Candle {
                open: *c,
                high: c + range / 2.0,
                low: c - range / 2.0,
                close: *c,
                volume: 1.0,
                close_time: i as i64 * 60_000,
            })
            .collect()
    }

    fn line(from: f64, to: f64, n: usize) -> Vec<f64> {
        let step = (to - from) / (n.saturating_sub(1)).max(1) as f64;
        (0..n).map(|i| from + step * i as f64).collect()
    }

    fn chop(base: f64, n: usize) -> Vec<f64> {
        (0..n)
            .map(|i| base + if i % 2 == 0 { 1.0 } else { -1.0 })
            .collect()
    }

    /// A healthy snapshot: clean uptrend, tight book, neutral funding, peak session.
    fn good_snapshot() -> MarketSnapshot {
        let closes = line(100.0, 160.0, 300);
        MarketSnapshot {
            symbol: "BTCUSDT".into(),
            // 1970-01-01T14:00Z — inside the London-NY overlap.
            now_ms: 14 * 3_600_000,
            feed_ts: 14 * 3_600_000,
            timeframes: vec![
                TimeframeData {
                    label: "15m",
                    weight: 1.0,
                    candles: candles_from(&closes, 1.0),
                },
                TimeframeData {
                    label: "1h",
                    weight: 2.0,
                    candles: candles_from(&closes, 1.0),
                },
                TimeframeData {
                    label: "4h",
                    weight: 3.0,
                    candles: candles_from(&closes, 1.0),
                },
            ],
            funding_rate: 0.00001,
            oi_delta_1h: 0.0,
            spread_bps: 0.5,
            depth_usd: 2_000_000.0,
            btc_closes: closes,
        }
    }

    // ---- vetoes ------------------------------------------------------------

    #[test]
    fn a_healthy_market_scores_and_is_not_vetoed() {
        let s = score(&good_snapshot(), &ScoringConfig::default());
        assert!(
            s.pulse.vetoes.is_empty(),
            "unexpected vetoes: {:?}",
            s.pulse.vetoes
        );
        assert!(
            s.pulse.tradability > 50,
            "healthy market scored {}",
            s.pulse.tradability
        );
    }

    #[test]
    fn a_blown_out_spread_zeroes_an_otherwise_perfect_setup() {
        // The whole point of stage 1: pristine trend, untradeable book.
        let mut snap = good_snapshot();
        snap.spread_bps = 50.0;
        let s = score(&snap, &ScoringConfig::default());
        assert!(s.pulse.vetoes.contains(&Veto::SpreadTooWide));
        assert_eq!(s.pulse.tradability, 0);
    }

    #[test]
    fn each_gate_vetoes_independently() {
        let cfg = ScoringConfig::default();

        let mut thin = good_snapshot();
        thin.depth_usd = 1_000.0;
        assert!(score(&thin, &cfg)
            .pulse
            .vetoes
            .contains(&Veto::InsufficientDepth));

        let mut stale = good_snapshot();
        stale.now_ms = stale.feed_ts + 60_000;
        assert!(score(&stale, &cfg).pulse.vetoes.contains(&Veto::StaleFeed));

        let mut funded = good_snapshot();
        funded.funding_rate = 0.01;
        assert!(score(&funded, &cfg)
            .pulse
            .vetoes
            .contains(&Veto::FundingExtreme));
    }

    #[test]
    fn too_little_history_is_vetoed_not_scored_low() {
        let mut snap = good_snapshot();
        let short = line(100.0, 105.0, 10);
        snap.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 1.0,
            candles: candles_from(&short, 1.0),
        }];
        let s = score(&snap, &ScoringConfig::default());
        assert!(s.pulse.vetoes.contains(&Veto::InsufficientHistory));
        assert_eq!(s.pulse.tradability, 0);
    }

    #[test]
    fn vetoes_accumulate_rather_than_short_circuit() {
        // Every reason must be reported: a user shown one blocker who fixes it and
        // still sees zero has been misled about why.
        let mut snap = good_snapshot();
        snap.spread_bps = 99.0;
        snap.depth_usd = 10.0;
        snap.funding_rate = 0.5;
        let s = score(&snap, &ScoringConfig::default());
        assert!(s.pulse.vetoes.len() >= 3, "only got {:?}", s.pulse.vetoes);
    }

    // ---- regime ------------------------------------------------------------

    #[test]
    fn a_clean_uptrend_is_classified_as_trending_up() {
        assert_eq!(
            score(&good_snapshot(), &ScoringConfig::default())
                .pulse
                .regime,
            Regime::TrendingUp
        );
    }

    #[test]
    fn a_clean_downtrend_is_trending_down_and_scores_as_well_as_up() {
        let mut down = good_snapshot();
        let closes = line(160.0, 100.0, 300);
        down.timeframes = good_snapshot()
            .timeframes
            .iter()
            .map(|tf| TimeframeData {
                label: tf.label,
                weight: tf.weight,
                candles: candles_from(&closes, 1.0),
            })
            .collect();
        down.btc_closes = closes;

        let cfg = ScoringConfig::default();
        let s_down = score(&down, &cfg);
        let s_up = score(&good_snapshot(), &cfg);

        assert_eq!(s_down.pulse.regime, Regime::TrendingDown);
        // Direction-agnostic: a short setup is not worth less than a long one.
        let delta = (s_down.pulse.tradability as i32 - s_up.pulse.tradability as i32).abs();
        assert!(
            delta <= 2,
            "up {} vs down {}",
            s_up.pulse.tradability,
            s_down.pulse.tradability
        );
    }

    #[test]
    fn chop_is_not_classified_as_a_trend() {
        let mut snap = good_snapshot();
        let closes = chop(100.0, 300);
        snap.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 1.0,
            candles: candles_from(&closes, 0.5),
        }];
        snap.btc_closes = closes;
        let regime = score(&snap, &ScoringConfig::default()).pulse.regime;
        // MeanReverting is the sharpest correct answer for a strictly alternating
        // series — the variance ratio detects it directly. Ranging/VolatileChop are
        // acceptable; a trend label is not.
        assert!(
            matches!(
                regime,
                Regime::MeanReverting | Regime::Ranging | Regime::VolatileChop
            ),
            "chop classified as {regime:?}"
        );
    }

    #[test]
    fn chop_scores_below_a_clean_trend() {
        let cfg = ScoringConfig::default();
        let mut choppy = good_snapshot();
        let closes = chop(100.0, 300);
        choppy.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 1.0,
            candles: candles_from(&closes, 0.5),
        }];
        choppy.btc_closes = closes;

        let trend_score = score(&good_snapshot(), &cfg).pulse.tradability;
        let chop_score = score(&choppy, &cfg).pulse.tradability;
        assert!(
            chop_score < trend_score,
            "chop {chop_score} >= trend {trend_score}"
        );
    }

    // ---- factors -----------------------------------------------------------

    #[test]
    fn volatility_band_is_a_hump_not_a_ramp() {
        // The defining property: both extremes score worse than the middle.
        let mid = hump(0.55, 0.55, 0.18);
        let dead = hump(0.02, 0.55, 0.18);
        let wild = hump(0.99, 0.55, 0.18);
        assert!(
            mid > dead && mid > wild,
            "mid {mid} dead {dead} wild {wild}"
        );
        assert!((mid - 1.0).abs() < 1e-9);
    }

    #[test]
    fn book_quality_is_bounded_by_its_worse_dimension() {
        let cfg = ScoringConfig::default();
        let mut snap = good_snapshot();
        // Excellent depth, terrible spread. Averaging would call this ~0.5.
        snap.depth_usd = 10_000_000.0;
        snap.spread_bps = cfg.max_spread_bps * 0.99;
        let q = book_quality_score(&snap, &cfg);
        assert!(q < 0.05, "deep book masked a blown spread: {q}");
    }

    #[test]
    fn session_liquidity_peaks_at_the_london_ny_overlap() {
        let overlap = session_liquidity(14 * 3_600_000);
        let asia = session_liquidity(3_600_000);
        assert!(overlap > asia, "overlap {overlap} not above asia {asia}");
        assert!((overlap - 1.0).abs() < 1e-9);
    }

    #[test]
    fn session_liquidity_handles_negative_and_huge_timestamps() {
        for ts in [-1_000_000_i64, 0, i64::MAX / 2] {
            let v = session_liquidity(ts);
            assert!((0.0..=1.0).contains(&v), "ts {ts} produced {v}");
        }
    }

    #[test]
    fn rising_open_interest_into_stretched_funding_compounds_the_penalty() {
        let cfg = ScoringConfig::default();
        let mut flat_oi = good_snapshot();
        flat_oi.funding_rate = cfg.max_abs_funding * 0.6;
        flat_oi.oi_delta_1h = 0.0;

        let mut building = flat_oi.clone();
        building.oi_delta_1h = 0.5;

        assert!(
            positioning_score(&building, &cfg) < positioning_score(&flat_oi, &cfg),
            "OI building into stretched funding was not penalised"
        );
    }

    #[test]
    fn an_absent_timeframe_does_not_vote_against_the_trend() {
        // A timeframe with too little history must abstain. Counting it as a zero vote
        // would make a clean trend look conflicted purely from a short warm-up buffer.
        let cfg = ScoringConfig::default();
        let full = good_snapshot();
        let mut with_stub = full.clone();
        with_stub.timeframes.push(TimeframeData {
            label: "1d",
            weight: 10.0,
            candles: candles_from(&line(100.0, 101.0, 3), 1.0),
        });

        let (a, _) = trend(&full, &cfg);
        let (b, _) = trend(&with_stub, &cfg);
        assert!(
            (a - b).abs() < 1e-9,
            "stub timeframe diluted alignment: {a} vs {b}"
        );
    }

    // ---- score properties --------------------------------------------------

    #[test]
    fn every_factor_stays_within_zero_and_one() {
        let cfg = ScoringConfig::default();
        for snap in [good_snapshot(), degenerate_snapshot()] {
            let f = score(&snap, &cfg).pulse.factors;
            for (name, v) in [
                ("trend_alignment", f.trend_alignment),
                ("volatility_band", f.volatility_band),
                ("efficiency_ratio", f.efficiency_ratio),
                ("liquidity_window", f.liquidity_window),
                ("positioning", f.positioning),
                ("book_quality", f.book_quality),
            ] {
                assert!((0.0..=1.0).contains(&v), "{name} escaped range: {v}");
                assert!(v.is_finite(), "{name} was not finite: {v}");
            }
        }
    }

    fn degenerate_snapshot() -> MarketSnapshot {
        MarketSnapshot {
            symbol: "EMPTY".into(),
            now_ms: 0,
            feed_ts: 0,
            timeframes: vec![],
            funding_rate: 0.0,
            oi_delta_1h: 0.0,
            spread_bps: 0.0,
            depth_usd: 0.0,
            btc_closes: vec![],
        }
    }

    #[test]
    fn an_empty_snapshot_does_not_panic_and_is_vetoed() {
        let s = score(&degenerate_snapshot(), &ScoringConfig::default());
        assert!(s.pulse.vetoes.contains(&Veto::InsufficientHistory));
        assert_eq!(s.pulse.tradability, 0);
    }

    #[test]
    fn structure_reaches_the_pulse_and_is_bounded() {
        // The `structure` field shipped empty until 2026-08-02 because the scorer passed
        // Structure::default(). An empty structure is indistinguishable from "no levels
        // exist", so the per-user layer had nothing to reason over.
        let mut snap = good_snapshot();
        // Oscillation is required for swings — a monotonic ramp has no strict interior
        // extremum and correctly yields none.
        let closes: Vec<f64> = (0..400)
            .map(|i| {
                let t = i as f64;
                100.0 + t * 0.05 + 10.0 * (t * std::f64::consts::TAU / 20.0).sin()
            })
            .collect();
        snap.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 2.0,
            candles: closes
                .iter()
                .enumerate()
                .map(|(i, c)| Candle {
                    open: *c,
                    high: c + 0.5,
                    low: c - 0.5,
                    close: *c,
                    volume: 1.0,
                    close_time: i as i64 * 3_600_000,
                })
                .collect(),
        }];

        let cfg = ScoringConfig::default();
        let s = score(&snap, &cfg);
        let st = &s.pulse.structure;

        assert!(st.swing_high.is_some(), "no swing high reached the pulse");
        assert!(st.swing_low.is_some(), "no swing low reached the pulse");
        assert!(!st.key_levels.is_empty(), "no key levels reached the pulse");

        // Payload bound: a ranging symbol accumulates hundreds of levels, and publishing
        // them all would bloat every pulse and bury the ones near price.
        for (name, levels) in [
            ("order_blocks", &st.order_blocks),
            ("fvgs", &st.fvgs),
            ("liquidity_pools", &st.liquidity_pools),
            ("key_levels", &st.key_levels),
        ] {
            assert!(
                levels.len() <= cfg.max_levels_per_kind,
                "{name} published {} levels, cap is {}",
                levels.len(),
                cfg.max_levels_per_kind
            );
        }
    }

    #[test]
    fn published_levels_are_the_ones_nearest_price() {
        // Regression, caught in live output 2026-08-02: the cap kept the LAST N entries
        // of each vector, but liquidity_pools sorts by price, so it published the ten
        // highest-priced pools — 77,640 while BTC traded at 62,530, 25% away and
        // worthless. Selecting by distance is the only ordering that means the same
        // thing for every level kind.
        let mut snap = good_snapshot();
        let closes: Vec<f64> = (0..500)
            .map(|i| {
                let t = i as f64;
                // Wide oscillation so levels form far above and below the final price.
                1000.0 + 300.0 * (t * std::f64::consts::TAU / 40.0).sin()
            })
            .collect();
        snap.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 2.0,
            candles: candles_from(&closes, 2.0),
        }];

        let cfg = ScoringConfig::default();
        let s = score(&snap, &cfg);
        let price = s.pulse.reference_price;

        let dist = |l: &Level| {
            if price < l.low {
                l.low - price
            } else if price > l.high {
                price - l.high
            } else {
                0.0
            }
        };

        for (name, levels) in [
            ("key_levels", &s.pulse.structure.key_levels),
            ("liquidity_pools", &s.pulse.structure.liquidity_pools),
        ] {
            if levels.len() < 2 {
                continue;
            }
            let distances: Vec<f64> = levels.iter().map(dist).collect();
            let sorted = distances.windows(2).all(|w| match (w.first(), w.get(1)) {
                (Some(a), Some(b)) => a <= b,
                _ => true,
            });
            assert!(
                sorted,
                "{name} not ordered by distance from price: {distances:?}"
            );
        }
    }

    #[test]
    fn structure_detection_never_panics_on_a_degenerate_snapshot() {
        let _ = score(&degenerate_snapshot(), &ScoringConfig::default());
        let mut flat = good_snapshot();
        flat.timeframes = vec![TimeframeData {
            label: "1h",
            weight: 1.0,
            candles: candles_from(&[100.0; 400], 0.0),
        }];
        let s = score(&flat, &ScoringConfig::default());
        // A perfectly flat market genuinely has no structure. Empty is the right answer.
        assert!(s.pulse.structure.key_levels.is_empty());
    }

    #[test]
    fn scoring_is_deterministic() {
        // Load-bearing for the differential tests against the Python oracle: the same
        // snapshot must always produce byte-identical output.
        let snap = good_snapshot();
        let cfg = ScoringConfig::default();
        let a = serde_json::to_string(&score(&snap, &cfg).pulse).expect("serialize");
        let b = serde_json::to_string(&score(&snap, &cfg).pulse).expect("serialize");
        assert_eq!(a, b);
    }

    #[test]
    fn weights_that_sum_to_zero_degrade_to_zero_not_nan() {
        let cfg = ScoringConfig {
            weights: Weights {
                trend_alignment: 0.0,
                volatility_band: 0.0,
                efficiency_ratio: 0.0,
                liquidity_window: 0.0,
                positioning: 0.0,
                book_quality: 0.0,
            },
            ..ScoringConfig::default()
        };
        let s = score(&good_snapshot(), &cfg);
        assert_eq!(s.pulse.tradability, 0);
    }

    #[test]
    fn the_score_is_monotonic_in_a_single_factor() {
        // Sanity on the aggregation: widening the spread while holding everything else
        // fixed must never raise the score.
        let cfg = ScoringConfig::default();
        let mut last = 101u8;
        for spread in [0.1_f64, 1.0, 2.0, 4.0, 7.0] {
            let mut snap = good_snapshot();
            snap.spread_bps = spread;
            let t = score(&snap, &cfg).pulse.tradability;
            assert!(
                t <= last,
                "score rose from {last} to {t} as spread widened to {spread}"
            );
            last = t;
        }
    }
}
