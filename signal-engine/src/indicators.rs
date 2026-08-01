//! Deterministic indicator math.
//!
//! Every function is pure and total: insufficient data returns `None` rather than a
//! plausible-looking number computed from a short window. A scorer that silently accepts
//! a 3-candle ATR produces confident garbage, which is worse than producing nothing —
//! hence the `Veto::InsufficientHistory` path in the scorer.
//!
//! The crate denies `indexing_slicing`, `unwrap_used`, and `panic`, so these are written
//! against iterators and `get()`. That is not ceremony: a panic here takes down the
//! shared signal plane, which by design is a single point of failure for every tenant.

/// One OHLCV bar. `close_time` is epoch millis at bar close.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Candle {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub close_time: i64,
}

impl Candle {
    /// True Range against the previous close: the classic max of the three ranges.
    /// Falls back to the bar's own range when there is no previous close.
    pub fn true_range(&self, prev_close: Option<f64>) -> f64 {
        let hl = self.high - self.low;
        match prev_close {
            Some(pc) => hl.max((self.high - pc).abs()).max((self.low - pc).abs()),
            None => hl,
        }
    }
}

/// Simple moving average of the last `period` values.
pub fn sma(values: &[f64], period: usize) -> Option<f64> {
    if period == 0 || values.len() < period {
        return None;
    }
    let sum: f64 = values.iter().rev().take(period).sum();
    Some(sum / period as f64)
}

/// Exponential moving average over the whole series, seeded with the SMA of the first
/// `period` values (the standard seeding — seeding with the first value alone biases the
/// early output toward it for several multiples of the period).
pub fn ema(values: &[f64], period: usize) -> Option<f64> {
    if period == 0 || values.len() < period {
        return None;
    }
    let mut iter = values.iter();
    let seed_sum: f64 = iter.by_ref().take(period).sum();
    let mut acc = seed_sum / period as f64;

    let k = 2.0 / (period as f64 + 1.0);
    for v in iter {
        acc = v * k + acc * (1.0 - k);
    }
    Some(acc)
}

/// Incremental EMA step — the whole reason an EMA is cheap to keep live.
///
/// Used by the feature store on each closed bar so a running EMA never rescans its
/// window. `ema()` above is the batch form used for seeding and for the differential
/// tests; the two must agree, which [`tests::incremental_ema_matches_batch`] pins.
pub fn ema_step(prev: f64, value: f64, period: usize) -> f64 {
    let k = 2.0 / (period as f64 + 1.0);
    value * k + prev * (1.0 - k)
}

/// Average True Range using Wilder's smoothing (not a plain SMA of TRs — Wilder's is
/// what every charting package means by "ATR", and the two diverge materially).
///
/// Needs `period + 1` candles: the first TR requires a previous close.
pub fn atr(candles: &[Candle], period: usize) -> Option<f64> {
    if period == 0 || candles.len() <= period {
        return None;
    }

    let trs: Vec<f64> = candles
        .windows(2)
        .filter_map(|w| match (w.first(), w.get(1)) {
            (Some(prev), Some(cur)) => Some(cur.true_range(Some(prev.close))),
            _ => None,
        })
        .collect();

    if trs.len() < period {
        return None;
    }

    let mut iter = trs.iter();
    let seed: f64 = iter.by_ref().take(period).sum();
    let mut acc = seed / period as f64;

    let n = period as f64;
    for tr in iter {
        acc = (acc * (n - 1.0) + tr) / n;
    }
    Some(acc)
}

/// Kaufman Efficiency Ratio over the last `period` closes: net directional travel
/// divided by total path length, in `0.0..=1.0`.
///
/// 1.0 is a straight line, 0.0 is pure noise that ends where it started. This is the
/// single best trend-versus-chop discriminator available from price alone, and unlike
/// ADX it needs no smoothing constant to argue about.
///
/// A perfectly flat window has zero path length. That is *undefined*, not efficient, so
/// it returns 0.0 — reporting 1.0 there would score a dead market as a perfect trend.
pub fn efficiency_ratio(closes: &[f64], period: usize) -> Option<f64> {
    if period == 0 || closes.len() < period + 1 {
        return None;
    }

    let window: Vec<f64> = closes
        .iter()
        .rev()
        .take(period + 1)
        .rev()
        .copied()
        .collect();
    let first = window.first()?;
    let last = window.last()?;

    let net = (last - first).abs();
    let path: f64 = window
        .windows(2)
        .filter_map(|w| Some((w.get(1)? - w.first()?).abs()))
        .sum();

    if path <= f64::EPSILON {
        return Some(0.0);
    }
    Some((net / path).clamp(0.0, 1.0))
}

/// Fraction of `sample` strictly below `value`, in `0.0..=1.0`.
///
/// Used to place current volatility against its own recent distribution, which is what
/// makes the volatility factor regime-relative: 2% daily range is calm for one symbol
/// and extreme for another, so an absolute threshold would be wrong for both.
pub fn percentile_rank(sample: &[f64], value: f64) -> Option<f64> {
    if sample.is_empty() || value.is_nan() {
        return None;
    }
    let below = sample.iter().filter(|s| !s.is_nan() && **s < value).count();
    let valid = sample.iter().filter(|s| !s.is_nan()).count();
    if valid == 0 {
        return None;
    }
    Some(below as f64 / valid as f64)
}

/// Pearson correlation between two equal-length series, in `-1.0..=1.0`.
///
/// Used for BTC correlation: when everything moves together, several "diversified"
/// positions are one position, and the per-user risk layer needs to know that.
pub fn correlation(a: &[f64], b: &[f64]) -> Option<f64> {
    let n = a.len();
    if n < 2 || n != b.len() {
        return None;
    }
    let nf = n as f64;
    let mean_a = a.iter().sum::<f64>() / nf;
    let mean_b = b.iter().sum::<f64>() / nf;

    let mut cov = 0.0;
    let mut var_a = 0.0;
    let mut var_b = 0.0;
    for (x, y) in a.iter().zip(b.iter()) {
        let da = x - mean_a;
        let db = y - mean_b;
        cov += da * db;
        var_a += da * da;
        var_b += db * db;
    }

    let denom = (var_a * var_b).sqrt();
    if denom <= f64::EPSILON {
        return None; // a constant series has no correlation, defined or otherwise
    }
    Some((cov / denom).clamp(-1.0, 1.0))
}

/// Simple returns series from a price series: `(p[i] - p[i-1]) / p[i-1]`.
/// Non-positive prices are skipped rather than producing infinities.
pub fn returns(prices: &[f64]) -> Vec<f64> {
    prices
        .windows(2)
        .filter_map(|w| {
            let prev = *w.first()?;
            let cur = *w.get(1)?;
            if prev > 0.0 {
                Some((cur - prev) / prev)
            } else {
                None
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    // See the note in pulse::tests — a panic is the failure report here.
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn candle(high: f64, low: f64, close: f64) -> Candle {
        Candle {
            open: close,
            high,
            low,
            close,
            volume: 1.0,
            close_time: 0,
        }
    }

    fn line(from: f64, to: f64, n: usize) -> Vec<f64> {
        if n < 2 {
            return vec![from];
        }
        let step = (to - from) / (n - 1) as f64;
        (0..n).map(|i| from + step * i as f64).collect()
    }

    // ---- guards -----------------------------------------------------------

    #[test]
    fn insufficient_data_returns_none_not_a_guess() {
        assert_eq!(sma(&[1.0, 2.0], 5), None);
        assert_eq!(ema(&[1.0, 2.0], 5), None);
        assert_eq!(efficiency_ratio(&[1.0, 2.0], 10), None);
        assert_eq!(atr(&[candle(2.0, 1.0, 1.5)], 14), None);
        assert_eq!(percentile_rank(&[], 1.0), None);
        assert_eq!(correlation(&[1.0], &[1.0]), None);
    }

    #[test]
    fn zero_period_is_rejected_rather_than_dividing_by_zero() {
        assert_eq!(sma(&[1.0, 2.0, 3.0], 0), None);
        assert_eq!(ema(&[1.0, 2.0, 3.0], 0), None);
        assert_eq!(efficiency_ratio(&[1.0, 2.0, 3.0], 0), None);
    }

    // ---- sma / ema --------------------------------------------------------

    #[test]
    fn sma_averages_only_the_last_period_values() {
        assert_eq!(sma(&[1.0, 2.0, 3.0, 100.0, 200.0], 2), Some(150.0));
    }

    #[test]
    fn ema_of_a_constant_series_is_that_constant() {
        let flat = vec![42.0; 50];
        let got = ema(&flat, 10).expect("enough data");
        assert!((got - 42.0).abs() < 1e-9, "got {got}");
    }

    #[test]
    fn ema_tracks_a_rising_series_above_its_seed() {
        let rising = line(100.0, 200.0, 60);
        let got = ema(&rising, 10).expect("enough data");
        assert!(got > 150.0 && got < 200.0, "EMA {got} not inside the trend");
    }

    #[test]
    fn incremental_ema_matches_batch() {
        // The feature store keeps EMAs live with ema_step(); the batch form seeds and
        // cross-checks them. If these ever diverge the live score drifts from every
        // backtest silently, so this equivalence is load-bearing.
        let series = line(100.0, 180.0, 80);
        let period = 12;

        let seed = sma(
            &series.iter().take(period).copied().collect::<Vec<_>>(),
            period,
        )
        .expect("seed");
        let incremental = series
            .iter()
            .skip(period)
            .fold(seed, |acc, v| ema_step(acc, *v, period));

        let batch = ema(&series, period).expect("batch");
        assert!(
            (incremental - batch).abs() < 1e-9,
            "incremental {incremental} != batch {batch}"
        );
    }

    // ---- atr --------------------------------------------------------------

    #[test]
    fn true_range_uses_the_gap_when_price_gaps_away() {
        // Bar range is 1.0, but it gapped up 10 from the previous close — TR is 11.
        let c = candle(21.0, 20.0, 20.5);
        assert_eq!(c.true_range(Some(10.0)), 11.0);
    }

    #[test]
    fn true_range_without_a_previous_close_is_the_bar_range() {
        assert_eq!(candle(21.0, 20.0, 20.5).true_range(None), 1.0);
    }

    #[test]
    fn atr_of_constant_range_candles_equals_that_range() {
        // Every bar spans exactly 2.0 and closes at the same place, so TR == 2.0
        // throughout and Wilder's smoothing must converge to it.
        let candles: Vec<Candle> = (0..40).map(|_| candle(11.0, 9.0, 10.0)).collect();
        let got = atr(&candles, 14).expect("enough data");
        assert!((got - 2.0).abs() < 1e-9, "got {got}");
    }

    #[test]
    fn atr_needs_one_more_candle_than_its_period() {
        let candles: Vec<Candle> = (0..14).map(|_| candle(11.0, 9.0, 10.0)).collect();
        assert_eq!(
            atr(&candles, 14),
            None,
            "14 candles cannot yield a 14-period ATR"
        );
        let candles: Vec<Candle> = (0..15).map(|_| candle(11.0, 9.0, 10.0)).collect();
        assert!(atr(&candles, 14).is_some());
    }

    // ---- efficiency ratio -------------------------------------------------

    #[test]
    fn efficiency_ratio_of_a_straight_line_is_one() {
        let got = efficiency_ratio(&line(100.0, 200.0, 30), 20).expect("enough data");
        assert!((got - 1.0).abs() < 1e-9, "got {got}");
    }

    #[test]
    fn efficiency_ratio_of_a_round_trip_is_zero() {
        // Up 50 then back down 50: lots of path, no net travel. This is exactly the
        // chop the factor exists to punish.
        let mut series = line(100.0, 150.0, 11);
        series.extend(line(149.0, 100.0, 10));
        let got = efficiency_ratio(&series, 20).expect("enough data");
        assert!(got < 0.01, "round trip scored {got}, expected ~0");
    }

    #[test]
    fn a_dead_flat_market_is_not_a_perfect_trend() {
        // Zero path length is undefined, not efficient. Returning 1.0 here would score
        // a market with no movement as the cleanest possible trend.
        let flat = vec![100.0; 30];
        assert_eq!(efficiency_ratio(&flat, 20), Some(0.0));
    }

    #[test]
    fn efficiency_ratio_is_direction_agnostic() {
        let up = efficiency_ratio(&line(100.0, 200.0, 30), 20).expect("up");
        let down = efficiency_ratio(&line(200.0, 100.0, 30), 20).expect("down");
        assert!((up - down).abs() < 1e-9, "up {up} != down {down}");
    }

    #[test]
    fn efficiency_ratio_stays_in_range_on_noisy_input() {
        let noisy: Vec<f64> = (0..200)
            .map(|i| 100.0 + ((i * 7919) % 23) as f64 - 11.0)
            .collect();
        let got = efficiency_ratio(&noisy, 50).expect("enough data");
        assert!((0.0..=1.0).contains(&got), "ER escaped its range: {got}");
    }

    // ---- percentile / correlation ----------------------------------------

    #[test]
    fn percentile_rank_places_a_value_in_its_distribution() {
        let sample: Vec<f64> = (1..=10).map(|i| i as f64).collect();
        assert_eq!(percentile_rank(&sample, 5.5), Some(0.5));
        assert_eq!(percentile_rank(&sample, 0.0), Some(0.0));
        assert_eq!(percentile_rank(&sample, 100.0), Some(1.0));
    }

    #[test]
    fn percentile_rank_rejects_nan_rather_than_ranking_it() {
        assert_eq!(percentile_rank(&[1.0, 2.0], f64::NAN), None);
    }

    #[test]
    fn correlation_detects_lockstep_and_opposition() {
        let a = line(1.0, 10.0, 10);
        let inverse: Vec<f64> = a.iter().map(|v| -v).collect();
        assert!((correlation(&a, &a).expect("self") - 1.0).abs() < 1e-9);
        assert!((correlation(&a, &inverse).expect("inverse") + 1.0).abs() < 1e-9);
    }

    #[test]
    fn correlation_of_a_constant_series_is_undefined_not_zero() {
        let flat = vec![5.0; 10];
        assert_eq!(correlation(&line(1.0, 10.0, 10), &flat), None);
    }

    #[test]
    fn correlation_rejects_mismatched_lengths() {
        assert_eq!(correlation(&[1.0, 2.0, 3.0], &[1.0, 2.0]), None);
    }

    // ---- returns ----------------------------------------------------------

    #[test]
    fn returns_are_simple_period_over_period() {
        let got = returns(&[100.0, 110.0, 99.0]);
        assert_eq!(got.len(), 2);
        assert!((got.first().copied().unwrap_or_default() - 0.10).abs() < 1e-9);
        assert!((got.get(1).copied().unwrap_or_default() + 0.10).abs() < 1e-9);
    }

    #[test]
    fn returns_skip_non_positive_prices_instead_of_producing_infinity() {
        let got = returns(&[0.0, 100.0, 110.0]);
        assert_eq!(got.len(), 1, "a zero price produced a bogus return");
        assert!(got.iter().all(|r| r.is_finite()));
    }
}
