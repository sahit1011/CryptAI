//! Binance market data ingest — REST only, no websockets (R1.4).
//!
//! The scorer consumes exactly three things, each on a slow, known cadence:
//! CLOSED candles (once per timeframe boundary), the top of book (once per 5s scoring
//! tick), and funding/open-interest (changes over minutes-to-hours). Every one of those
//! is a poll, not a stream. The kline websocket fleet this replaces pushed intra-bar
//! updates the engine then *discarded* (only closed bars are scored — a forming bar is
//! a number still changing, which no backtest can reproduce), at ~0.6GB/mo per stream
//! against a 5GB/mo host budget. Polling the closed bar at its boundary carries the
//! identical information the scorer read, for ~2MB/mo.
//!
//! Row *parsing* stays pure and separated from I/O, so the part most likely to break
//! silently — a renamed field, a string where a float was expected — is unit testable
//! without a network.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use tokio::sync::RwLock;
use tracing::{error, info, warn};

use crate::feature_store::{BookTop, FeatureStore, TIMEFRAMES};
use crate::indicators::Candle;
use crate::venue::{Venue, FALLBACK_ORDER};

/// Public market data goes through Binance's DATA MIRROR, not api.binance.com: the
/// per-IP request-weight budget on the main API is shared with every other tenant on
/// the host's egress IP (a cloud box got this engine 418-banned within minutes of its
/// first deploy, at ~48 weight/min of its own usage against a 6,000/min budget). The
/// mirror exists precisely for public data consumers and serves identical /api/v3
/// endpoints. Funding/OI stay on fapi (no mirror exists) at one poll a minute.
const REST_BASE: &str = "https://data-api.binance.vision/api/v3";

/// How long to stay away after the venue says go away (ms since epoch), or None for a
/// non-rate-limit status. 418 means an active IP ban — CONTINUING TO SEND requests
/// while banned is what escalates bans (2min → 3 days), so callers must actually wait.
pub fn ban_until_ms(status: u16, body: &str, now_ms: i64) -> Option<i64> {
    if status != 418 && status != 429 {
        return None;
    }
    // Binance embeds the expiry: "... IP banned until 1787609279289."
    if let Some(idx) = body.find("banned until ") {
        let digits: String = body[idx + "banned until ".len()..]
            .chars()
            .take_while(char::is_ascii_digit)
            .collect();
        if let Ok(ts) = digits.parse::<i64>() {
            if ts > now_ms {
                // Cap at an hour: a clock-skewed or garbage timestamp must not
                // silence the feed for days.
                return Some(ts.min(now_ms + 3_600_000));
            }
        }
    }
    // No parseable expiry: back off hard on a ban, gently on a rate limit.
    Some(now_ms + if status == 418 { 600_000 } else { 60_000 })
}

// ---------------------------------------------------------------- parsing

fn f(s: &str) -> Option<f64> {
    s.parse::<f64>().ok().filter(|v| v.is_finite())
}

/// Reject nonsense geometry rather than poisoning every downstream window. The old
/// websocket path enforced this on every frame; REST rows get the identical gate.
pub fn candle_is_sane(candle: &Candle) -> bool {
    candle.high >= candle.low && candle.close > 0.0 && candle.close_time > 0
}

// ---------------------------------------------------------------- kline schedule

/// Milliseconds per configured timeframe. Kept adjacent to `TIMEFRAMES` (whose second
/// element is the scoring WEIGHT, not a duration) — `tf_millis_covers_every_timeframe`
/// pins the two lists together so a new timeframe cannot silently never be polled.
fn tf_millis(tf: &str) -> Option<i64> {
    match tf {
        "5m" => Some(300_000),
        "15m" => Some(900_000),
        "1h" => Some(3_600_000),
        "4h" => Some(14_400_000),
        _ => None,
    }
}

/// Binance needs a beat to finalize a bar after its boundary; fetching at T+0 can
/// return the PREVIOUS bar as the latest closed row.
const KLINE_SETTLE_MS: i64 = 3_000;


/// The close boundary of the most recent bar that is safely CLOSED at `now_ms`.
///
/// Pure, so the scheduler's arithmetic — the part that decides whether the engine
/// polls at all — is testable without a clock or a network.
pub fn latest_closed_boundary(now_ms: i64, tf_ms: i64, settle_ms: i64) -> i64 {
    ((now_ms - settle_ms) / tf_ms) * tf_ms
}

// ---------------------------------------------------------------- REST bootstrap

/// Backfill history over REST so the engine can score immediately instead of waiting
/// hours for enough closed bars to accumulate.
///
/// Without this the service starts up emitting `InsufficientHistory` vetoes for every
/// symbol — correct, but useless, and for the 4h timeframe it would take weeks.
///
/// VENUE FALLBACK. Tries `FALLBACK_ORDER` and returns the venue that actually answered.
/// A shared cloud egress IP gets us Binance-banned through other tenants' traffic, and
/// on 2026-08-25 that cost 1h42m of signal plane; a second venue turns that into
/// seconds. A symbol's history is never MIXED across venues — the first venue to load
/// anything wins for this whole process, and the store is cleared before each attempt
/// so a partial load from a banned venue cannot be topped up from another one.
pub async fn bootstrap_history(
    store: &Arc<RwLock<FeatureStore>>,
    symbols: &[String],
    limit: usize,
) -> (usize, Option<i64>, Option<Venue>) {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .unwrap_or_default();

    let mut first_ban: Option<i64> = None;

    for &venue in FALLBACK_ORDER {
        // A previous venue may have loaded some bars before being banned. Those bars
        // must not survive into this attempt: two venues' bars in one window shift
        // every volume- and range-derived factor silently.
        {
            let mut guard = store.write().await;
            for symbol in symbols {
                guard.entry(symbol).clear_candles();
            }
        }

        match bootstrap_from(&client, store, symbols, limit, venue).await {
            Ok(loaded) if loaded > 0 => {
                info!("bootstrap complete via {} ({loaded} bars)", venue.name());
                return (loaded, None, Some(venue));
            }
            Ok(_) => {
                warn!("bootstrap via {} returned no usable bars", venue.name());
            }
            Err(ban_until) => {
                first_ban = first_ban.or(ban_until);
                warn!(
                    "bootstrap via {} hit a rate limit/ban — trying the next venue",
                    venue.name()
                );
            }
        }
    }

    // Nothing answered. Report the earliest ban expiry so the caller waits rather than
    // hammering, exactly as before the fallback existed.
    (0, first_ban, None)
}

/// One venue's bootstrap attempt. `Err(Some(until_ms))` means it rate-limited us;
/// `Err(None)` means it failed for another reason. `Ok(n)` is bars loaded.
async fn bootstrap_from(
    client: &reqwest::Client,
    store: &Arc<RwLock<FeatureStore>>,
    symbols: &[String],
    limit: usize,
    venue: Venue,
) -> Result<usize, Option<i64>> {
    let mut loaded = 0usize;
    for symbol in symbols {
        for (tf, _) in TIMEFRAMES {
            let tf_ms = match tf_millis(tf) {
                Some(ms) => ms,
                None => continue,
            };
            let url = match venue.kline_url(symbol, tf, limit) {
                Some(u) => u,
                None => {
                    warn!("{} has no dialect for {tf}", venue.name());
                    continue;
                }
            };

            let body = match client.get(&url).send().await {
                Ok(resp) if resp.status().is_success() => resp.text().await.unwrap_or_default(),
                Ok(resp) => {
                    let status = resp.status();
                    let body = resp.text().await.unwrap_or_default();
                    if venue.is_rate_limit(status.as_u16()) {
                        error!(
                            "bootstrap aborted on {}: venue rate limit/ban ({status}) — \
                             hammering through a ban escalates it",
                            venue.name()
                        );
                        return Err(ban_until_ms(status.as_u16(), &body, now_ms())
                            .or(Some(now_ms() + 600_000)));
                    }
                    warn!("bootstrap {} {symbol} {tf}: HTTP {status}", venue.name());
                    continue;
                }
                Err(e) => {
                    warn!("bootstrap {} {symbol} {tf}: {e}", venue.name());
                    continue;
                }
            };

            let candles = match venue.parse_klines(&body, tf_ms) {
                Some(c) => c,
                None => {
                    // A body we cannot parse is a FAILED fetch, never an empty market.
                    warn!("bootstrap {} {symbol} {tf}: unparseable body", venue.name());
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
            let complete = candles.len().saturating_sub(1);
            for candle in candles.iter().take(complete) {
                if candle_is_sane(candle) {
                    state.push_candle(tf, *candle);
                    loaded += 1;
                }
            }
            drop(guard);

            // Stay well inside the public REST weight limit.
            tokio::time::sleep(Duration::from_millis(120)).await;
        }
        info!("bootstrapped history for {symbol} via {}", venue.name());
    }
    Ok(loaded)
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
    let mut banned_until: i64 = 0;

    loop {
        tokio::select! {
            _ = ticker.tick() => {}
            _ = shutdown.changed() => {
                info!("book poller shutting down");
                return;
            }
        }

        if now_ms() < banned_until {
            continue; // sit out the ban — polling through it is what escalates it
        }

        let (tops, ban) = fetch_book_tops(&client, &url, &symbols_param).await;
        if let Some(until) = ban {
            banned_until = until;
            warn!(
                "book poll pausing {}s: venue rate limit/ban — pulses will go stale and \
                 sessions will fail closed until it lifts (the designed outcome)",
                (until - now_ms()) / 1000
            );
            continue;
        }
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
) -> (Vec<(String, BookTop)>, Option<i64>) {
    let response = match client.get(url).query(&[("symbols", symbols_param)]).send().await {
        Ok(r) => r,
        Err(e) => {
            warn!("book poll failed: {e}");
            return (Vec::new(), None);
        }
    };

    // Check the status BEFORE parsing. An error body (`{"code":-1121,"msg":"Invalid
    // symbol."}`) is valid JSON, so without this it parsed cleanly, failed `as_array`,
    // and returned empty with only a debug-level clue. Since this poller is now the only
    // thing advancing `last_event_ts` between 5-minute candle closes, one bad symbol or a
    // rate-limit ban silently stalls the heartbeat for EVERY symbol — after 15s every
    // pulse carries StaleFeed and every session fails closed. Loud is the right volume.
    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        error!(
            "book poll rejected ({status}): {} — the feed heartbeat depends on this call",
            body.chars().take(200).collect::<String>()
        );
        return (Vec::new(), ban_until_ms(status.as_u16(), &body, now_ms()));
    }

    let body: serde_json::Value = match response.json().await {
        Ok(v) => v,
        Err(e) => {
            warn!("book poll: bad JSON: {e}");
            return (Vec::new(), None);
        }
    };

    let now = now_ms();
    let Some(rows) = body.as_array() else {
        warn!("book poll: expected an array, got something else");
        return (Vec::new(), None);
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
    (out, None)
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

// ---------------------------------------------------------------- kline polling

/// Poll CLOSED bars at each timeframe boundary, forever. Replaces the kline websocket.
///
/// Every `POLL_CHECK` it asks the pure scheduler whether any timeframe has crossed a
/// boundary (plus a settle delay); when one has, it fetches the missed closed rows per
/// symbol in a single request. A brief outage self-heals: the fetch limit grows with
/// the number of missed bars (capped), and `push_candle` overwrites replays and drops
/// out-of-order rows, so refetching is always safe.
///
/// Deliberately does NOT advance `last_event_ts`: the feed heartbeat rides the 5s book
/// poll, exactly as it did under the websocket — closed bars arrive minutes apart and
/// carry only their own close_time.
pub async fn poll_klines(
    store: Arc<RwLock<FeatureStore>>,
    symbols: Vec<String>,
    mut shutdown: tokio::sync::watch::Receiver<bool>,
    venue: Venue,
) {
    const POLL_CHECK: Duration = Duration::from_secs(5);
    // One request tops out here — after a longer outage, bootstrap-scale backfill is
    // not this loop's job.
    const MAX_MISSED: i64 = 99;

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .unwrap_or_default();

    // Start from "now": bootstrap_history just filled the store, so the first fetch for
    // each timeframe happens at its NEXT boundary rather than refetching immediately.
    let mut last_fetched: HashMap<&'static str, i64> = HashMap::new();
    for &(tf, _) in TIMEFRAMES {
        if let Some(tf_ms) = tf_millis(tf) {
            last_fetched.insert(tf, latest_closed_boundary(now_ms(), tf_ms, KLINE_SETTLE_MS));
        }
    }

    info!(
        "kline poller started ({} symbols x {} timeframes, boundary-driven)",
        symbols.len(),
        TIMEFRAMES.len()
    );
    let mut banned_until: i64 = 0;

    loop {
        tokio::select! {
            _ = tokio::time::sleep(POLL_CHECK) => {}
            _ = shutdown.changed() => {
                info!("kline poller shutting down");
                return;
            }
        }

        let now = now_ms();
        if now < banned_until {
            continue; // sit out the ban; missed boundaries refetch afterwards
        }
        for &(tf, _) in TIMEFRAMES {
            let Some(tf_ms) = tf_millis(tf) else { continue };
            let boundary = latest_closed_boundary(now, tf_ms, KLINE_SETTLE_MS);
            let last = last_fetched.get(tf).copied().unwrap_or(boundary);
            if boundary <= last {
                continue;
            }
            let missed = ((boundary - last) / tf_ms).clamp(1, MAX_MISSED);

            for symbol in &symbols {
                // +1 row for the forming bar venues append; dropped below.
                // MUST stay on the venue bootstrap chose: swapping mid-history would
                // interleave two venues' bars in one window (see crate::venue).
                let url = match venue.kline_url(symbol, tf, (missed + 1) as usize) {
                    Some(u) => u,
                    None => continue,
                };
                let body = match client.get(&url).send().await {
                    Ok(resp) if resp.status().is_success() => {
                        resp.text().await.unwrap_or_default()
                    }
                    Ok(resp) => {
                        let status = resp.status();
                        let body = resp.text().await.unwrap_or_default();
                        warn!("kline poll {symbol} {tf} [{}]: HTTP {status}", venue.name());
                        if venue.is_rate_limit(status.as_u16()) {
                            banned_until = ban_until_ms(status.as_u16(), &body, now_ms())
                                .unwrap_or(now_ms() + 600_000);
                        }
                        continue;
                    }
                    Err(e) => {
                        warn!("kline poll {symbol} {tf} [{}]: {e}", venue.name());
                        continue;
                    }
                };

                let candles = match venue.parse_klines(&body, tf_ms) {
                    Some(c) => c,
                    None => {
                        warn!("kline poll {symbol} {tf} [{}]: unparseable body", venue.name());
                        continue;
                    }
                };

                // Same rule as bootstrap: the final row is the bar still FORMING, whose
                // close_time is in the future — pushing it would poison staleness math.
                let complete = candles.len().saturating_sub(1);
                let mut guard = store.write().await;
                let state = guard.entry(symbol);
                for candle in candles.iter().take(complete) {
                    if candle_is_sane(candle) {
                        state.push_candle(tf, *candle);
                    }
                }
                drop(guard);

                // Stay well inside the public REST weight limit.
                tokio::time::sleep(Duration::from_millis(120)).await;
            }
            if now_ms() < banned_until {
                break; // ban hit mid-round: leave last_fetched so this boundary refetches
            }
            last_fetched.insert(tf, boundary);
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

    // ---- row parsing (the REST equivalent of the old frame tests) ------------

    // Row parsing now lives in ONE place — crate::venue — so Binance and Bybit cannot
    // drift apart. These tests exercise it through that single door.
    const TF_MS: i64 = 3_600_000;

    fn parse_one(row: serde_json::Value) -> Option<Candle> {
        let body = serde_json::Value::Array(vec![row]).to_string();
        Venue::Binance
            .parse_klines(&body, TF_MS)
            .and_then(|mut v| if v.is_empty() { None } else { Some(v.remove(0)) })
    }

    fn row(o: &str, h: &str, l: &str, c: &str, v: &str, close_time: i64) -> serde_json::Value {
        serde_json::json!([1700000000000i64, o, h, l, c, v, close_time, "0", 0, "0", "0", "0"])
    }

    #[test]
    fn parses_a_kline_row() {
        let candle = parse_one(row("100.5", "102.0", "99.0", "101.25", "1234.5", 1_700_003_599_999))
            .expect("parsed");
        assert_eq!(candle.open, 100.5);
        assert_eq!(candle.high, 102.0);
        assert_eq!(candle.low, 99.0);
        assert_eq!(candle.close, 101.25);
        assert_eq!(candle.close_time, 1_700_003_599_999);
    }

    #[test]
    fn malformed_rows_return_none_rather_than_panicking() {
        for raw in [
            serde_json::json!([]),
            serde_json::json!("not an array"),
            serde_json::json!([1, 2, 3]),
            serde_json::json!([1700000000000i64, "not-a-number", "1", "1", "1", "1", 1700003599999i64]),
        ] {
            assert_eq!(parse_one(raw.clone()), None, "should have rejected: {raw}");
        }
    }

    #[test]
    fn rejects_a_candle_with_impossible_geometry() {
        // high < low
        let bad = parse_one(row("100", "99.0", "101.0", "100", "1", 1_700_003_599_999)).unwrap();
        assert!(!candle_is_sane(&bad), "high < low was accepted");
        // non-positive close
        let bad = parse_one(row("100", "102.0", "99.0", "0.0", "1", 1_700_003_599_999)).unwrap();
        assert!(!candle_is_sane(&bad), "close <= 0 was accepted");
        // sane row passes
        let ok = parse_one(row("100", "102.0", "99.0", "101.25", "1", 1_700_003_599_999)).unwrap();
        assert!(candle_is_sane(&ok));
    }

    // ---- the boundary scheduler (the part that decides whether we poll at all) ----

    #[test]
    fn tf_millis_covers_every_timeframe() {
        // A timeframe added to TIMEFRAMES without a duration here would silently
        // never be polled — the feed equivalent of the tested-but-unwired trap.
        for &(tf, _) in TIMEFRAMES {
            assert!(tf_millis(tf).is_some(), "no duration mapping for {tf}");
        }
    }

    #[test]
    fn boundary_is_the_last_closed_bar_not_the_forming_one() {
        let tf = 300_000; // 5m — note 1_700_000_100_000 is an exact 5m boundary
        // Mid-bar: the latest CLOSED boundary is the one already behind us.
        assert_eq!(latest_closed_boundary(1_700_000_150_000, tf, 3_000), 1_700_000_100_000);
        // Exactly at the boundary, inside the settle window: still the previous bar —
        // Binance may not have finalized the new row yet.
        assert_eq!(latest_closed_boundary(1_700_000_100_000, tf, 3_000), 1_699_999_800_000);
        // Once the settle delay has passed, the new boundary is safe to fetch.
        assert_eq!(latest_closed_boundary(1_700_000_103_000, tf, 3_000), 1_700_000_100_000);
    }

    #[test]
    fn boundary_advances_once_per_bar() {
        let tf = 3_600_000; // 1h
        let b1 = latest_closed_boundary(1_700_000_000_000, tf, 3_000);
        let b2 = latest_closed_boundary(1_700_000_000_000 + tf, tf, 3_000);
        assert_eq!(b2 - b1, tf);
    }

    // ---- ban handling (the thing that keeps a rate limit from becoming a 3-day ban) --

    #[test]
    fn a_ban_with_an_expiry_is_honored_but_capped() {
        let now = 1_700_000_000_000;
        let body = r#"{"code":-1003,"msg":"Way too much request weight used; IP banned until 1700000500000."}"#;
        assert_eq!(ban_until_ms(418, body, now), Some(1_700_000_500_000));
        // A garbage far-future expiry must not silence the feed for days.
        let far = r#"{"msg":"IP banned until 1900000000000."}"#;
        assert_eq!(ban_until_ms(418, far, now), Some(now + 3_600_000));
    }

    #[test]
    fn bans_without_expiries_back_off_hard_and_rate_limits_gently() {
        let now = 1_700_000_000_000;
        assert_eq!(ban_until_ms(418, "teapot", now), Some(now + 600_000));
        assert_eq!(ban_until_ms(429, "slow down", now), Some(now + 60_000));
    }

    #[test]
    fn ordinary_statuses_are_not_bans() {
        for status in [200u16, 400, 404, 500, 503] {
            assert_eq!(ban_until_ms(status, "whatever", 0), None);
        }
    }
}
