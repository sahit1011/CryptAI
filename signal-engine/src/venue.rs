//! Where candles come from — and the fallback that keeps the plane alive.
//!
//! WHY THIS EXISTS. Public Binance data reaches us over a SHARED cloud egress IP, so
//! other tenants' request weight gets us 418-banned through no fault of our own.
//! Measured 2026-08-25: a deploy restart landed inside such a ban and the signal plane
//! was down **1h42m** — and because the pulse gate fail-closes, nobody could scan for
//! that entire window. Retrying harder is not the fix (it escalates bans), and caching
//! history is not either: a pulse carries the market data's `feed_ts`, so stale candles
//! produce pulses the staleness gate correctly rejects. The only real fix is a SECOND
//! venue.
//!
//! THE RULE THAT KEEPS IT HONEST: **a symbol's history is never mixed across venues.**
//! Bybit's prices and volumes are close to Binance's but not identical, and appending
//! foreign bars onto a Binance window would silently shift every volume- and
//! range-derived factor. So the venue is chosen ONCE at bootstrap (first one that
//! answers), used for that whole process lifetime, and stamped onto every pulse so
//! every downstream consumer — including the calibration ledger — knows which venue
//! produced the number it is about to draw conclusions from.

use crate::indicators::Candle;

/// One venue's top-of-book row: `(symbol, bid, bid_qty, ask, ask_qty)`.
pub type BookRow = (String, f64, f64, f64, f64);

/// Public-data venues, in fallback order. Binance first: it is the deepest book and
/// the venue our historical calibration was measured on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Venue {
    /// Binance's public DATA MIRROR — exists for exactly this use, same /api/v3 shapes.
    Binance,
    /// Bybit v5 linear perps. Different exchange, different egress reputation, so a
    /// Binance IP ban says nothing about whether this one answers.
    Bybit,
}

/// Tried in order at bootstrap. Extending this list is the cheap way to add resilience;
/// re-ordering it is a data-consistency decision, not a config tweak.
pub const FALLBACK_ORDER: &[Venue] = &[Venue::Binance, Venue::Bybit];

impl Venue {
    /// Stable identifier written into the pulse payload and the calibration ledger.
    pub fn name(&self) -> &'static str {
        match self {
            Venue::Binance => "binance",
            Venue::Bybit => "bybit",
        }
    }

    /// Kline endpoint for one symbol/timeframe. `tf` is OUR canonical label
    /// ("5m"/"15m"/"1h"/"4h"); each venue's dialect is translated here and nowhere else.
    pub fn kline_url(&self, symbol: &str, tf: &str, limit: usize) -> Option<String> {
        match self {
            Venue::Binance => Some(format!(
                "https://data-api.binance.vision/api/v3/klines\
                 ?symbol={symbol}&interval={tf}&limit={limit}"
            )),
            Venue::Bybit => Some(format!(
                "https://api.bybit.com/v5/market/kline\
                 ?category=linear&symbol={symbol}&interval={}&limit={limit}",
                bybit_interval(tf)?
            )),
        }
    }

    /// Parse a kline response body into bars in ASCENDING time order.
    ///
    /// `tf_ms` supplies the bar width because Bybit reports a bar's START and the
    /// engine keys everything on CLOSE time; deriving it here keeps the rest of the
    /// codebase free of per-venue timestamp conventions. Returns None when the body
    /// is not a recognisable success payload — the caller then treats it as a failed
    /// fetch rather than an empty market.
    pub fn parse_klines(&self, body: &str, tf_ms: i64) -> Option<Vec<Candle>> {
        let json: serde_json::Value = serde_json::from_str(body).ok()?;
        match self {
            Venue::Binance => {
                let rows = json.as_array()?;
                Some(rows.iter().filter_map(parse_binance_row).collect())
            }
            Venue::Bybit => {
                // Bybit signals application errors in retCode with HTTP 200, so a
                // non-zero code must not be read as "no candles".
                if json.get("retCode").and_then(|c| c.as_i64()).unwrap_or(-1) != 0 {
                    return None;
                }
                let rows = json.get("result")?.get("list")?.as_array()?;
                let mut out: Vec<Candle> = rows
                    .iter()
                    .filter_map(|r| parse_bybit_row(r, tf_ms))
                    .collect();
                // Bybit returns NEWEST FIRST. Everything downstream — the sanity gate,
                // the boundary logic, every indicator window — assumes ascending time.
                out.reverse();
                Some(out)
            }
        }
    }

    /// Top-of-book endpoint for ONE symbol.
    ///
    /// Binance can batch every symbol into one round trip; Bybit's orderbook endpoint
    /// is per-symbol. The poller therefore asks for a batch URL first and falls back to
    /// per-symbol calls — a handful of extra requests on a 5s cadence is trivially
    /// inside any budget, and it is the difference between a working spread veto and
    /// every symbol reading tradability 0.
    pub fn book_url_single(&self, symbol: &str) -> Option<String> {
        match self {
            Venue::Binance => Some(format!(
                "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol={symbol}"
            )),
            Venue::Bybit => Some(format!(
                "https://api.bybit.com/v5/market/orderbook?category=linear&symbol={symbol}&limit=1"
            )),
        }
    }

    /// Batch top-of-book URL, when the venue supports one. `None` -> use
    /// `book_url_single` per symbol.
    pub fn book_url_batch(&self, symbols_param: &str) -> Option<String> {
        match self {
            Venue::Binance => Some(format!(
                "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbols={symbols_param}"
            )),
            Venue::Bybit => None,
        }
    }

    /// Parse a top-of-book body into `(symbol, bid, bid_qty, ask, ask_qty)` rows.
    ///
    /// Returns None for an unrecognisable payload so the caller treats it as a failed
    /// fetch — never as "the book is empty", which would read as a zero spread.
    pub fn parse_book(&self, body: &str) -> Option<Vec<BookRow>> {
        let json: serde_json::Value = serde_json::from_str(body).ok()?;
        match self {
            Venue::Binance => {
                // One symbol answers with an object, several with an array.
                let rows: Vec<&serde_json::Value> = match json.as_array() {
                    Some(a) => a.iter().collect(),
                    None => vec![&json],
                };
                let mut out: Vec<BookRow> = Vec::new();
                for r in rows {
                    let symbol = r.get("symbol")?.as_str()?.to_uppercase();
                    out.push((
                        symbol,
                        num(r.get("bidPrice"))?,
                        num(r.get("bidQty")).unwrap_or(0.0),
                        num(r.get("askPrice"))?,
                        num(r.get("askQty")).unwrap_or(0.0),
                    ));
                }
                Some(out)
            }
            Venue::Bybit => {
                if json.get("retCode").and_then(|c| c.as_i64()).unwrap_or(-1) != 0 {
                    return None;
                }
                let result = json.get("result")?;
                let symbol = result.get("s")?.as_str()?.to_uppercase();
                // b / a are [[price, size], ...], best first.
                let bid = result.get("b")?.as_array()?.first()?.as_array()?;
                let ask = result.get("a")?.as_array()?.first()?.as_array()?;
                Some(vec![(
                    symbol,
                    num(bid.first())?,
                    num(bid.get(1)).unwrap_or(0.0),
                    num(ask.first())?,
                    num(ask.get(1)).unwrap_or(0.0),
                )])
            }
        }
    }

    /// Whether an HTTP status from this venue means "stop sending requests".
    /// Bybit uses 403 for IP rate limiting where Binance uses 418.
    pub fn is_rate_limit(&self, status: u16) -> bool {
        match self {
            Venue::Binance => status == 418 || status == 429,
            Venue::Bybit => status == 403 || status == 429,
        }
    }
}

/// Our timeframe label -> Bybit's `interval` (minutes as a string).
fn bybit_interval(tf: &str) -> Option<&'static str> {
    Some(match tf {
        "1m" => "1",
        "5m" => "5",
        "15m" => "15",
        "1h" => "60",
        "4h" => "240",
        "1d" => "D",
        _ => return None,
    })
}

fn num(v: Option<&serde_json::Value>) -> Option<f64> {
    let v = v?;
    // Both venues quote numbers as strings; tolerate a real number too.
    v.as_str()
        .and_then(|s| s.parse::<f64>().ok())
        .or_else(|| v.as_f64())
        .filter(|f| f.is_finite())
}

/// Binance: [openTime, o, h, l, c, v, closeTime, ...]
fn parse_binance_row(row: &serde_json::Value) -> Option<Candle> {
    let arr = row.as_array()?;
    Some(Candle {
        open: num(arr.get(1))?,
        high: num(arr.get(2))?,
        low: num(arr.get(3))?,
        close: num(arr.get(4))?,
        volume: num(arr.get(5)).unwrap_or(0.0),
        close_time: arr.get(6)?.as_i64()?,
    })
}

/// Bybit: [startTime, o, h, l, c, volume, turnover] — all strings, newest first.
/// close_time follows Binance's convention (last millisecond of the bar) so the two
/// venues' bars are directly comparable and the boundary logic needs no special case.
fn parse_bybit_row(row: &serde_json::Value, tf_ms: i64) -> Option<Candle> {
    let arr = row.as_array()?;
    let start = num(arr.first())? as i64;
    Some(Candle {
        open: num(arr.get(1))?,
        high: num(arr.get(2))?,
        low: num(arr.get(3))?,
        close: num(arr.get(4))?,
        volume: num(arr.get(5)).unwrap_or(0.0),
        close_time: start + tf_ms - 1,
    })
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    const H1_MS: i64 = 3_600_000;

    #[test]
    fn names_are_stable_identifiers() {
        // These strings land in the pulse payload and pulse_snapshots.venue; renaming
        // one silently re-labels historical calibration data.
        assert_eq!(Venue::Binance.name(), "binance");
        assert_eq!(Venue::Bybit.name(), "bybit");
    }

    #[test]
    fn binance_is_tried_before_bybit() {
        assert_eq!(FALLBACK_ORDER, &[Venue::Binance, Venue::Bybit]);
    }

    #[test]
    fn bybit_url_translates_our_timeframe_dialect() {
        let url = Venue::Bybit.kline_url("BTCUSDT", "4h", 500).unwrap();
        assert!(url.contains("interval=240"), "{url}");
        assert!(url.contains("category=linear"), "{url}");
        assert!(Venue::Bybit.kline_url("BTCUSDT", "7m", 500).is_none());
    }

    #[test]
    fn binance_rows_parse_ascending() {
        let body = r#"[
            ["1700000000000","100.0","110.0","90.0","105.0","12.5",1700003599999,"0",1,"0","0","0"],
            ["1700003600000","105.0","115.0","95.0","110.0","13.5",1700007199999,"0",1,"0","0","0"]
        ]"#;
        let out = Venue::Binance.parse_klines(body, H1_MS).unwrap();
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].close, 105.0);
        assert_eq!(out[1].close, 110.0);
        assert!(out[0].close_time < out[1].close_time);
    }

    #[test]
    fn bybit_rows_are_reversed_into_ascending_order() {
        // As Bybit sends it: NEWEST FIRST.
        let body = r#"{"retCode":0,"retMsg":"OK","result":{"symbol":"BTCUSDT","list":[
            ["1700003600000","105.0","115.0","95.0","110.0","13.5","1400"],
            ["1700000000000","100.0","110.0","90.0","105.0","12.5","1300"]
        ]}}"#;
        let out = Venue::Bybit.parse_klines(body, H1_MS).unwrap();
        assert_eq!(out.len(), 2);
        assert_eq!(out[0].close, 105.0, "oldest bar must come first");
        assert_eq!(out[1].close, 110.0);
        assert!(out[0].close_time < out[1].close_time);
    }

    #[test]
    fn bybit_close_time_matches_binance_convention() {
        let body = r#"{"retCode":0,"result":{"list":[
            ["1700000000000","100.0","110.0","90.0","105.0","12.5","1300"]
        ]}}"#;
        let out = Venue::Bybit.parse_klines(body, H1_MS).unwrap();
        // Binance would report 1700003599999 for the same bar.
        assert_eq!(out[0].close_time, 1_700_000_000_000 + H1_MS - 1);
    }

    #[test]
    fn bybit_application_error_is_not_an_empty_market() {
        // HTTP 200 with a non-zero retCode. Reading this as "zero candles" would look
        // like a calm market instead of a failed fetch.
        let body = r#"{"retCode":10006,"retMsg":"Too many visits","result":{}}"#;
        assert!(Venue::Bybit.parse_klines(body, H1_MS).is_none());
    }

    #[test]
    fn garbage_bodies_never_parse_as_candles() {
        for venue in FALLBACK_ORDER {
            assert!(venue.parse_klines("not json", H1_MS).is_none());
            assert!(venue.parse_klines("{}", H1_MS).is_none());
        }
    }

    #[test]
    fn binance_book_batches_and_bybit_does_not() {
        // Binance answers every symbol in one round trip; Bybit is per-symbol. The
        // poller relies on this distinction to pick its request shape.
        assert!(Venue::Binance.book_url_batch("[\"BTCUSDT\"]").is_some());
        assert!(Venue::Bybit.book_url_batch("[\"BTCUSDT\"]").is_none());
        assert!(Venue::Bybit.book_url_single("BTCUSDT").unwrap().contains("orderbook"));
    }

    #[test]
    fn binance_book_parses_both_single_object_and_array() {
        let one = r#"{"symbol":"BTCUSDT","bidPrice":"64000.1","bidQty":"1.5","askPrice":"64000.5","askQty":"2.0"}"#;
        let rows = Venue::Binance.parse_book(one).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0], ("BTCUSDT".to_string(), 64000.1, 1.5, 64000.5, 2.0));

        let many = r#"[{"symbol":"BTCUSDT","bidPrice":"1","bidQty":"1","askPrice":"2","askQty":"1"},
                       {"symbol":"ETHUSDT","bidPrice":"3","bidQty":"1","askPrice":"4","askQty":"1"}]"#;
        assert_eq!(Venue::Binance.parse_book(many).unwrap().len(), 2);
    }

    #[test]
    fn bybit_book_parses_best_bid_and_ask() {
        let body = r#"{"retCode":0,"result":{"s":"BTCUSDT",
            "b":[["64000.1","1.5"],["63999.0","2.0"]],
            "a":[["64000.5","2.0"],["64001.0","3.0"]]}}"#;
        let rows = Venue::Bybit.parse_book(body).unwrap();
        assert_eq!(rows.len(), 1);
        // BEST bid/ask only — taking a deeper level would overstate the spread.
        assert_eq!(rows[0], ("BTCUSDT".to_string(), 64000.1, 1.5, 64000.5, 2.0));
    }

    #[test]
    fn an_unparseable_book_is_a_failed_fetch_not_a_zero_spread() {
        // A zero/absent book read as real would produce a nonsense spread, and spread
        // drives the veto that decides whether anyone can trade at all.
        for v in FALLBACK_ORDER {
            assert!(v.parse_book("not json").is_none());
        }
        assert!(Venue::Bybit.parse_book(r#"{"retCode":10006,"result":{}}"#).is_none());
        assert!(Venue::Bybit.parse_book(r#"{"retCode":0,"result":{"s":"X","b":[],"a":[]}}"#).is_none());
        assert!(Venue::Binance.parse_book(r#"{"symbol":"X"}"#).is_none());
    }

    #[test]
    fn rate_limit_statuses_are_per_venue() {
        assert!(Venue::Binance.is_rate_limit(418));
        assert!(Venue::Binance.is_rate_limit(429));
        assert!(!Venue::Binance.is_rate_limit(403));
        // Bybit rate-limits with 403, which is NOT a ban signal on Binance.
        assert!(Venue::Bybit.is_rate_limit(403));
        assert!(Venue::Bybit.is_rate_limit(429));
        assert!(!Venue::Bybit.is_rate_limit(418));
    }

    #[test]
    fn malformed_rows_are_skipped_not_defaulted() {
        let body = r#"[
            ["1700000000000","100.0","110.0","90.0","105.0","12.5",1700003599999],
            ["1700003600000","oops","115.0","95.0","110.0","13.5",1700007199999]
        ]"#;
        let out = Venue::Binance.parse_klines(body, H1_MS).unwrap();
        assert_eq!(out.len(), 1, "a bad row must vanish, not become zeros");
    }
}

#[cfg(test)]
mod fallback_contract {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;
    use crate::feature_store::FeatureStore;

    const H1_MS: i64 = 3_600_000;

    /// The rule the whole fallback rests on: a symbol's window must never contain two
    /// venues' bars. Bybit's volumes and prices are close to Binance's but not equal,
    /// so an interleaved window silently shifts every volume- and range-derived factor
    /// while looking perfectly healthy. bootstrap_history clears before each attempt;
    /// this pins the primitive that makes that possible.
    #[test]
    fn clearing_a_symbol_drops_history_and_its_freshness_claim() {
        let mut store = FeatureStore::default();
        let state = store.entry("BTCUSDT");

        let binance = Venue::Binance
            .parse_klines(
                r#"[["1700000000000","100.0","110.0","90.0","105.0","12.5",1700003599999]]"#,
                H1_MS,
            )
            .unwrap();
        for c in &binance {
            state.push_candle("1h", *c);
        }
        assert_eq!(state.candles_for("1h").len(), 1);
        assert!(state.last_event_ts > 0, "pushing a bar should stamp freshness");

        state.clear_candles();
        assert!(state.candles_for("1h").is_empty(), "history must be gone");
        assert_eq!(
            state.last_event_ts, 0,
            "a cleared symbol must not keep claiming the freshness of data it no longer has"
        );

        // A fallback venue's bars then load into a clean window, not on top.
        let bybit = Venue::Bybit
            .parse_klines(
                r#"{"retCode":0,"result":{"list":[["1700000000000","100.0","110.0","90.0","105.0","12.5","1300"]]}}"#,
                H1_MS,
            )
            .unwrap();
        for c in &bybit {
            state.push_candle("1h", *c);
        }
        assert_eq!(state.candles_for("1h").len(), 1, "exactly one venue's bar");
    }

    /// Both venues must agree on a bar's identity, or the same bar would be stored
    /// twice (push_candle dedupes on close_time) and every window would drift.
    #[test]
    fn the_two_venues_agree_on_close_time_for_the_same_bar() {
        let binance = Venue::Binance
            .parse_klines(
                r#"[["1700000000000","100.0","110.0","90.0","105.0","12.5",1700003599999]]"#,
                H1_MS,
            )
            .unwrap();
        let bybit = Venue::Bybit
            .parse_klines(
                r#"{"retCode":0,"result":{"list":[["1700000000000","100.0","110.0","90.0","105.0","12.5","1300"]]}}"#,
                H1_MS,
            )
            .unwrap();
        assert_eq!(binance[0].close_time, bybit[0].close_time);
    }
}
