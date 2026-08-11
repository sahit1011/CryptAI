//! Binance market data ingest.
//!
//! Message *parsing* is pure and separated from the socket, so the part most likely to
//! break silently — a renamed field, a string where a float was expected — is unit
//! testable without a network. The socket layer only owns connection lifecycle.
//!
//! Reconnect uses exponential backoff with a cap. The failure mode being avoided is a
//! busy-spin reconnect loop against a rate-limited endpoint, which turns a brief outage
//! into a ban.

use std::sync::Arc;
use std::time::Duration;

use futures_util::StreamExt;
use serde::Deserialize;
use tokio::sync::RwLock;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message;
use tracing::{debug, error, info, warn};

use crate::feature_store::{BookTop, FeatureStore, TIMEFRAMES};
use crate::indicators::Candle;

const WS_BASE: &str = "wss://stream.binance.com:9443/stream?streams=";
const REST_BASE: &str = "https://api.binance.com/api/v3";

const BACKOFF_START: Duration = Duration::from_secs(1);
const BACKOFF_MAX: Duration = Duration::from_secs(60);

/// A parsed market event. The socket layer produces these; the store consumes them.
#[derive(Debug, Clone, PartialEq)]
pub enum Event {
    /// A CLOSED candle. Unclosed updates are discarded — scoring a forming bar means
    /// scoring a number that is still changing, which no backtest can reproduce.
    Candle {
        symbol: String,
        timeframe: String,
        candle: Candle,
    },
    Book {
        symbol: String,
        top: BookTop,
    },
}

// ---------------------------------------------------------------- parsing

#[derive(Deserialize)]
struct Envelope {
    stream: String,
    data: serde_json::Value,
}

#[derive(Deserialize)]
struct KlinePayload {
    s: String,
    k: KlineBody,
}

#[derive(Deserialize)]
struct KlineBody {
    #[serde(rename = "T")]
    close_time: i64,
    i: String,
    o: String,
    h: String,
    l: String,
    c: String,
    v: String,
    /// Binance sets this true only on the final update for a bar.
    x: bool,
}

#[derive(Deserialize)]
struct BookTickerPayload {
    s: String,
    b: String,
    #[serde(rename = "B")]
    bid_qty: String,
    a: String,
    #[serde(rename = "A")]
    ask_qty: String,
}

fn f(s: &str) -> Option<f64> {
    s.parse::<f64>().ok().filter(|v| v.is_finite())
}

/// Parse one combined-stream frame. `None` for anything not understood or not actionable
/// (an unclosed candle, an unknown stream, a malformed number).
pub fn parse_frame(raw: &str, now_ms: i64) -> Option<Event> {
    let env: Envelope = serde_json::from_str(raw).ok()?;

    if env.stream.contains("@kline") {
        let p: KlinePayload = serde_json::from_value(env.data).ok()?;
        // Only closed bars.
        if !p.k.x {
            return None;
        }
        let candle = Candle {
            open: f(&p.k.o)?,
            high: f(&p.k.h)?,
            low: f(&p.k.l)?,
            close: f(&p.k.c)?,
            volume: f(&p.k.v).unwrap_or(0.0),
            close_time: p.k.close_time,
        };
        // Reject nonsense geometry rather than poisoning every downstream window.
        if candle.high < candle.low || candle.close <= 0.0 {
            return None;
        }
        return Some(Event::Candle {
            symbol: p.s.to_uppercase(),
            timeframe: p.k.i,
            candle,
        });
    }

    if env.stream.contains("@bookTicker") {
        let p: BookTickerPayload = serde_json::from_value(env.data).ok()?;
        return Some(Event::Book {
            symbol: p.s.to_uppercase(),
            top: BookTop {
                bid: f(&p.b)?,
                ask: f(&p.a)?,
                bid_qty: f(&p.bid_qty).unwrap_or(0.0),
                ask_qty: f(&p.ask_qty).unwrap_or(0.0),
                ts: now_ms,
            },
        });
    }

    None
}

/// Combined-stream URL for the configured symbols and timeframes.
///
/// Klines only. `@bookTicker` is deliberately NOT streamed: it pushes on every best
/// bid/ask change, which at a handful of symbols is a continuous firehose whose bytes
/// dwarf everything else this process does — it was half of the egress that exhausted a
/// 5GB/month allowance and suspended the host. The scorer only reads the book once per
/// tick, so a REST snapshot at that cadence carries the same information (see
/// `poll_book_tops`) for a fraction of a percent of the bandwidth.
pub fn stream_url(symbols: &[String]) -> String {
    let mut streams: Vec<String> = Vec::new();
    for symbol in symbols {
        let lower = symbol.to_lowercase();
        for (tf, _) in TIMEFRAMES {
            streams.push(format!("{lower}@kline_{tf}"));
        }
    }
    format!("{WS_BASE}{}", streams.join("/"))
}

// ---------------------------------------------------------------- REST bootstrap

#[allow(clippy::indexing_slicing)]
fn kline_row_to_candle(row: &serde_json::Value) -> Option<Candle> {
    let arr = row.as_array()?;
    Some(Candle {
        open: f(arr.get(1)?.as_str()?)?,
        high: f(arr.get(2)?.as_str()?)?,
        low: f(arr.get(3)?.as_str()?)?,
        close: f(arr.get(4)?.as_str()?)?,
        volume: f(arr.get(5)?.as_str()?).unwrap_or(0.0),
        close_time: arr.get(6)?.as_i64()?,
    })
}

/// Backfill history over REST so the engine can score immediately instead of waiting
/// hours for the websocket to accumulate enough closed bars.
///
/// Without this the service starts up emitting `InsufficientHistory` vetoes for every
/// symbol — correct, but useless, and for the 4h timeframe it would take weeks.
pub async fn bootstrap_history(
    store: &Arc<RwLock<FeatureStore>>,
    symbols: &[String],
    limit: usize,
) -> usize {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .unwrap_or_default();

    let mut loaded = 0usize;
    for symbol in symbols {
        for (tf, _) in TIMEFRAMES {
            let url = format!("{REST_BASE}/klines?symbol={symbol}&interval={tf}&limit={limit}");
            let rows: Vec<serde_json::Value> = match client.get(&url).send().await {
                Ok(resp) => match resp.json().await {
                    Ok(v) => v,
                    Err(e) => {
                        warn!("bootstrap {symbol} {tf}: bad JSON: {e}");
                        continue;
                    }
                },
                Err(e) => {
                    warn!("bootstrap {symbol} {tf}: {e}");
                    continue;
                }
            };

            let mut guard = store.write().await;
            let state = guard.entry(symbol);
            // Drop the final row BEFORE pushing: it is the bar still forming, and its
            // close_time is in the FUTURE (a 4h bar opened 10 minutes ago closes in
            // 3h50m). Pushing it and popping it afterwards leaves last_event_ts set to
            // that future timestamp, which makes feed_ts exceed now and every staleness
            // check pass forever — a dead feed would look eternally fresh. Verified
            // against live data on 2026-08-02: feed_ts led ts by 1.8 hours.
            let complete = rows.len().saturating_sub(1);
            for row in rows.iter().take(complete) {
                if let Some(candle) = kline_row_to_candle(row) {
                    state.push_candle(tf, candle);
                    loaded += 1;
                }
            }
            drop(guard);

            // Stay well inside the public REST weight limit.
            tokio::time::sleep(Duration::from_millis(120)).await;
        }
        info!("bootstrapped history for {symbol}");
    }
    loaded
}

// ---------------------------------------------------------------- perp state

const FAPI_BASE: &str = "https://fapi.binance.com/fapi/v1";

/// Poll funding rate and open interest from the USDT-M futures API.
///
/// REST rather than a second websocket: funding updates every 8 hours and open interest
/// every few minutes, so a 60s poll is well inside the resolution that matters, and it
/// avoids a second connection lifecycle to get wrong.
///
/// NOTE ON VENUE: klines and the book come from Binance SPOT while these come from
/// FUTURES. That is deliberate — spot has the deeper, cleaner price history, and funding
/// and open interest only exist on the perp. It does mean the two are not the same
/// instrument; the basis is small for majors but is a known simplification.
///
/// Failures are logged and skipped. A symbol with no perp listing (a spot-only pair such
/// as XAUTUSDT) simply never populates these fields, and the positioning factor stays
/// neutral for it rather than blocking the whole loop.
pub async fn poll_perp_state(
    store: Arc<RwLock<FeatureStore>>,
    symbols: Vec<String>,
    mut shutdown: tokio::sync::watch::Receiver<bool>,
) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            error!("cannot build perp HTTP client: {e}");
            return;
        }
    };

    let mut ticker = tokio::time::interval(Duration::from_secs(60));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        tokio::select! {
            _ = ticker.tick() => {}
            _ = shutdown.changed() => {
                info!("perp poller shutting down");
                return;
            }
        }

        for symbol in &symbols {
            let funding = fetch_funding(&client, symbol).await;
            let oi = fetch_open_interest(&client, symbol).await;
            if funding.is_none() && oi.is_none() {
                continue;
            }

            let now = now_ms();
            let mut guard = store.write().await;
            let state = guard.entry(symbol);
            if let Some(rate) = funding {
                state.perp.funding_rate = rate;
                state.perp.ts = now;
            }
            if let Some(value) = oi {
                state.push_open_interest(now, value);
            }
        }
    }
}

/// Poll top-of-book for every symbol in ONE request, on the scoring cadence.
///
/// Replaces the `@bookTicker` stream. Two things make the swap safe:
///
/// 1. **The scorer only reads the book once per tick**, so a snapshot taken at that same
///    cadence carries the same information a tick-by-tick stream would have left behind.
///    Spread and touch size are the only fields consumed (`book_quality`, `SpreadTooWide`,
///    `InsufficientDepth`), and none of them turn over meaningfully inside one tick.
/// 2. **It carries the feed heartbeat.** `last_event_ts` feeds `feed_ts`, and BOTH planes
///    fail closed past 15s — the Rust scorer raises `Veto::StaleFeed`
///    (`max_feed_age_ms`) and the Python `PulseClient` rejects the pulse outright. Closed
///    candles arrive every 5 minutes and the perp poller every 60s, so without this the
///    feed would read as permanently stale and every session's pulse gate would refuse to
///    run. `interval` MUST stay well inside that 15s budget.
///
/// Bandwidth is the whole point: one ~700B request per tick instead of an unbounded
/// push on every best bid/ask change.
pub async fn poll_book_tops(
    store: Arc<RwLock<FeatureStore>>,
    symbols: Vec<String>,
    interval: Duration,
    mut shutdown: tokio::sync::watch::Receiver<bool>,
) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            error!("cannot build book HTTP client: {e}");
            return;
        }
    };

    // Binance accepts a JSON array of symbols and answers with one array — so the cost
    // is a single round trip regardless of how many symbols are configured.
    let symbols_param = format!(
        "[{}]",
        symbols
            .iter()
            .map(|s| format!("\"{}\"", s.to_uppercase()))
            .collect::<Vec<_>>()
            .join(",")
    );
    let url = format!("{REST_BASE}/ticker/bookTicker");

    let mut ticker = tokio::time::interval(interval);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        tokio::select! {
            _ = ticker.tick() => {}
            _ = shutdown.changed() => {
                info!("book poller shutting down");
                return;
            }
        }

        let tops = fetch_book_tops(&client, &url, &symbols_param).await;
        if tops.is_empty() {
            // A failed poll is survivable: the previous book stands and the staleness
            // gate takes over if the outage outlives the budget. That is the honest
            // outcome — better than scoring on a book we could not refresh.
            continue;
        }

        let mut guard = store.write().await;
        for (symbol, top) in tops {
            let state = guard.entry(&symbol);
            state.last_event_ts = state.last_event_ts.max(top.ts);
            state.book = top;
        }
    }
}

async fn fetch_book_tops(
    client: &reqwest::Client,
    url: &str,
    symbols_param: &str,
) -> Vec<(String, BookTop)> {
    let body: serde_json::Value = match client
        .get(url)
        .query(&[("symbols", symbols_param)])
        .send()
        .await
    {
        Ok(r) => match r.json().await {
            Ok(v) => v,
            Err(e) => {
                warn!("book poll: bad JSON: {e}");
                return Vec::new();
            }
        },
        Err(e) => {
            warn!("book poll failed: {e}");
            return Vec::new();
        }
    };

    let now = now_ms();
    let Some(rows) = body.as_array() else {
        warn!("book poll: expected an array, got something else");
        return Vec::new();
    };

    let mut out = Vec::new();
    for row in rows {
        let Some(symbol) = row.get("symbol").and_then(|v| v.as_str()) else {
            continue;
        };
        let num = |k: &str| row.get(k).and_then(|v| v.as_str()).and_then(f);
        // A book without both sides priced is not a book — skip it rather than let a
        // zero masquerade as a real quote and produce a nonsense spread.
        let (Some(bid), Some(ask)) = (num("bidPrice"), num("askPrice")) else {
            continue;
        };
        out.push((
            symbol.to_uppercase(),
            BookTop {
                bid,
                ask,
                bid_qty: num("bidQty").unwrap_or(0.0),
                ask_qty: num("askQty").unwrap_or(0.0),
                ts: now,
            },
        ));
    }
    out
}

async fn fetch_funding(client: &reqwest::Client, symbol: &str) -> Option<f64> {
    let url = format!("{FAPI_BASE}/premiumIndex?symbol={symbol}");
    let body: serde_json::Value = client.get(&url).send().await.ok()?.json().await.ok()?;
    body.get("lastFundingRate")?.as_str().and_then(f)
}

async fn fetch_open_interest(client: &reqwest::Client, symbol: &str) -> Option<f64> {
    let url = format!("{FAPI_BASE}/openInterest?symbol={symbol}");
    let body: serde_json::Value = client.get(&url).send().await.ok()?.json().await.ok()?;
    body.get("openInterest")?.as_str().and_then(f)
}

// ---------------------------------------------------------------- socket loop

/// Connect and stream forever, reconnecting with capped exponential backoff.
///
/// Returns only when `shutdown` fires. Every other exit path reconnects: a signal engine
/// that quietly stops publishing looks exactly like a calm market to its consumers, which
/// is why the staleness contract exists on the read side as well.
pub async fn run_feed(
    store: Arc<RwLock<FeatureStore>>,
    symbols: Vec<String>,
    mut shutdown: tokio::sync::watch::Receiver<bool>,
) {
    let url = stream_url(&symbols);
    let mut backoff = BACKOFF_START;

    loop {
        if *shutdown.borrow() {
            info!("feed shutting down");
            return;
        }

        info!("connecting to Binance stream ({} symbols)", symbols.len());
        let stream = tokio::select! {
            r = connect_async(&url) => r,
            _ = shutdown.changed() => return,
        };

        let (_, mut read) = match stream {
            Ok((ws, _)) => {
                info!("feed connected");
                backoff = BACKOFF_START; // only reset after a real connection
                ws.split()
            }
            Err(e) => {
                error!("feed connect failed: {e}; retrying in {:?}", backoff);
                tokio::select! {
                    _ = tokio::time::sleep(backoff) => {}
                    _ = shutdown.changed() => return,
                }
                backoff = (backoff * 2).min(BACKOFF_MAX);
                continue;
            }
        };

        loop {
            let msg = tokio::select! {
                m = read.next() => m,
                _ = shutdown.changed() => return,
            };

            let Some(msg) = msg else {
                warn!("feed stream ended; reconnecting");
                break;
            };

            match msg {
                Ok(Message::Text(text)) => {
                    let now = now_ms();
                    if let Some(event) = parse_frame(&text, now) {
                        apply(&store, event).await;
                    }
                }
                Ok(Message::Ping(_) | Message::Pong(_)) => {}
                Ok(Message::Close(frame)) => {
                    warn!("feed closed by peer: {frame:?}");
                    break;
                }
                Ok(_) => {}
                Err(e) => {
                    error!("feed read error: {e}");
                    break;
                }
            }
        }

        tokio::select! {
            _ = tokio::time::sleep(backoff) => {}
            _ = shutdown.changed() => return,
        }
        backoff = (backoff * 2).min(BACKOFF_MAX);
    }
}

async fn apply(store: &Arc<RwLock<FeatureStore>>, event: Event) {
    let mut guard = store.write().await;
    match event {
        Event::Candle {
            symbol,
            timeframe,
            candle,
        } => {
            debug!("candle {symbol} {timeframe} @ {}", candle.close);
            guard.entry(&symbol).push_candle(&timeframe, candle);
        }
        Event::Book { symbol, top } => {
            let state = guard.entry(&symbol);
            state.last_event_ts = state.last_event_ts.max(top.ts);
            state.book = top;
        }
    }
}

pub fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn kline_frame(closed: bool, interval: &str) -> String {
        format!(
            r#"{{"stream":"btcusdt@kline_{interval}","data":{{"e":"kline","s":"BTCUSDT",
            "k":{{"t":1700000000000,"T":1700003599999,"i":"{interval}","o":"100.5","h":"102.0",
            "l":"99.0","c":"101.25","v":"1234.5","x":{closed}}}}}}}"#
        )
    }

    #[test]
    fn parses_a_closed_candle() {
        let ev = parse_frame(&kline_frame(true, "1h"), 0).expect("parsed");
        match ev {
            Event::Candle {
                symbol,
                timeframe,
                candle,
            } => {
                assert_eq!(symbol, "BTCUSDT");
                assert_eq!(timeframe, "1h");
                assert_eq!(candle.close, 101.25);
                assert_eq!(candle.high, 102.0);
                assert_eq!(candle.close_time, 1700003599999);
            }
            other => panic!("wrong event: {other:?}"),
        }
    }

    #[test]
    fn discards_an_unclosed_candle() {
        // Scoring a forming bar means scoring a number that is still changing, and no
        // backtest can reproduce it.
        assert_eq!(parse_frame(&kline_frame(false, "1h"), 0), None);
    }

    #[test]
    fn parses_a_book_ticker() {
        let raw = r#"{"stream":"btcusdt@bookTicker","data":{"s":"BTCUSDT","b":"99.99",
            "B":"5.0","a":"100.01","A":"3.0"}}"#;
        match parse_frame(raw, 12345).expect("parsed") {
            Event::Book { symbol, top } => {
                assert_eq!(symbol, "BTCUSDT");
                assert_eq!(top.bid, 99.99);
                assert_eq!(top.ts, 12345);
                assert!((top.spread_bps().expect("spread") - 2.0).abs() < 1e-6);
            }
            other => panic!("wrong event: {other:?}"),
        }
    }

    #[test]
    fn malformed_input_returns_none_rather_than_panicking() {
        // A panic here takes down the shared plane for every tenant.
        for raw in [
            "",
            "not json",
            r#"{"stream":"x","data":{}}"#,
            r#"{"stream":"btcusdt@kline_1h","data":{"s":"BTCUSDT","k":{"x":true}}}"#,
            r#"{"stream":"btcusdt@bookTicker","data":{"s":"B","b":"abc","a":"1","B":"1","A":"1"}}"#,
        ] {
            assert_eq!(parse_frame(raw, 0), None, "should have rejected: {raw}");
        }
    }

    #[test]
    fn rejects_a_candle_with_impossible_geometry() {
        let raw = r#"{"stream":"btcusdt@kline_1h","data":{"s":"BTCUSDT","k":{"t":1,"T":2,
            "i":"1h","o":"100","h":"90","l":"110","c":"100","v":"1","x":true}}}"#;
        assert_eq!(parse_frame(raw, 0), None, "high < low was accepted");
    }

    #[test]
    fn rejects_a_non_positive_close() {
        let raw = r#"{"stream":"btcusdt@kline_1h","data":{"s":"BTCUSDT","k":{"t":1,"T":2,
            "i":"1h","o":"100","h":"110","l":"90","c":"0","v":"1","x":true}}}"#;
        assert_eq!(parse_frame(raw, 0), None);
    }

    #[test]
    fn ignores_streams_it_does_not_understand() {
        let raw = r#"{"stream":"btcusdt@depth20","data":{"bids":[],"asks":[]}}"#;
        assert_eq!(parse_frame(raw, 0), None);
    }

    #[test]
    fn stream_url_covers_every_timeframe() {
        let url = stream_url(&["BTCUSDT".to_string(), "ETHUSDT".to_string()]);
        for tf in ["5m", "15m", "1h", "4h"] {
            assert!(url.contains(&format!("btcusdt@kline_{tf}")), "missing {tf}");
            assert!(
                url.contains(&format!("ethusdt@kline_{tf}")),
                "missing eth {tf}"
            );
        }
        assert!(url.starts_with("wss://"));
    }

    #[test]
    fn stream_url_never_subscribes_the_book() {
        // @bookTicker pushes on every best bid/ask change and was half the egress that
        // exhausted the host's monthly bandwidth. Top-of-book now arrives by REST on the
        // scoring cadence (poll_book_tops). Re-adding it here would silently restore the
        // firehose, so this asserts the absence rather than trusting a comment.
        let url = stream_url(&["BTCUSDT".to_string(), "ETHUSDT".to_string()]);
        assert!(
            !url.contains("bookTicker"),
            "the book must not be streamed: {url}"
        );
    }

    #[test]
    fn symbols_are_lowercased_for_the_stream_but_uppercased_on_events() {
        // Binance requires lowercase in the URL and reports uppercase in payloads.
        // Getting this backwards silently subscribes to nothing.
        assert!(stream_url(&["BtCuSdT".to_string()]).contains("btcusdt@kline_5m"));
        match parse_frame(&kline_frame(true, "5m"), 0).expect("parsed") {
            Event::Candle { symbol, .. } => assert_eq!(symbol, "BTCUSDT"),
            other => panic!("wrong event: {other:?}"),
        }
    }
}
