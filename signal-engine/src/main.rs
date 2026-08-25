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
use signal_engine::ingest::{bootstrap_history, now_ms};
use signal_engine::venue::Venue;
use signal_engine::publish;
use signal_engine::pulse::GlobalPulse;
use signal_engine::scoring::{score, MarketSnapshot, ScoringConfig, TimeframeData};

const DEFAULT_SYMBOLS: &str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT";

/// The staleness budget both planes enforce: `scoring::Weights::max_feed_age_ms` raises
/// `Veto::StaleFeed` past this, and the Python `PulseClient` rejects the pulse outright.
const BOOK_STALENESS_BUDGET_MS: u64 = 15_000;
/// Worst-case time for one book request, so the schedule leaves room for it. Matches the
/// HTTP client timeout in `ingest::poll_book_tops`; a stamp is taken only after a
/// response is parsed, so interval + request is the real stamp-to-stamp gap.
const BOOK_REQUEST_BUDGET_MS: u64 = 10_000;

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
    // Bootstrap MUST eventually succeed: the score loop cannot warm the 1h/4h
    // timeframes from forward polling alone (that would take days), so an aborted
    // bootstrap — e.g. the host's shared egress IP is rate-limit banned at the venue,
    // seen live on first deploy — retries after the ban lifts instead of giving up.
    // Until it succeeds the engine publishes nothing, consumers' staleness gates hold,
    // and sessions fail closed: cold and honest beats warm and wrong.
    info!("bootstrapping history over REST...");
    let mut bootstrap_shutdown = shutdown_rx.clone();
    let (loaded, active_venue) = loop {
        let (loaded, ban_until, venue) = bootstrap_history(&store, &symbols, 500).await;
        if loaded > 0 {
            // The venue that answered owns this process's history. Mixing venues within
            // one symbol's window silently shifts every volume/range factor, so this
            // choice is sticky until the next restart (see signal_engine::venue).
            break (loaded, venue.unwrap_or(Venue::Binance));
        }
        let wait_ms = ban_until
            .map(|until| (until - now_ms()).clamp(60_000, 3_600_000))
            .unwrap_or(300_000);
        warn!(
            "bootstrap loaded nothing — retrying in {}s (venue ban or outage)",
            wait_ms / 1000
        );
        tokio::select! {
            _ = tokio::time::sleep(Duration::from_millis(wait_ms as u64)) => {}
            _ = bootstrap_shutdown.changed() => {
                info!("shutdown during bootstrap wait");
                return;
            }
        }
    };
    info!("bootstrapped {loaded} bars from {}", active_venue.name());

    // Closed bars by REST at each timeframe boundary (R1.4) — the kline websocket
    // fleet is gone: it pushed intra-bar updates the scorer discarded, at ~0.6GB/mo
    // per stream. The boundary poll carries the identical scored information.
    let feed = tokio::spawn(signal_engine::ingest::poll_klines(
        Arc::clone(&store),
        symbols.clone(),
        shutdown_rx.clone(),
        active_venue,
    ));

    let perp = tokio::spawn(signal_engine::ingest::poll_perp_state(
        Arc::clone(&store),
        symbols.clone(),
        shutdown_rx.clone(),
    ));

    // Top-of-book by REST on the scoring cadence rather than the @bookTicker stream.
    // It also carries the feed heartbeat, so the gap between two STAMPS must stay inside
    // the 15s staleness budget both planes enforce.
    //
    // The schedule alone does not bound that gap: a stamp is taken after the response is
    // parsed, so the worst case is one interval plus one request. With a 10s interval and
    // the 10s client timeout, a fast poll followed by a slow-but-successful one is ~19.5s
    // apart — a StaleFeed veto on healthy data. Budget for the request explicitly instead
    // of assuming the cadence covers it.
    let book_interval_ms = tick_ms
        .clamp(1_000, BOOK_STALENESS_BUDGET_MS.saturating_sub(BOOK_REQUEST_BUDGET_MS));
    let book = tokio::spawn(signal_engine::ingest::poll_book_tops(
        Arc::clone(&store),
        symbols.clone(),
        Duration::from_millis(book_interval_ms),
        shutdown_rx.clone(),
    ));

    let scorer = tokio::spawn(score_loop(
        Arc::clone(&store),
        symbols.clone(),
        redis_url,
        tick_ms,
        warmup_bars,
        shutdown_rx,
        active_venue,
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
        let _ = book.await;
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
    // Stamped onto every pulse: which venue's candles these scores were computed from.
    venue: Venue,
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
        // (tradability, vetoed) per published pulse — feeds the cross-market aggregate.
        let mut tick_scores: Vec<(u8, bool)> = Vec::new();

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
                    venue: venue.name().to_string(),
                }
            };

            let scored = score(&snapshot, &cfg);
            if publish::publish(&mut conn, &scored.pulse).await {
                published += 1;
                tick_scores.push((scored.pulse.tradability, !scored.pulse.vetoes.is_empty()));
            }
        }

        // The cross-market "is the market hot" aggregate (FR-SIGNAL-2) — published on
        // the same tick from the same pulses, so it can never disagree with them.
        if let Some(global) = GlobalPulse::aggregate(now, &tick_scores) {
            publish::publish_global(&mut conn, &global).await;
        }

        if cold > 0 {
            warn!("{published} pulses published, {cold} symbols still warming up");
        } else {
            info!("{published} pulses published");
        }
    }
}
