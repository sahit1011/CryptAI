//! Estimators a quant desk would actually use.
//!
//! The retail versions of these are all available and all worse. Each choice here is a
//! variance or bias improvement with a citation behind it:
//!
//! - **Yang-Zhang volatility** over ATR. ATR throws away the open and treats a gap the
//!   same as a range. Yang-Zhang (2000) is the minimum-variance OHLC estimator that is
//!   simultaneously drift-independent and handles overnight jumps — roughly 7-14x more
//!   efficient than close-to-close for the same sample.
//! - **Lo-MacKinlay variance ratio** over "the EMAs are stacked". This is an actual
//!   hypothesis test against a random walk null, with a heteroskedasticity-robust
//!   z-statistic, so "trending" becomes a claim with a p-value instead of a vibe.
//! - **Hurst exponent** for persistence, as an independent second opinion on the
//!   variance ratio.
//! - **Robust z-scores** (median/MAD) over mean/σ. Crypto return distributions are
//!   fat-tailed; a single 8σ candle poisons a mean-based normalisation for as long as
//!   it stays in the window.
//!
//! Everything is pure and total: insufficient or degenerate input returns `None`, never
//! a plausible-looking number.

/// Yang-Zhang volatility components, all as variances (square to get σ).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct YangZhang {
    /// Close-to-open (overnight / inter-bar gap) variance.
    pub overnight: f64,
    /// Open-to-close (intra-bar) variance.
    pub open_close: f64,
    /// Rogers-Satchell variance — drift-independent by construction.
    pub rogers_satchell: f64,
    /// The combined Yang-Zhang variance.
    pub variance: f64,
}

impl YangZhang {
    /// Volatility (standard deviation) per bar.
    pub fn sigma(&self) -> f64 {
        self.variance.max(0.0).sqrt()
    }

    /// Annualised volatility given how many bars make up a year.
    pub fn annualized(&self, bars_per_year: f64) -> f64 {
        self.sigma() * bars_per_year.max(0.0).sqrt()
    }
}

/// One OHLC bar for volatility estimation. Separate from [`crate::Candle`] so the
/// estimators stay usable on any bar source.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Ohlc {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
}

impl Ohlc {
    fn is_valid(&self) -> bool {
        self.open > 0.0
            && self.high > 0.0
            && self.low > 0.0
            && self.close > 0.0
            && self.high >= self.low
    }
}

/// Rogers-Satchell variance for a single bar.
///
/// `ln(H/C)ln(H/O) + ln(L/C)ln(L/O)`. Its defining property is drift independence: a bar
/// that trends hard in one direction does not inflate the estimate the way Parkinson or
/// Garman-Klass would, which matters because crypto trends inside the bar constantly.
pub fn rogers_satchell_bar(bar: &Ohlc) -> Option<f64> {
    if !bar.is_valid() {
        return None;
    }
    let hc = (bar.high / bar.close).ln();
    let ho = (bar.high / bar.open).ln();
    let lc = (bar.low / bar.close).ln();
    let lo = (bar.low / bar.open).ln();
    let v = hc * ho + lc * lo;
    v.is_finite().then_some(v)
}

/// Yang-Zhang volatility over a window of bars.
///
/// Needs at least 3 bars (the overnight term is a variance over `n-1` gaps, so 2 bars
/// would give a zero-degrees-of-freedom estimate).
pub fn yang_zhang(bars: &[Ohlc]) -> Option<YangZhang> {
    let n = bars.len();
    if n < 3 || !bars.iter().all(Ohlc::is_valid) {
        return None;
    }

    // Overnight: ln(O_t / C_{t-1}). Open-to-close: ln(C_t / O_t), over the same bars so
    // the two series align.
    let mut overnight = Vec::with_capacity(n - 1);
    let mut open_close = Vec::with_capacity(n - 1);
    for w in bars.windows(2) {
        let (Some(prev), Some(cur)) = (w.first(), w.get(1)) else {
            continue;
        };
        overnight.push((cur.open / prev.close).ln());
        open_close.push((cur.close / cur.open).ln());
    }

    let var_o = sample_variance(&overnight)?;
    let var_c = sample_variance(&open_close)?;

    // Rogers-Satchell over the same bars used above (skip the first, which has no gap).
    let rs_values: Vec<f64> = bars
        .iter()
        .skip(1)
        .filter_map(rogers_satchell_bar)
        .collect();
    if rs_values.is_empty() {
        return None;
    }
    let var_rs = rs_values.iter().sum::<f64>() / rs_values.len() as f64;

    // k minimises the variance of the combined estimator (Yang & Zhang 2000).
    let m = overnight.len() as f64;
    if m <= 1.0 {
        return None;
    }
    let k = 0.34 / (1.34 + (m + 1.0) / (m - 1.0));

    let variance = var_o + k * var_c + (1.0 - k) * var_rs;
    if !variance.is_finite() {
        return None;
    }

    Some(YangZhang {
        overnight: var_o,
        open_close: var_c,
        rogers_satchell: var_rs,
        variance: variance.max(0.0),
    })
}

/// Result of a Lo-MacKinlay variance ratio test.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VarianceRatio {
    /// The ratio itself. 1.0 is a random walk, >1 trending, <1 mean-reverting.
    pub ratio: f64,
    /// Heteroskedasticity-robust z-statistic against the random walk null.
    pub z_statistic: f64,
    /// Two-sided p-value for that z.
    pub p_value: f64,
    /// Aggregation period tested.
    pub q: usize,
}

impl VarianceRatio {
    /// Whether the random walk null is rejected at the given significance level.
    ///
    /// This is the honest form of "is it trending": not a threshold on an indicator, but
    /// a rejected null. At the default 5% level roughly one in twenty random windows
    /// will trip it, which is exactly what the p-value is telling you.
    pub fn rejects_random_walk(&self, alpha: f64) -> bool {
        self.p_value < alpha
    }

    /// Signed strength in `-1.0..=1.0`: positive when trending, negative when
    /// mean-reverting, zero when the null survives.
    pub fn signal(&self, alpha: f64) -> f64 {
        if !self.rejects_random_walk(alpha) {
            return 0.0;
        }
        // Map the ratio's distance from 1 into a bounded score. tanh keeps a single
        // extreme window from dominating.
        (self.ratio - 1.0).tanh().clamp(-1.0, 1.0)
    }
}

/// Lo-MacKinlay (1988) variance ratio test with the heteroskedasticity-robust statistic.
///
/// Under a random walk, the variance of `q`-period returns is `q` times the variance of
/// 1-period returns, so the ratio is 1. Deviations mean autocorrelation: above 1 is
/// positive (momentum), below 1 is negative (mean reversion).
///
/// The robust statistic is used rather than the homoskedastic one because crypto
/// volatility clusters severely, and the homoskedastic version would reject the null
/// constantly on volatility clustering alone — reporting "trending" for what is only
/// heteroskedasticity.
pub fn variance_ratio(returns: &[f64], q: usize) -> Option<VarianceRatio> {
    let n = returns.len();
    if q < 2 || n < q * 2 {
        return None;
    }

    let mean = returns.iter().sum::<f64>() / n as f64;

    // Variance of 1-period returns (biased denominator, per the paper).
    let var_1: f64 = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / n as f64;
    if var_1 <= f64::EPSILON {
        return None;
    }

    // Variance of overlapping q-period returns.
    let q_sums: Vec<f64> = returns.windows(q).map(|w| w.iter().sum::<f64>()).collect();
    if q_sums.len() < 2 {
        return None;
    }
    let q_mean = mean * q as f64;
    let var_q: f64 = q_sums.iter().map(|s| (s - q_mean).powi(2)).sum::<f64>() / q_sums.len() as f64;

    let ratio = var_q / (q as f64 * var_1);
    if !ratio.is_finite() {
        return None;
    }

    // Heteroskedasticity-robust asymptotic variance:
    //   theta = sum_{j=1}^{q-1} [2(q-j)/q]^2 * delta_j
    let denom_sq = returns
        .iter()
        .map(|r| (r - mean).powi(2))
        .sum::<f64>()
        .powi(2);
    if denom_sq <= f64::EPSILON {
        return None;
    }

    let mut theta = 0.0;
    for j in 1..q {
        let mut num = 0.0;
        for t in j..n {
            let (Some(rt), Some(rtj)) = (returns.get(t), returns.get(t - j)) else {
                continue;
            };
            num += (rt - mean).powi(2) * (rtj - mean).powi(2);
        }
        let delta_j = num * n as f64 / denom_sq;
        let weight = 2.0 * (q - j) as f64 / q as f64;
        theta += weight * weight * delta_j;
    }

    if theta <= f64::EPSILON {
        return None;
    }

    let z = (ratio - 1.0) * (n as f64).sqrt() / theta.sqrt();
    if !z.is_finite() {
        return None;
    }

    Some(VarianceRatio {
        ratio,
        z_statistic: z,
        p_value: two_sided_p(z),
        q,
    })
}

/// Hurst exponent via rescaled range (R/S) analysis.
///
/// 0.5 is a random walk, >0.5 persistent (trends continue), <0.5 anti-persistent (mean
/// reverting). Carried as an independent second opinion on the variance ratio: R/S and
/// VR fail in different ways, so agreement between them is worth more than either alone.
///
/// R/S is biased on short samples — hence the `min_window` guard and the requirement for
/// several window sizes before a slope is fitted.
pub fn hurst_exponent(series: &[f64], min_window: usize) -> Option<f64> {
    let n = series.len();
    if min_window < 8 || n < min_window * 4 {
        return None;
    }

    let mut logs_n = Vec::new();
    let mut logs_rs = Vec::new();

    let mut window = min_window;
    while window <= n / 2 {
        let chunks = n / window;
        let mut rs_values = Vec::with_capacity(chunks);

        for c in 0..chunks {
            let start = c * window;
            let Some(chunk) = series.get(start..start + window) else {
                continue;
            };
            if let Some(rs) = rescaled_range(chunk) {
                rs_values.push(rs);
            }
        }

        if !rs_values.is_empty() {
            let mean_rs = rs_values.iter().sum::<f64>() / rs_values.len() as f64;
            if mean_rs > 0.0 {
                logs_n.push((window as f64).ln());
                logs_rs.push(mean_rs.ln());
            }
        }
        window *= 2;
    }

    if logs_n.len() < 3 {
        return None;
    }
    let slope = ols_slope(&logs_n, &logs_rs)?;
    slope.is_finite().then(|| slope.clamp(0.0, 1.0))
}

/// Rescaled range of one chunk: range of the cumulative deviation series over its
/// standard deviation.
fn rescaled_range(chunk: &[f64]) -> Option<f64> {
    let n = chunk.len();
    if n < 2 {
        return None;
    }
    let mean = chunk.iter().sum::<f64>() / n as f64;

    let mut cum = 0.0;
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    for v in chunk {
        cum += v - mean;
        min = min.min(cum);
        max = max.max(cum);
    }
    let range = max - min;

    let var = chunk.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n as f64;
    let sd = var.sqrt();
    if sd <= f64::EPSILON || !range.is_finite() {
        return None;
    }
    Some(range / sd)
}

/// Ordinary least squares slope of y on x.
fn ols_slope(x: &[f64], y: &[f64]) -> Option<f64> {
    let n = x.len();
    if n < 2 || n != y.len() {
        return None;
    }
    let nf = n as f64;
    let mx = x.iter().sum::<f64>() / nf;
    let my = y.iter().sum::<f64>() / nf;

    let mut num = 0.0;
    let mut den = 0.0;
    for (xi, yi) in x.iter().zip(y.iter()) {
        num += (xi - mx) * (yi - my);
        den += (xi - mx).powi(2);
    }
    (den > f64::EPSILON).then(|| num / den)
}

/// Sample variance with Bessel's correction.
pub fn sample_variance(values: &[f64]) -> Option<f64> {
    let n = values.len();
    if n < 2 {
        return None;
    }
    let mean = values.iter().sum::<f64>() / n as f64;
    let ss: f64 = values.iter().map(|v| (v - mean).powi(2)).sum();
    let var = ss / (n as f64 - 1.0);
    var.is_finite().then_some(var)
}

/// Median of a slice. Does not mutate the input.
pub fn median(values: &[f64]) -> Option<f64> {
    let mut v: Vec<f64> = values.iter().copied().filter(|x| x.is_finite()).collect();
    if v.is_empty() {
        return None;
    }
    v.sort_by(f64::total_cmp);
    let mid = v.len() / 2;
    if v.len() % 2 == 1 {
        v.get(mid).copied()
    } else {
        match (v.get(mid - 1), v.get(mid)) {
            (Some(a), Some(b)) => Some((a + b) / 2.0),
            _ => None,
        }
    }
}

/// Median absolute deviation, scaled to be a consistent estimator of σ for normal data.
pub fn mad(values: &[f64]) -> Option<f64> {
    let med = median(values)?;
    let deviations: Vec<f64> = values
        .iter()
        .filter(|v| v.is_finite())
        .map(|v| (v - med).abs())
        .collect();
    // 1.4826 makes MAD comparable to the standard deviation under normality.
    median(&deviations).map(|m| m * 1.4826)
}

/// Robust z-score using median and MAD instead of mean and σ.
///
/// Crypto returns are fat-tailed: one 8σ candle contaminates a mean/σ normalisation for
/// the entire lookback window, which silently rescales every factor derived from it. The
/// median/MAD version has a 50% breakdown point.
///
/// Falls back to `None` rather than dividing by a zero MAD (a window where more than half
/// the observations are identical).
pub fn robust_zscore(sample: &[f64], value: f64) -> Option<f64> {
    if !value.is_finite() {
        return None;
    }
    let med = median(sample)?;
    let scale = mad(sample)?;
    (scale > f64::EPSILON).then(|| (value - med) / scale)
}

/// Two-sided p-value for a standard normal z, via the Abramowitz-Stegun 7.1.26
/// approximation to erf (absolute error < 1.5e-7 — far below what matters here).
pub fn two_sided_p(z: f64) -> f64 {
    if !z.is_finite() {
        return 1.0;
    }
    let x = z.abs() / std::f64::consts::SQRT_2;

    let t = 1.0 / (1.0 + 0.3275911 * x);
    let poly = t
        * (0.254829592
            + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
    let erf = 1.0 - poly * (-x * x).exp();

    (1.0 - erf).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    /// Deterministic uniform sequence — no RNG, identical on every machine.
    fn lcg(n: usize, seed: u64) -> Vec<f64> {
        let mut x = seed;
        (0..n)
            .map(|_| {
                x = (1103515245u64.wrapping_mul(x).wrapping_add(12345)) % (1 << 31);
                x as f64 / (1u64 << 31) as f64
            })
            .collect()
    }

    /// Approximately-normal deviates by summing uniforms (CLT), mean 0 sd ~1.
    fn normalish(n: usize, seed: u64) -> Vec<f64> {
        let u = lcg(n * 12, seed);
        (0..n)
            .map(|i| u.iter().skip(i * 12).take(12).sum::<f64>() - 6.0)
            .collect()
    }

    fn bars_from(closes: &[f64], intrabar: f64) -> Vec<Ohlc> {
        closes
            .iter()
            .map(|c| Ohlc {
                open: *c,
                high: c * (1.0 + intrabar),
                low: c * (1.0 - intrabar),
                close: *c,
            })
            .collect()
    }

    // ---- Yang-Zhang --------------------------------------------------------

    #[test]
    fn yang_zhang_rejects_degenerate_input() {
        assert!(yang_zhang(&[]).is_none());
        assert!(
            yang_zhang(&bars_from(&[100.0, 101.0], 0.01)).is_none(),
            "2 bars is not enough"
        );
        let bad = vec![
            Ohlc {
                open: 0.0,
                high: 1.0,
                low: 1.0,
                close: 1.0
            };
            10
        ];
        assert!(yang_zhang(&bad).is_none(), "non-positive price accepted");
    }

    #[test]
    fn yang_zhang_is_zero_for_a_perfectly_still_market() {
        let bars = vec![
            Ohlc {
                open: 100.0,
                high: 100.0,
                low: 100.0,
                close: 100.0
            };
            30
        ];
        let yz = yang_zhang(&bars).expect("valid");
        assert!(
            yz.sigma() < 1e-12,
            "still market had volatility {}",
            yz.sigma()
        );
    }

    #[test]
    fn yang_zhang_rises_with_actual_volatility() {
        let calm = yang_zhang(&bars_from(&vec![100.0; 60], 0.001)).expect("calm");
        let wild = yang_zhang(&bars_from(&vec![100.0; 60], 0.05)).expect("wild");
        assert!(
            wild.sigma() > calm.sigma(),
            "calm {} wild {}",
            calm.sigma(),
            wild.sigma()
        );
    }

    #[test]
    fn yang_zhang_captures_gaps_that_a_range_estimator_would_miss() {
        // Bars with a tiny intrabar range but large jumps between them. An estimator
        // built only on high-low would call this nearly still; the overnight term must
        // not.
        let closes: Vec<f64> = (0..60)
            .map(|i| 100.0 * if i % 2 == 0 { 1.0 } else { 1.05 })
            .collect();
        let yz = yang_zhang(&bars_from(&closes, 0.0001)).expect("valid");
        assert!(
            yz.overnight > yz.rogers_satchell,
            "gap risk not captured: overnight {} rs {}",
            yz.overnight,
            yz.rogers_satchell
        );
    }

    #[test]
    fn rogers_satchell_is_drift_independent() {
        // Two bars with the same true range, one trending hard up, one flat-ish. RS is
        // designed so a strong intrabar drift does not inflate the estimate.
        let trending = Ohlc {
            open: 100.0,
            high: 110.0,
            low: 100.0,
            close: 110.0,
        };
        let rs = rogers_satchell_bar(&trending).expect("valid");
        assert!(rs.abs() < 1e-9, "drift leaked into Rogers-Satchell: {rs}");
    }

    #[test]
    fn annualization_scales_by_root_time() {
        let yz = yang_zhang(&bars_from(&vec![100.0; 60], 0.01)).expect("valid");
        let a = yz.annualized(365.0);
        assert!((a - yz.sigma() * 365.0_f64.sqrt()).abs() < 1e-12);
    }

    // ---- variance ratio ----------------------------------------------------

    #[test]
    fn variance_ratio_rejects_too_little_data() {
        assert!(variance_ratio(&[0.01; 5], 4).is_none());
        assert!(variance_ratio(&[0.01; 100], 1).is_none(), "q must be >= 2");
    }

    #[test]
    fn variance_ratio_of_a_random_walk_is_near_one() {
        let r = normalish(2000, 42);
        let vr = variance_ratio(&r, 4).expect("valid");
        assert!(
            (vr.ratio - 1.0).abs() < 0.15,
            "random walk gave VR {} (z {})",
            vr.ratio,
            vr.z_statistic
        );
    }

    #[test]
    fn variance_ratio_detects_momentum() {
        // Positively autocorrelated series: r_t = 0.5 r_{t-1} + noise. Trending, so
        // q-period variance must exceed q times the 1-period variance.
        let noise = normalish(3000, 7);
        let mut r = Vec::with_capacity(noise.len());
        let mut prev = 0.0;
        for e in &noise {
            let cur = 0.5 * prev + e;
            r.push(cur);
            prev = cur;
        }
        let vr = variance_ratio(&r, 4).expect("valid");
        assert!(vr.ratio > 1.2, "momentum series gave VR {}", vr.ratio);
        assert!(vr.rejects_random_walk(0.05), "p {}", vr.p_value);
        assert!(vr.signal(0.05) > 0.0);
    }

    #[test]
    fn variance_ratio_detects_mean_reversion() {
        // Negatively autocorrelated: r_t = -0.5 r_{t-1} + noise.
        let noise = normalish(3000, 99);
        let mut r = Vec::with_capacity(noise.len());
        let mut prev = 0.0;
        for e in &noise {
            let cur = -0.5 * prev + e;
            r.push(cur);
            prev = cur;
        }
        let vr = variance_ratio(&r, 4).expect("valid");
        assert!(vr.ratio < 0.8, "mean-reverting series gave VR {}", vr.ratio);
        assert!(vr.signal(0.05) < 0.0);
    }

    #[test]
    fn an_unrejected_null_produces_no_signal() {
        // The point of using a test rather than a threshold: when the data does not
        // distinguish itself from a random walk, the signal is exactly zero.
        let vr = VarianceRatio {
            ratio: 1.4,
            z_statistic: 0.3,
            p_value: 0.76,
            q: 4,
        };
        assert_eq!(vr.signal(0.05), 0.0);
    }

    // ---- Hurst -------------------------------------------------------------

    #[test]
    fn hurst_of_a_random_walk_is_near_one_half() {
        let h = hurst_exponent(&normalish(4096, 11), 16).expect("valid");
        assert!((h - 0.5).abs() < 0.15, "random walk Hurst {h}");
    }

    #[test]
    fn hurst_rises_for_a_persistent_series() {
        let noise = normalish(4096, 5);
        let mut r = Vec::with_capacity(noise.len());
        let mut prev = 0.0;
        for e in &noise {
            let cur = 0.7 * prev + e;
            r.push(cur);
            prev = cur;
        }
        let persistent = hurst_exponent(&r, 16).expect("valid");
        let random = hurst_exponent(&normalish(4096, 11), 16).expect("valid");
        assert!(
            persistent > random,
            "persistent {persistent} not above random {random}"
        );
    }

    #[test]
    fn hurst_needs_enough_data_and_window_sizes() {
        assert!(
            hurst_exponent(&normalish(100, 1), 4).is_none(),
            "min_window too small"
        );
        assert!(
            hurst_exponent(&normalish(20, 1), 16).is_none(),
            "series too short"
        );
    }

    // ---- robust statistics -------------------------------------------------

    #[test]
    fn median_handles_both_parities() {
        assert_eq!(median(&[3.0, 1.0, 2.0]), Some(2.0));
        assert_eq!(median(&[4.0, 1.0, 3.0, 2.0]), Some(2.5));
        assert_eq!(median(&[]), None);
    }

    #[test]
    fn robust_zscore_survives_an_outlier_that_breaks_the_mean() {
        // A single extreme observation. Mean/σ normalisation would be dragged so far
        // that a genuinely typical value looks unremarkable.
        let mut sample: Vec<f64> = (0..99).map(|i| i as f64 / 99.0).collect();
        sample.push(10_000.0);

        let robust = robust_zscore(&sample, 0.9).expect("valid");

        let n = sample.len() as f64;
        let mean = sample.iter().sum::<f64>() / n;
        let sd = (sample.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n).sqrt();
        let naive = (0.9 - mean) / sd;

        assert!(
            robust.abs() > naive.abs() * 10.0,
            "robust {robust} was not meaningfully more sensitive than naive {naive}"
        );
    }

    #[test]
    fn robust_zscore_refuses_a_degenerate_scale() {
        // More than half the window identical: MAD is zero and the z-score is undefined.
        // Returning a large finite number here would be worse than returning nothing.
        let sample = vec![5.0; 100];
        assert_eq!(robust_zscore(&sample, 9.0), None);
    }

    #[test]
    fn mad_is_scaled_to_match_sigma_under_normality() {
        let sample = normalish(20_000, 3);
        let m = mad(&sample).expect("valid");
        let var = sample_variance(&sample).expect("valid");
        // Should land close to the true σ ≈ 1 for these deviates.
        assert!((m - var.sqrt()).abs() < 0.1, "mad {m} vs sd {}", var.sqrt());
    }

    // ---- p-values ----------------------------------------------------------

    #[test]
    fn two_sided_p_matches_known_normal_quantiles() {
        assert!((two_sided_p(0.0) - 1.0).abs() < 1e-6);
        assert!(
            (two_sided_p(1.959964) - 0.05).abs() < 1e-4,
            "got {}",
            two_sided_p(1.959964)
        );
        assert!(
            (two_sided_p(2.575829) - 0.01).abs() < 1e-4,
            "got {}",
            two_sided_p(2.575829)
        );
        assert!(
            (two_sided_p(-1.959964) - 0.05).abs() < 1e-4,
            "must be symmetric"
        );
    }

    #[test]
    fn two_sided_p_is_defined_for_non_finite_input() {
        assert_eq!(two_sided_p(f64::NAN), 1.0);
        assert_eq!(two_sided_p(f64::INFINITY), 1.0);
    }
}
