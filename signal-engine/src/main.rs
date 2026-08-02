//! The signal engine service.
//!
//! Bootstraps history over REST, streams live bars over websocket, scores every symbol on
//! a fixed tick, and publishes pulses to Redis. Runs forever; no user ever touches it.
//!
//! ```text
//! SYMBOLS=BTCUSDT,ETHUSDT REDIS_URL=redis://localhost:6379 cargo run --release
//! ```
//!
//! Environment:
//!   SYMBOLS      comma-separated (default: a liquid-perp starter set)
//!   REDIS_URL    default redis://localhost:6379
//!   TICK_MS      scoring cadence, default 5000
//!   WARMUP_BARS  minimum bars per timeframe before scoring, default 250
//!   RUST_LOG     tracing filter, default info

use std::sync::Arc;
use std::time::Duration;

use tokio::sync::{watch, RwLock};
use tracing::{error, info, warn};

use signal_engine::feature_store::{FeatureStore, TIMEFRAMES};
use signal_engine::ingest::{bootstrap_history, now_ms, run_feed};
use signal_engine::publish;
use signal_engine::scoring::{score, MarketSnapshot, ScoringConfig, TimeframeData};

const DEFAULT_SYMBOLS: &str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT";

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let symbols: Vec<String> = env_or("SYMBOLS", DEFAULT_SYMBOLS)
        .split(',')
        .map(|s| s.trim().to_uppercase())
        .filter(|s| !s.is_empty())
        .collect();

    if symbols.is_empty() {
        error!("no symbols configured");
        std::process::exit(2);
    }

    let redis_url = env_or("REDIS_URL", "redis://localhost:6379");
    let tick_ms: u64 = env_or("TICK_MS", "5000").parse().unwrap_or(5000);
    let warmup_bars: usize = env_or("WARMUP_BARS", "250").parse().unwrap_or(250);

    info!(
        "signal engine starting: {} symbols, tick {}ms, warmup {} bars",
        symbols.len(),
        tick_ms,
        warmup_bars
    );

    let store = Arc::new(RwLock::new(FeatureStore::new()));
    let (shutdown_tx, shutdown_rx) = watch::channel(false);

    // Backfill first. Without it the 4h timeframe would need weeks of uptime before the
    // engine could score anything, and every pulse until then would be an
    // InsufficientHistory veto — correct, but useless.
    info!("bootstrapping history over REST...");
    let loaded = bootstrap_history(&store, &symbols, 500).await;
    info!("bootstrapped {loaded} bars");

    let feed = tokio::spawn(run_feed(
        Arc::clone(&store),
        symbols.clone(),
        shutdown_rx.clone(),
    ));

    let perp = tokio::spawn(signal_engine::ingest::poll_perp_state(
        Arc::clone(&store),
        symbols.clone(),
        shutdown_rx.clone(),
    ));

    let scorer = tokio::spawn(score_loop(
        Arc::clone(&store),
        symbols.clone(),
        redis_url,
        tick_ms,
        warmup_bars,
        shutdown_rx,
    ));

    // Handle both SIGINT and SIGTERM: containers are stopped with SIGTERM, and only
    // handling Ctrl-C means every deploy is an ungraceful kill.
    let mut sigterm = match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
    {
        Ok(s) => s,
        Err(e) => {
            error!("cannot install SIGTERM handler: {e}");
            return;
        }
    };
    tokio::select! {
        _ = tokio::signal::ctrl_c() => info!("SIGINT received, shutting down"),
        _ = sigterm.recv() => info!("SIGTERM received, shutting down"),
    }

    let _ = shutdown_tx.send(true);
    let _ = tokio::time::timeout(Duration::from_secs(10), async {
        let _ = feed.await;
        let _ = perp.await;
        let _ = scorer.await;
    })
    .await;
    info!("stopped");
}

async fn score_loop(
    store: Arc<RwLock<FeatureStore>>,
    symbols: Vec<String>,
    redis_url: String,
    tick_ms: u64,
    warmup_bars: usize,
    mut shutdown: watch::Receiver<bool>,
) {
    let mut conn = loop {
        match publish::connect(&redis_url).await {
            Ok(c) => break c,
            Err(e) => {
                error!("redis connect failed: {e}; retrying in 5s");
                tokio::select! {
                    _ = tokio::time::sleep(Duration::from_secs(5)) => {}
                    _ = shutdown.changed() => return,
                }
            }
        }
    };
    info!("redis connected");

    let cfg = ScoringConfig::default();
    let mut ticker = tokio::time::interval(Duration::from_millis(tick_ms));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        tokio::select! {
            _ = ticker.tick() => {}
            _ = shutdown.changed() => {
                info!("score loop shutting down");
                return;
            }
        }

        let now = now_ms();
        let mut published = 0usize;
        let mut cold = 0usize;

        // BTC is the market's common factor: when everything moves with it, several
        // "diversified" positions are one position, and the per-user risk layer needs to
        // know that. Read once per tick rather than per symbol.
        let btc_closes: Vec<f64> = {
            let guard = store.read().await;
            guard
                .get("BTCUSDT")
                .map(|s| s.candles_for("1h").iter().map(|c| c.close).collect())
                .unwrap_or_default()
        };

        for symbol in &symbols {
            let snapshot = {
                let guard = store.read().await;
                let Some(state) = guard.get(symbol) else {
                    cold += 1;
                    continue;
                };
                if !state.is_warm(warmup_bars) {
                    cold += 1;
                    continue;
                }

                let timeframes: Vec<TimeframeData> = TIMEFRAMES
                    .iter()
                    .map(|(tf, weight)| TimeframeData {
                        label: tf,
                        weight: *weight,
                        candles: state.candles_for(tf),
                    })
                    .collect();

                // A missing or crossed book is not "zero spread" — treat it as unusable
                // so the veto fires rather than scoring a perfect book that isn't there.
                let spread_bps = state.book.spread_bps().unwrap_or(f64::MAX);

                MarketSnapshot {
                    symbol: symbol.clone(),
                    now_ms: now,
                    feed_ts: state.last_event_ts,
                    timeframes,
                    funding_rate: state.perp.funding_rate,
                    oi_delta_1h: state.perp.oi_delta_1h(),
                    spread_bps,
                    depth_usd: state.book.touch_notional(),
                    // Correlating BTC against itself would report 1.0, which is true but
                    // useless; leave it empty so the factor reads as "not applicable".
                    btc_closes: if symbol == "BTCUSDT" {
                        Vec::new()
                    } else {
                        btc_closes.clone()
                    },
                }
            };

            let scored = score(&snapshot, &cfg);
            if publish::publish(&mut conn, &scored.pulse).await {
                published += 1;
            }
        }

        if cold > 0 {
            warn!("{published} pulses published, {cold} symbols still warming up");
        } else {
            info!("{published} pulses published");
        }
    }
}
