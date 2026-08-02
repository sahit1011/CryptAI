//! Market structure detection — swings, breaks, fair value gaps, order blocks, and
//! resting liquidity.
//!
//! This is "confluence" in the sense a discretionary trader means it: independent
//! features of the chart that happen to line up at the same price. It is deliberately
//! separate from the statistical layer in [`crate::quant`], because the two fail in
//! different ways — structure is precise but subjective, statistics are objective but
//! blunt, and a level both agree on is worth more than either alone.
//!
//! Everything here is **shared-plane data**: a fair value gap is a fair value gap
//! regardless of who is looking at it. It describes geometry, never a trade.
//!
//! # On the subjectivity
//!
//! Every one of these patterns has a dozen published definitions and no authority to
//! settle between them. The ones implemented here are the common formulations, stated
//! explicitly in each doc comment so a disagreement is about a documented choice rather
//! than a mystery. None of them is validated against forward returns yet — they populate
//! `Structure` for the per-user layer to reason over, and `eval/FINDINGS.md` records that
//! they are unvalidated.

use crate::indicators::Candle;
use crate::pulse::Level;

/// A confirmed swing high or low.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SwingPoint {
    pub index: usize,
    pub price: f64,
    pub ts: i64,
    pub is_high: bool,
}

/// A break of market structure.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StructureBreak {
    /// Price that was taken out.
    pub price: f64,
    pub bullish: bool,
    /// A CHoCH is the first break *against* the prevailing swing sequence — the earliest
    /// structural hint of a reversal. A BOS is a break that continues it. Same geometry,
    /// different meaning, so they are distinguished rather than merged.
    pub is_change_of_character: bool,
}

/// A three-candle imbalance: price moved so fast it left an unfilled gap.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FairValueGap {
    pub low: f64,
    pub high: f64,
    pub bullish: bool,
    pub index: usize,
}

/// The candle whose inventory is presumed to have caused a displacement move.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OrderBlock {
    pub low: f64,
    pub high: f64,
    pub bullish: bool,
    pub index: usize,
}

/// Everything detectable from one timeframe's bars.
#[derive(Debug, Clone, Default)]
pub struct StructureMap {
    pub swings: Vec<SwingPoint>,
    pub last_break: Option<StructureBreak>,
    pub fvgs: Vec<FairValueGap>,
    pub order_blocks: Vec<OrderBlock>,
    pub liquidity_pools: Vec<Level>,
    /// Higher-timeframe bias implied by the swing sequence.
    pub bias: Option<&'static str>,
}

/// Fractal swing detection: a bar is a swing high if its high is the strict maximum of
/// the window `lookback` bars either side.
///
/// Requires `lookback` bars of confirmation on the RIGHT, so the most recent `lookback`
/// bars can never produce a swing. That lag is not a flaw to engineer around — a "swing
/// high" identified without right-side confirmation is just the current bar, and treating
/// it as structure is how repainting indicators are built.
pub fn swing_points(candles: &[Candle], lookback: usize) -> Vec<SwingPoint> {
    if lookback == 0 || candles.len() < lookback * 2 + 1 {
        return Vec::new();
    }

    let mut out = Vec::new();
    for i in lookback..candles.len().saturating_sub(lookback) {
        let Some(pivot) = candles.get(i) else {
            continue;
        };
        let Some(window) = candles.get(i - lookback..=i + lookback) else {
            continue;
        };

        let is_high = window
            .iter()
            .enumerate()
            .all(|(j, c)| j == lookback || c.high < pivot.high);
        let is_low = window
            .iter()
            .enumerate()
            .all(|(j, c)| j == lookback || c.low > pivot.low);

        if is_high {
            out.push(SwingPoint {
                index: i,
                price: pivot.high,
                ts: pivot.close_time,
                is_high: true,
            });
        } else if is_low {
            out.push(SwingPoint {
                index: i,
                price: pivot.low,
                ts: pivot.close_time,
                is_high: false,
            });
        }
    }
    out
}

/// Bias from the swing sequence: higher highs and higher lows is bullish, the mirror is
/// bearish, anything else is neither.
///
/// Returns `None` rather than guessing when the sequence is mixed. A forced call on
/// ambiguous structure is worse than an abstention, because downstream cannot tell the
/// two apart.
pub fn swing_bias(swings: &[SwingPoint]) -> Option<&'static str> {
    let highs: Vec<f64> = swings
        .iter()
        .filter(|s| s.is_high)
        .map(|s| s.price)
        .collect();
    let lows: Vec<f64> = swings
        .iter()
        .filter(|s| !s.is_high)
        .map(|s| s.price)
        .collect();
    if highs.len() < 2 || lows.len() < 2 {
        return None;
    }

    let last_two = |v: &[f64]| -> Option<(f64, f64)> {
        let n = v.len();
        Some((*v.get(n - 2)?, *v.get(n - 1)?))
    };
    let (h_prev, h_last) = last_two(&highs)?;
    let (l_prev, l_last) = last_two(&lows)?;

    if h_last > h_prev && l_last > l_prev {
        Some("bullish")
    } else if h_last < h_prev && l_last < l_prev {
        Some("bearish")
    } else {
        None
    }
}

/// The most recent structure break relative to the latest close.
///
/// A break is a close beyond the last confirmed swing in that direction. Using the close
/// rather than the wick is the conservative choice: a wick through a level is a liquidity
/// sweep at least as often as it is a break, and counting sweeps as breaks is what makes
/// structure-following strategies buy every top.
pub fn detect_break(
    swings: &[SwingPoint],
    last_close: f64,
    bias: Option<&str>,
) -> Option<StructureBreak> {
    let last_high = swings.iter().rev().find(|s| s.is_high)?;
    let last_low = swings.iter().rev().find(|s| !s.is_high)?;

    if last_close > last_high.price {
        return Some(StructureBreak {
            price: last_high.price,
            bullish: true,
            // Breaking up while the sequence was bearish is a change of character.
            is_change_of_character: bias == Some("bearish"),
        });
    }
    if last_close < last_low.price {
        return Some(StructureBreak {
            price: last_low.price,
            bullish: false,
            is_change_of_character: bias == Some("bullish"),
        });
    }
    None
}

/// Three-candle fair value gaps.
///
/// Bullish when `candles[i-1].high < candles[i+1].low` — the middle candle displaced so
/// hard that no trading occurred between those prices. Bearish is the mirror.
///
/// Only gaps that remain UNFILLED by later price action are returned: a gap that price
/// has already traded back through has done its job and is no longer a level.
pub fn fair_value_gaps(candles: &[Candle], max_age: usize) -> Vec<FairValueGap> {
    if candles.len() < 3 {
        return Vec::new();
    }
    let start = candles.len().saturating_sub(max_age);
    let mut out = Vec::new();

    for i in (start + 1)..candles.len().saturating_sub(1) {
        let (Some(prev), Some(next)) = (candles.get(i - 1), candles.get(i + 1)) else {
            continue;
        };

        let gap = if prev.high < next.low {
            Some(FairValueGap {
                low: prev.high,
                high: next.low,
                bullish: true,
                index: i,
            })
        } else if prev.low > next.high {
            Some(FairValueGap {
                low: next.high,
                high: prev.low,
                bullish: false,
                index: i,
            })
        } else {
            None
        };

        let Some(gap) = gap else { continue };

        // Discard if any later candle traded through it.
        let filled = candles
            .get(i + 2..)
            .map(|rest| rest.iter().any(|c| c.low <= gap.high && c.high >= gap.low))
            .unwrap_or(false);
        if !filled {
            out.push(gap);
        }
    }
    out
}

/// Order blocks: the last opposing candle before a displacement move.
///
/// A bullish order block is the last down-close candle before a run that takes out the
/// prior swing high. `displacement_atr` scales the move that counts as displacement, so a
/// quiet market and a volatile one are not held to the same absolute threshold.
pub fn order_blocks(
    candles: &[Candle],
    atr: f64,
    displacement_atr: f64,
    max_age: usize,
) -> Vec<OrderBlock> {
    if candles.len() < 4 || atr <= 0.0 {
        return Vec::new();
    }
    let threshold = atr * displacement_atr;
    let start = candles.len().saturating_sub(max_age);
    let mut out = Vec::new();

    for i in start..candles.len().saturating_sub(2) {
        let (Some(base), Some(next)) = (candles.get(i), candles.get(i + 1)) else {
            continue;
        };
        let move_size = next.close - next.open;

        // Bullish: a down candle followed by an up-displacement.
        if base.close < base.open && move_size > threshold {
            out.push(OrderBlock {
                low: base.low,
                high: base.high,
                bullish: true,
                index: i,
            });
        }
        // Bearish: an up candle followed by a down-displacement.
        if base.close > base.open && -move_size > threshold {
            out.push(OrderBlock {
                low: base.low,
                high: base.high,
                bullish: false,
                index: i,
            });
        }
    }
    out
}

/// Resting liquidity: clusters of swing points at effectively the same price.
///
/// Equal highs and equal lows are where stop orders accumulate, which is precisely why
/// price tends to be drawn there. `tolerance_pct` decides how close counts as equal.
pub fn liquidity_pools(swings: &[SwingPoint], tolerance_pct: f64) -> Vec<Level> {
    if swings.len() < 2 || tolerance_pct <= 0.0 {
        return Vec::new();
    }
    let mut pools = Vec::new();

    for (kind, wanted_high) in [("high", true), ("low", false)] {
        let mut prices: Vec<f64> = swings
            .iter()
            .filter(|s| s.is_high == wanted_high)
            .map(|s| s.price)
            .collect();
        prices.sort_by(f64::total_cmp);

        let mut cluster: Vec<f64> = Vec::new();
        for price in prices {
            let extend = cluster
                .first()
                .map(|anchor| ((price - anchor) / anchor).abs() * 100.0 <= tolerance_pct)
                .unwrap_or(true);
            if extend {
                cluster.push(price);
            } else {
                push_pool(&mut pools, &cluster, kind);
                cluster = vec![price];
            }
        }
        push_pool(&mut pools, &cluster, kind);
    }
    pools
}

fn push_pool(pools: &mut Vec<Level>, cluster: &[f64], kind: &str) {
    // A single swing is a level, not a pool. Two or more at the same price is what makes
    // it liquidity worth hunting.
    if cluster.len() < 2 {
        return;
    }
    let lo = cluster.iter().copied().fold(f64::INFINITY, f64::min);
    let hi = cluster.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if lo.is_finite() && hi.is_finite() {
        pools.push(Level {
            low: lo,
            high: hi,
            timeframe: Some(kind.to_string()),
        });
    }
}

/// Full structure map for one timeframe.
pub fn analyze(candles: &[Candle], atr: f64, lookback: usize) -> StructureMap {
    let swings = swing_points(candles, lookback);
    let bias = swing_bias(&swings);
    let last_close = candles.last().map(|c| c.close).unwrap_or(0.0);

    StructureMap {
        last_break: detect_break(&swings, last_close, bias),
        fvgs: fair_value_gaps(candles, 200),
        order_blocks: order_blocks(candles, atr, 1.5, 200),
        liquidity_pools: liquidity_pools(&swings, 0.15),
        bias,
        swings,
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn c(open: f64, high: f64, low: f64, close: f64, i: i64) -> Candle {
        Candle {
            open,
            high,
            low,
            close,
            volume: 1.0,
            close_time: i * 60_000,
        }
    }

    fn flat(n: usize, price: f64) -> Vec<Candle> {
        (0..n)
            .map(|i| c(price, price + 0.5, price - 0.5, price, i as i64))
            .collect()
    }

    // ---- swings ------------------------------------------------------------

    #[test]
    fn finds_an_obvious_swing_high() {
        let mut bars = flat(11, 100.0);
        bars[5] = c(100.0, 120.0, 99.0, 110.0, 5);
        let swings = swing_points(&bars, 3);
        let high = swings.iter().find(|s| s.is_high).expect("swing high");
        assert_eq!(high.index, 5);
        assert_eq!(high.price, 120.0);
    }

    #[test]
    fn the_most_recent_bars_can_never_be_swings() {
        // A swing needs right-side confirmation. Detecting one on the last bar is how
        // repainting indicators are built.
        let mut bars = flat(11, 100.0);
        let last = bars.len() - 1;
        bars[last] = c(100.0, 500.0, 99.0, 400.0, last as i64);
        let swings = swing_points(&bars, 3);
        assert!(
            swings.iter().all(|s| s.index <= last - 3),
            "a swing was reported without right-side confirmation"
        );
    }

    #[test]
    fn insufficient_bars_yield_no_swings() {
        assert!(swing_points(&flat(4, 100.0), 3).is_empty());
        assert!(swing_points(&flat(100, 100.0), 0).is_empty());
    }

    #[test]
    fn a_flat_market_has_no_swings() {
        // Every bar identical: nothing is a strict extremum, so nothing is a swing.
        assert!(swing_points(&flat(50, 100.0), 3).is_empty());
    }

    // ---- bias --------------------------------------------------------------

    #[test]
    fn higher_highs_and_higher_lows_is_bullish() {
        let swings = vec![
            SwingPoint {
                index: 0,
                price: 90.0,
                ts: 0,
                is_high: false,
            },
            SwingPoint {
                index: 1,
                price: 100.0,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 95.0,
                ts: 2,
                is_high: false,
            },
            SwingPoint {
                index: 3,
                price: 110.0,
                ts: 3,
                is_high: true,
            },
        ];
        assert_eq!(swing_bias(&swings), Some("bullish"));
    }

    #[test]
    fn mixed_structure_abstains_rather_than_guessing() {
        // Higher high but lower low — genuinely ambiguous. A forced call here is worse
        // than none, because downstream cannot distinguish the two.
        let swings = vec![
            SwingPoint {
                index: 0,
                price: 90.0,
                ts: 0,
                is_high: false,
            },
            SwingPoint {
                index: 1,
                price: 100.0,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 85.0,
                ts: 2,
                is_high: false,
            },
            SwingPoint {
                index: 3,
                price: 110.0,
                ts: 3,
                is_high: true,
            },
        ];
        assert_eq!(swing_bias(&swings), None);
    }

    // ---- breaks ------------------------------------------------------------

    #[test]
    fn a_close_beyond_the_last_swing_high_is_a_bullish_break() {
        let swings = vec![
            SwingPoint {
                index: 1,
                price: 100.0,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 90.0,
                ts: 2,
                is_high: false,
            },
        ];
        let b = detect_break(&swings, 105.0, Some("bullish")).expect("break");
        assert!(b.bullish);
        assert!(
            !b.is_change_of_character,
            "continuation misreported as CHoCH"
        );
    }

    #[test]
    fn breaking_against_the_prevailing_bias_is_a_change_of_character() {
        let swings = vec![
            SwingPoint {
                index: 1,
                price: 100.0,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 90.0,
                ts: 2,
                is_high: false,
            },
        ];
        let b = detect_break(&swings, 105.0, Some("bearish")).expect("break");
        assert!(b.is_change_of_character);
    }

    #[test]
    fn price_inside_the_range_is_not_a_break() {
        let swings = vec![
            SwingPoint {
                index: 1,
                price: 100.0,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 90.0,
                ts: 2,
                is_high: false,
            },
        ];
        assert_eq!(detect_break(&swings, 95.0, None), None);
    }

    // ---- fair value gaps ---------------------------------------------------

    #[test]
    fn detects_an_unfilled_bullish_gap() {
        // Bar 0 high 100, bar 2 low 110 -> a 10-wide unfilled gap.
        let bars = vec![
            c(99.0, 100.0, 98.0, 99.5, 0),
            c(100.0, 115.0, 100.0, 114.0, 1),
            c(114.0, 118.0, 110.0, 117.0, 2),
            c(117.0, 120.0, 116.0, 119.0, 3),
        ];
        let gaps = fair_value_gaps(&bars, 100);
        let g = gaps.first().expect("one gap");
        assert!(g.bullish);
        assert_eq!((g.low, g.high), (100.0, 110.0));
    }

    #[test]
    fn a_gap_price_has_traded_back_through_is_discarded() {
        // Same gap, but a later bar dips into it. It has done its job.
        let bars = vec![
            c(99.0, 100.0, 98.0, 99.5, 0),
            c(100.0, 115.0, 100.0, 114.0, 1),
            c(114.0, 118.0, 110.0, 117.0, 2),
            c(117.0, 118.0, 104.0, 106.0, 3), // trades back into 100..110
        ];
        assert!(
            fair_value_gaps(&bars, 100).is_empty(),
            "filled gap was reported"
        );
    }

    #[test]
    fn a_continuous_market_has_no_gaps() {
        assert!(fair_value_gaps(&flat(50, 100.0), 100).is_empty());
    }

    // ---- order blocks ------------------------------------------------------

    #[test]
    fn a_down_candle_before_an_up_displacement_is_a_bullish_order_block() {
        let bars = vec![
            c(100.0, 101.0, 98.0, 99.0, 0), // down candle
            c(99.0, 112.0, 99.0, 111.0, 1), // +12 displacement
            c(111.0, 113.0, 110.0, 112.0, 2),
            c(112.0, 114.0, 111.0, 113.0, 3),
        ];
        let obs = order_blocks(&bars, 2.0, 1.5, 100);
        let ob = obs.first().expect("one order block");
        assert!(ob.bullish);
        assert_eq!((ob.low, ob.high), (98.0, 101.0));
    }

    #[test]
    fn a_move_below_the_displacement_threshold_is_not_an_order_block() {
        let bars = vec![
            c(100.0, 101.0, 98.0, 99.0, 0),
            c(99.0, 100.0, 99.0, 99.5, 1), // tiny move
            c(99.5, 100.0, 99.0, 99.6, 2),
            c(99.6, 100.0, 99.0, 99.7, 3),
        ];
        assert!(order_blocks(&bars, 2.0, 1.5, 100).is_empty());
    }

    #[test]
    fn order_blocks_scale_with_volatility_not_absolute_price() {
        // The same +12 move is displacement in a calm market and noise in a wild one.
        let bars = vec![
            c(100.0, 101.0, 98.0, 99.0, 0),
            c(99.0, 112.0, 99.0, 111.0, 1),
            c(111.0, 113.0, 110.0, 112.0, 2),
            c(112.0, 114.0, 111.0, 113.0, 3),
        ];
        assert_eq!(order_blocks(&bars, 2.0, 1.5, 100).len(), 1, "calm market");
        assert!(
            order_blocks(&bars, 40.0, 1.5, 100).is_empty(),
            "wild market"
        );
    }

    #[test]
    fn a_zero_atr_yields_nothing_rather_than_everything() {
        // Dividing the world by a zero threshold would make every candle an order block.
        let bars = flat(20, 100.0);
        assert!(order_blocks(&bars, 0.0, 1.5, 100).is_empty());
    }

    // ---- liquidity pools ---------------------------------------------------

    #[test]
    fn equal_highs_cluster_into_one_pool() {
        let swings = vec![
            SwingPoint {
                index: 0,
                price: 100.00,
                ts: 0,
                is_high: true,
            },
            SwingPoint {
                index: 1,
                price: 100.05,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 100.02,
                ts: 2,
                is_high: true,
            },
        ];
        let pools = liquidity_pools(&swings, 0.15);
        assert_eq!(pools.len(), 1, "equal highs did not cluster: {pools:?}");
        assert!(pools[0].low <= 100.0 && pools[0].high >= 100.05);
    }

    #[test]
    fn a_lone_swing_is_a_level_not_a_pool() {
        let swings = vec![SwingPoint {
            index: 0,
            price: 100.0,
            ts: 0,
            is_high: true,
        }];
        assert!(liquidity_pools(&swings, 0.15).is_empty());
    }

    #[test]
    fn distant_swings_do_not_cluster() {
        let swings = vec![
            SwingPoint {
                index: 0,
                price: 100.0,
                ts: 0,
                is_high: true,
            },
            SwingPoint {
                index: 1,
                price: 150.0,
                ts: 1,
                is_high: true,
            },
        ];
        assert!(liquidity_pools(&swings, 0.15).is_empty());
    }

    #[test]
    fn highs_and_lows_form_separate_pools() {
        let swings = vec![
            SwingPoint {
                index: 0,
                price: 100.0,
                ts: 0,
                is_high: true,
            },
            SwingPoint {
                index: 1,
                price: 100.05,
                ts: 1,
                is_high: true,
            },
            SwingPoint {
                index: 2,
                price: 90.0,
                ts: 2,
                is_high: false,
            },
            SwingPoint {
                index: 3,
                price: 90.02,
                ts: 3,
                is_high: false,
            },
        ];
        let pools = liquidity_pools(&swings, 0.15);
        assert_eq!(pools.len(), 2);
    }

    // ---- integration -------------------------------------------------------

    #[test]
    fn analyze_never_panics_on_degenerate_input() {
        for bars in [vec![], flat(1, 100.0), flat(3, 100.0), flat(500, 100.0)] {
            let _ = analyze(&bars, 1.0, 3);
            let _ = analyze(&bars, 0.0, 3);
        }
    }

    #[test]
    fn analyze_populates_structure_on_a_realistic_series() {
        // A drifting SINE, not a ramp or a piecewise zigzag. A ramp has no strict
        // interior extremum (correctly yielding no swings), and in a piecewise zigzag the
        // turn bar's open equals the peak bar's close, so their highs TIE and the strict
        // inequality fails. A smooth oscillation gives genuinely distinct extrema.
        // The high/low are derived from the bar's OWN close, not from max(open, close).
        // With open = previous close, the bar after a peak opens exactly at the peak, so
        // its high would tie with the peak bar's and the strict inequality would fail.
        let mut bars = Vec::new();
        let mut prev = 100.0;
        for i in 0..160 {
            let t = i as f64;
            // Period 20 bars, amplitude 10, upward drift of 0.05/bar.
            let price = 100.0 + t * 0.05 + 10.0 * (t * std::f64::consts::TAU / 20.0).sin();
            bars.push(c(prev, price + 0.5, price - 0.5, price, i));
            prev = price;
        }

        let map = analyze(&bars, 1.0, 3);
        assert!(!map.swings.is_empty(), "no swings on a zigzag");
        assert!(
            map.swings.iter().any(|s| s.is_high) && map.swings.iter().any(|s| !s.is_high),
            "expected both highs and lows"
        );
        // Net +3.5 per 13-bar cycle, so the sequence makes higher highs and higher lows.
        assert_eq!(map.bias, Some("bullish"));
    }
}
