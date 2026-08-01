//! Walk-forward signal generation over historical bars.
//!
//! Emits one pulse per bar, computed from **only the bars at or before that point**.
//! Forward returns are joined on the Python side from bars strictly after it. That
//! separation is the entire guard against look-ahead bias, which is the single most
//! common way a backtest reports a signal that does not exist.
//!
//! This drives the real scorer. Backtesting a reimplementation would prove nothing about
//! the engine that actually ships.
//!
//! ```text
//! cargo run --release --bin backtest < bars.json > pulses.json
//! ```
//!
//! Klines carry no funding, open-interest, spread, or depth history, so those inputs are
//! held at neutral values unless supplied per-bar. Their factors then contribute a
//! constant offset and all *variation* in the score comes from the price-derived
//! factors plus the session clock. The Python report states this explicitly rather than
//! letting it look like a full-system result.

#![allow(clippy::print_stdout)]

use std::io::Read;

use serde::{Deserialize, Serialize};
use signal_engine::indicators::Candle;
use signal_engine::quant::{hurst_exponent, variance_ratio, yang_zhang, Ohlc};
use signal_engine::scoring::{score, MarketSnapshot, ScoringConfig, TimeframeData};

#[derive(Debug, Deserialize)]
struct Bar {
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    #[serde(default)]
    volume: f64,
    close_time: i64,
}

#[derive(Debug, Deserialize)]
struct Input {
    symbol: String,
    bars: Vec<Bar>,
    /// Bars of history required before the first pulse is emitted.
    #[serde(default = "default_warmup")]
    warmup: usize,
    /// How many base bars aggregate into the higher timeframe.
    #[serde(default = "default_htf_factor")]
    htf_factor: usize,
    #[serde(default)]
    spread_bps: Option<f64>,
    #[serde(default)]
    depth_usd: Option<f64>,
    #[serde(default)]
    funding_rate: Option<f64>,
}

fn default_warmup() -> usize {
    300
}
fn default_htf_factor() -> usize {
    4
}

#[derive(Debug, Serialize)]
struct Row {
    ts: i64,
    price: f64,
    tradability: u8,
    regime: String,
    vetoed: bool,
    trend_alignment: f64,
    volatility_band: f64,
    efficiency_ratio: f64,
    liquidity_window: f64,
    atr_pct: f64,
    atr_percentile: f64,
    /// Yang-Zhang σ per bar over the trailing window.
    yz_sigma: Option<f64>,
    /// Lo-MacKinlay variance ratio and its robust p-value.
    vr_ratio: Option<f64>,
    vr_p_value: Option<f64>,
    hurst: Option<f64>,
}

fn to_candle(b: &Bar) -> Candle {
    Candle {
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
        close_time: b.close_time,
    }
}

/// Aggregate base bars into higher-timeframe bars. Only COMPLETE groups are produced —
/// a partial trailing group would leak information about a bar that has not closed.
fn aggregate(candles: &[Candle], factor: usize) -> Vec<Candle> {
    if factor <= 1 {
        return candles.to_vec();
    }
    candles
        .chunks_exact(factor)
        .filter_map(|chunk| {
            let first = chunk.first()?;
            let last = chunk.last()?;
            Some(Candle {
                open: first.open,
                high: chunk
                    .iter()
                    .map(|c| c.high)
                    .fold(f64::NEG_INFINITY, f64::max),
                low: chunk.iter().map(|c| c.low).fold(f64::INFINITY, f64::min),
                close: last.close,
                volume: chunk.iter().map(|c| c.volume).sum(),
                close_time: last.close_time,
            })
        })
        .collect()
}

fn main() {
    let mut raw = String::new();
    if std::io::stdin().read_to_string(&mut raw).is_err() {
        eprintln!("failed to read input");
        std::process::exit(2);
    }
    let input: Input = match serde_json::from_str(&raw) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("bad input: {e}");
            std::process::exit(2);
        }
    };

    let candles: Vec<Candle> = input.bars.iter().map(to_candle).collect();
    let cfg = ScoringConfig::default();

    // Neutral defaults: no veto, mid-quality book. Stated in the report.
    let spread_bps = input.spread_bps.unwrap_or(1.0);
    let depth_usd = input.depth_usd.unwrap_or(cfg.target_depth_usd);
    let funding_rate = input.funding_rate.unwrap_or(0.0);

    let mut rows = Vec::new();

    for i in input.warmup..candles.len() {
        // STRICTLY causal: everything up to and including bar i, nothing after.
        let Some(history) = candles.get(..=i) else {
            continue;
        };
        let Some(current) = candles.get(i) else {
            continue;
        };

        let htf = aggregate(history, input.htf_factor);

        let snapshot = MarketSnapshot {
            symbol: input.symbol.clone(),
            now_ms: current.close_time,
            feed_ts: current.close_time,
            timeframes: vec![
                TimeframeData {
                    label: "base",
                    weight: 1.0,
                    candles: history.to_vec(),
                },
                TimeframeData {
                    label: "htf",
                    weight: 2.0,
                    candles: htf,
                },
            ],
            funding_rate,
            oi_delta_1h: 0.0,
            spread_bps,
            depth_usd,
            btc_closes: Vec::new(),
        };

        let scored = score(&snapshot, &cfg);
        let p = &scored.pulse;

        // Trailing window for the heavier estimators — recomputing these over the full
        // history at every bar would be quadratic for no analytical gain.
        let window_start = i.saturating_sub(400);
        let window = history.get(window_start..).unwrap_or(history);

        let ohlc: Vec<Ohlc> = window
            .iter()
            .map(|c| Ohlc {
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
            })
            .collect();
        let yz = yang_zhang(&ohlc).map(|v| v.sigma());

        let rets: Vec<f64> = window
            .windows(2)
            .filter_map(|w| {
                let prev = w.first()?.close;
                let cur = w.get(1)?.close;
                (prev > 0.0).then(|| (cur / prev).ln())
            })
            .collect();

        let vr = variance_ratio(&rets, 4);
        let hurst = hurst_exponent(&rets, 16);

        rows.push(Row {
            ts: current.close_time,
            price: current.close,
            tradability: p.tradability,
            regime: format!("{:?}", p.regime),
            vetoed: !p.vetoes.is_empty(),
            trend_alignment: p.factors.trend_alignment,
            volatility_band: p.factors.volatility_band,
            efficiency_ratio: p.factors.efficiency_ratio,
            liquidity_window: p.factors.liquidity_window,
            atr_pct: p.context.atr_pct,
            atr_percentile: p.context.atr_percentile_30d,
            yz_sigma: yz,
            vr_ratio: vr.map(|v| v.ratio),
            vr_p_value: vr.map(|v| v.p_value),
            hurst,
        });
    }

    match serde_json::to_string(&rows) {
        Ok(j) => println!("{j}"),
        Err(e) => {
            eprintln!("serialise failed: {e}");
            std::process::exit(2);
        }
    }
}
