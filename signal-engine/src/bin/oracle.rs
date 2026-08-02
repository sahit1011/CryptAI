//! Differential-test harness: computes indicators from a fixture and prints JSON.
//!
//! This exists to answer the question the Rust decision raises — *is the port correct?*
//! A Python/numpy reference implementation computes the same values from the same
//! fixtures, and `tests/test_pulse_differential.py` asserts the two agree. Rust is the
//! implementation; Python is the oracle. Neither is trusted alone.
//!
//! Reads a fixture JSON on stdin, writes results on stdout:
//!
//! ```text
//! cargo run --bin oracle < fixtures/trend_up.json
//! ```
//!
//! Deliberately dependency-free beyond serde so it builds in seconds in CI.

#![allow(clippy::print_stdout)]

use std::io::Read;

use serde::{Deserialize, Serialize};
use signal_engine::indicators::{
    atr, correlation, efficiency_ratio, ema, percentile_rank, returns, sma, Candle,
};

#[derive(Debug, Deserialize)]
struct Bar {
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    #[serde(default)]
    volume: f64,
    #[serde(default)]
    close_time: i64,
}

#[derive(Debug, Deserialize)]
struct Fixture {
    name: String,
    bars: Vec<Bar>,
    ema_period: usize,
    atr_period: usize,
    er_period: usize,
    /// Second series for the correlation check, e.g. BTC closes.
    #[serde(default)]
    reference_closes: Vec<f64>,
}

#[derive(Debug, Serialize)]
struct Output {
    name: String,
    bar_count: usize,
    sma: Option<f64>,
    ema: Option<f64>,
    atr: Option<f64>,
    efficiency_ratio: Option<f64>,
    percentile_of_last_close: Option<f64>,
    correlation_with_reference: Option<f64>,
    returns_count: usize,
    returns_sum: f64,
}

fn main() {
    let mut raw = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut raw) {
        eprintln!("failed to read fixture from stdin: {e}");
        std::process::exit(2);
    }

    let fixture: Fixture = match serde_json::from_str(&raw) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("fixture is not valid JSON: {e}");
            std::process::exit(2);
        }
    };

    let candles: Vec<Candle> = fixture
        .bars
        .iter()
        .map(|b| Candle {
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
            volume: b.volume,
            close_time: b.close_time,
        })
        .collect();

    let closes: Vec<f64> = candles.iter().map(|c| c.close).collect();
    let last_close = closes.last().copied();

    let sym_returns = returns(&closes);
    let ref_returns = returns(&fixture.reference_closes);
    let n = sym_returns.len().min(ref_returns.len());
    let corr = if n >= 2 {
        let a: Vec<f64> = sym_returns.iter().rev().take(n).copied().collect();
        let b: Vec<f64> = ref_returns.iter().rev().take(n).copied().collect();
        correlation(&a, &b)
    } else {
        None
    };

    let out = Output {
        name: fixture.name,
        bar_count: candles.len(),
        sma: sma(&closes, fixture.ema_period),
        ema: ema(&closes, fixture.ema_period),
        atr: atr(&candles, fixture.atr_period),
        efficiency_ratio: efficiency_ratio(&closes, fixture.er_period),
        percentile_of_last_close: last_close.and_then(|v| percentile_rank(&closes, v)),
        correlation_with_reference: corr,
        returns_count: sym_returns.len(),
        returns_sum: sym_returns.iter().sum(),
    };

    match serde_json::to_string_pretty(&out) {
        Ok(json) => println!("{json}"),
        Err(e) => {
            eprintln!("failed to serialise output: {e}");
            std::process::exit(2);
        }
    }
}
