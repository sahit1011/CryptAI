//! Rolling market state per symbol.
//!
//! Bounded by construction: every series is a ring buffer with a fixed capacity, so a
//! process that runs for months uses the same memory as one that just started. An
//! unbounded `Vec` here would be a slow leak in a service designed to never restart.
//!
//! Holds no `user_id` and never will — this is shared-plane state (see
//! `docs/MULTI_TENANCY.md`).

use std::collections::{HashMap, VecDeque};

use crate::indicators::Candle;

/// Bars retained per timeframe. Must exceed the largest lookback any factor needs
/// (`vol_percentile_window` = 200 plus the ATR period) with room to spare, or the
/// volatility percentile silently narrows its own distribution.
pub const CAPACITY: usize = 600;

/// Timeframes ingested, ascending. The weight is that timeframe's vote in the
/// multi-timeframe trend calculation — higher timeframes carry more.
pub const TIMEFRAMES: &[(&str, f64)] = &[("5m", 1.0), ("15m", 1.5), ("1h", 2.0), ("4h", 3.0)];

/// Top-of-book snapshot from the bookTicker stream.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct BookTop {
    pub bid: f64,
    pub ask: f64,
    pub bid_qty: f64,
    pub ask_qty: f64,
    pub ts: i64,
}

impl BookTop {
    /// Spread in basis points of the mid. Returns `None` for a crossed or empty book
    /// rather than a negative or infinite spread.
    pub fn spread_bps(&self) -> Option<f64> {
        if self.bid <= 0.0 || self.ask <= 0.0 || self.ask < self.bid {
            return None;
        }
        let mid = (self.bid + self.ask) / 2.0;
        (mid > 0.0).then(|| (self.ask - self.bid) / mid * 10_000.0)
    }

    /// Notional resting at the touch, both sides. A crude depth proxy — the real depth
    /// factor wants several levels, which needs the depth stream rather than bookTicker.
    pub fn touch_notional(&self) -> f64 {
        self.bid * self.bid_qty + self.ask * self.ask_qty
    }

    /// Order-book imbalance in `-1.0..=1.0`: positive when bids dominate.
    ///
    /// Genuinely orthogonal to every price-derived factor — it measures resting
    /// intent rather than realised price. Not yet wired into scoring; recorded so the
    /// calibration job can measure it before it is trusted.
    pub fn imbalance(&self) -> Option<f64> {
        let total = self.bid_qty + self.ask_qty;
        (total > 0.0).then(|| ((self.bid_qty - self.ask_qty) / total).clamp(-1.0, 1.0))
    }
}

/// Perpetual-specific state, from the mark-price stream and the open-interest endpoint.
#[derive(Debug, Clone, Copy, Default)]
pub struct PerpState {
    pub funding_rate: f64,
    pub open_interest: f64,
    /// Open interest one hour ago, for the delta. `None` until an hour of history exists.
    pub open_interest_1h_ago: Option<f64>,
    pub ts: i64,
}

impl PerpState {
    /// Fractional change in open interest over the last hour.
    pub fn oi_delta_1h(&self) -> f64 {
        match self.open_interest_1h_ago {
            Some(prev) if prev > 0.0 => (self.open_interest - prev) / prev,
            _ => 0.0,
        }
    }
}

/// How much open-interest history to retain, as (timestamp, value) samples. At the
/// 60s poll cadence this covers ~2 hours, enough to always find a sample an hour back.
pub const OI_HISTORY: usize = 128;

/// Everything known about one symbol.
#[derive(Debug, Default)]
pub struct SymbolState {
    /// Closed candles per timeframe label, oldest first.
    pub candles: HashMap<String, VecDeque<Candle>>,
    pub book: BookTop,
    pub perp: PerpState,
    /// (timestamp_ms, open_interest) samples, oldest first.
    pub oi_history: VecDeque<(i64, f64)>,
    /// Timestamp of the newest market event of any kind. This is what a pulse publishes
    /// as `feed_ts`, and therefore what every staleness check keys off.
    ///
    /// Must only ever be advanced by events that have actually HAPPENED. Seeding it from
    /// a bar that has not closed yet puts it in the future and makes every staleness
    /// check pass forever.
    pub last_event_ts: i64,
}

impl SymbolState {
    /// Append a CLOSED candle, evicting the oldest beyond capacity.
    ///
    /// Re-emission of the same bar is idempotent: Binance sends a final update per bar,
    /// but a reconnect can replay it, and appending twice would corrupt every window.
    pub fn push_candle(&mut self, timeframe: &str, candle: Candle) {
        let buf = self
            .candles
            .entry(timeframe.to_string())
            .or_insert_with(|| VecDeque::with_capacity(CAPACITY));

        match buf.back() {
            // Same bar replayed — overwrite rather than append.
            Some(last) if last.close_time == candle.close_time => {
                if let Some(slot) = buf.back_mut() {
                    *slot = candle;
                }
            }
            // Out-of-order or stale bar: ignore. Inserting it would break the ordering
            // every windowed indicator assumes.
            Some(last) if last.close_time > candle.close_time => return,
            _ => {
                if buf.len() >= CAPACITY {
                    buf.pop_front();
                }
                buf.push_back(candle);
            }
        }

        self.last_event_ts = self.last_event_ts.max(candle.close_time);
    }

    pub fn candles_for(&self, timeframe: &str) -> Vec<Candle> {
        self.candles
            .get(timeframe)
            .map(|b| b.iter().copied().collect())
            .unwrap_or_default()
    }

    /// Record an open-interest sample and refresh the one-hour-ago reference.
    ///
    /// Picks the newest sample at least an hour old rather than assuming a fixed number
    /// of samples back — the poller can miss ticks during an outage, and counting
    /// samples would then silently compare against the wrong horizon.
    pub fn push_open_interest(&mut self, ts: i64, value: f64) {
        if !value.is_finite() || value < 0.0 {
            return;
        }
        if self.oi_history.len() >= OI_HISTORY {
            self.oi_history.pop_front();
        }
        self.oi_history.push_back((ts, value));

        let cutoff = ts - 3_600_000;
        self.perp.open_interest = value;
        self.perp.open_interest_1h_ago = self
            .oi_history
            .iter()
            .filter(|(t, _)| *t <= cutoff)
            .last()
            .map(|(_, v)| *v);
        self.perp.ts = ts;
        self.last_event_ts = self.last_event_ts.max(ts);
    }

    /// Whether every configured timeframe has enough history to score honestly.
    pub fn is_warm(&self, min_bars: usize) -> bool {
        TIMEFRAMES.iter().all(|(tf, _)| {
            self.candles
                .get(*tf)
                .map(|b| b.len() >= min_bars)
                .unwrap_or(false)
        })
    }
}

/// All symbols. Guarded by a single lock at the call site rather than per-symbol locks —
/// updates are short and the write rate is bounded by the feed, not by user count.
#[derive(Debug, Default)]
pub struct FeatureStore {
    pub symbols: HashMap<String, SymbolState>,
}

impl FeatureStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn entry(&mut self, symbol: &str) -> &mut SymbolState {
        self.symbols.entry(symbol.to_uppercase()).or_default()
    }

    pub fn get(&self, symbol: &str) -> Option<&SymbolState> {
        self.symbols.get(&symbol.to_uppercase())
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn candle_at(close_time: i64, close: f64) -> Candle {
        Candle {
            open: close,
            high: close + 1.0,
            low: close - 1.0,
            close,
            volume: 1.0,
            close_time,
        }
    }

    #[test]
    fn ring_buffer_is_bounded() {
        let mut s = SymbolState::default();
        for i in 0..(CAPACITY as i64 * 3) {
            s.push_candle("1h", candle_at(i * 1000, i as f64));
        }
        assert_eq!(
            s.candles_for("1h").len(),
            CAPACITY,
            "buffer grew past capacity"
        );
    }

    #[test]
    fn oldest_bars_are_evicted_not_newest() {
        let mut s = SymbolState::default();
        for i in 0..(CAPACITY as i64 + 10) {
            s.push_candle("1h", candle_at(i * 1000, i as f64));
        }
        let got = s.candles_for("1h");
        assert_eq!(got.last().map(|c| c.close), Some((CAPACITY as f64) + 9.0));
    }

    #[test]
    fn replaying_the_same_bar_overwrites_instead_of_duplicating() {
        // A reconnect can replay the final update for a bar. Appending it twice would
        // corrupt every windowed indicator downstream.
        let mut s = SymbolState::default();
        s.push_candle("1h", candle_at(1000, 100.0));
        s.push_candle("1h", candle_at(1000, 105.0));
        let got = s.candles_for("1h");
        assert_eq!(got.len(), 1, "duplicate bar appended");
        assert_eq!(
            got.first().map(|c| c.close),
            Some(105.0),
            "replay did not update"
        );
    }

    #[test]
    fn out_of_order_bars_are_dropped() {
        let mut s = SymbolState::default();
        s.push_candle("1h", candle_at(2000, 100.0));
        s.push_candle("1h", candle_at(1000, 999.0)); // older, arrives late
        let got = s.candles_for("1h");
        assert_eq!(got.len(), 1);
        assert_eq!(got.first().map(|c| c.close), Some(100.0));
    }

    #[test]
    fn last_event_ts_never_goes_backwards() {
        let mut s = SymbolState::default();
        s.push_candle("1h", candle_at(5000, 1.0));
        s.push_candle("1h", candle_at(1000, 1.0)); // dropped
        assert_eq!(s.last_event_ts, 5000);
    }

    #[test]
    fn spread_rejects_a_crossed_or_empty_book() {
        assert_eq!(BookTop::default().spread_bps(), None);
        let crossed = BookTop {
            bid: 101.0,
            ask: 100.0,
            ..Default::default()
        };
        assert_eq!(crossed.spread_bps(), None, "crossed book produced a spread");
    }

    #[test]
    fn spread_is_in_basis_points_of_mid() {
        let b = BookTop {
            bid: 99.99,
            ask: 100.01,
            ..Default::default()
        };
        let bps = b.spread_bps().expect("valid");
        assert!((bps - 2.0).abs() < 1e-6, "got {bps}");
    }

    #[test]
    fn book_imbalance_is_signed_and_bounded() {
        let bid_heavy = BookTop {
            bid: 100.0,
            ask: 100.1,
            bid_qty: 30.0,
            ask_qty: 10.0,
            ts: 0,
        };
        let v = bid_heavy.imbalance().expect("valid");
        assert!(v > 0.0 && v <= 1.0, "got {v}");
        assert_eq!(
            BookTop::default().imbalance(),
            None,
            "empty book has no imbalance"
        );
    }

    #[test]
    fn oi_delta_is_zero_without_history_rather_than_a_guess() {
        let p = PerpState {
            open_interest: 1000.0,
            open_interest_1h_ago: None,
            ..Default::default()
        };
        assert_eq!(p.oi_delta_1h(), 0.0);
    }

    #[test]
    fn oi_delta_is_fractional() {
        let p = PerpState {
            open_interest: 1100.0,
            open_interest_1h_ago: Some(1000.0),
            ..Default::default()
        };
        assert!((p.oi_delta_1h() - 0.1).abs() < 1e-9);
    }

    #[test]
    fn warm_requires_every_timeframe_not_just_one() {
        let mut s = SymbolState::default();
        for i in 0..100 {
            s.push_candle("1h", candle_at(i * 1000, 1.0));
        }
        assert!(!s.is_warm(50), "warm with only one timeframe populated");
        for (tf, _) in TIMEFRAMES {
            for i in 0..100 {
                s.push_candle(tf, candle_at(i * 1000, 1.0));
            }
        }
        assert!(s.is_warm(50));
    }

    #[test]
    fn last_event_ts_must_never_be_in_the_future() {
        // Regression, found against live data 2026-08-02: bootstrap pushed the
        // still-forming bar (whose close_time is in the future) to set up the buffer,
        // then popped it — but last_event_ts kept the future timestamp. feed_ts then led
        // wall clock by 1.8 hours, so every staleness check passed forever and a dead
        // feed would have looked eternally fresh. Only CLOSED bars may advance it.
        let now = 1_700_000_000_000i64;
        let mut s = SymbolState::default();
        let closed = candle_at(now - 3_600_000, 100.0);
        s.push_candle("1h", closed);
        assert!(
            s.last_event_ts <= now,
            "last_event_ts {} is ahead of now {now}",
            s.last_event_ts
        );
    }

    #[test]
    fn oi_reference_is_chosen_by_age_not_by_sample_count() {
        // The poller can miss ticks during an outage. Counting samples back would then
        // compare against the wrong horizon and silently misreport the delta.
        let mut s = SymbolState::default();
        let t0 = 1_700_000_000_000i64;
        s.push_open_interest(t0, 1000.0);
        // A gap: no samples for 40 minutes.
        s.push_open_interest(t0 + 2_400_000, 1050.0);
        s.push_open_interest(t0 + 3_700_000, 1100.0); // just over an hour after t0

        assert_eq!(s.perp.open_interest_1h_ago, Some(1000.0));
        assert!((s.perp.oi_delta_1h() - 0.1).abs() < 1e-9);
    }

    #[test]
    fn oi_history_is_bounded_and_rejects_garbage() {
        let mut s = SymbolState::default();
        for i in 0..(OI_HISTORY as i64 * 3) {
            s.push_open_interest(i * 60_000, 1000.0 + i as f64);
        }
        assert_eq!(s.oi_history.len(), OI_HISTORY);

        let before = s.oi_history.len();
        s.push_open_interest(9_999_999, f64::NAN);
        s.push_open_interest(9_999_999, -5.0);
        assert_eq!(s.oi_history.len(), before, "garbage OI sample was recorded");
    }

    #[test]
    fn oi_delta_is_zero_until_an_hour_of_history_exists() {
        let mut s = SymbolState::default();
        let t0 = 1_700_000_000_000i64;
        s.push_open_interest(t0, 1000.0);
        s.push_open_interest(t0 + 60_000, 2000.0);
        // Doubling in a minute must not be reported as a 100% hourly delta.
        assert_eq!(s.perp.oi_delta_1h(), 0.0);
    }

    #[test]
    fn symbols_are_keyed_case_insensitively() {
        let mut store = FeatureStore::new();
        store.entry("btcusdt").last_event_ts = 42;
        assert_eq!(store.get("BTCUSDT").map(|s| s.last_event_ts), Some(42));
    }
}
