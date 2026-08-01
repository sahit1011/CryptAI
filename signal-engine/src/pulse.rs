//! The pulse contract — the ONLY interface between the shared signal plane and the
//! per-user reasoning plane.
//!
//! Mirrors `docs/MULTI_TENANCY.md` exactly. Two rules govern everything here:
//!
//! 1. **A pulse carries facts and scores, never a trade decision.** There is no entry,
//!    stop, or target field, and there must never be one. That absence is what keeps
//!    setup synthesis per-user; the moment the shared plane emits a trade, every user
//!    gets the same one and the personalisation layer becomes a filter.
//! 2. **A non-empty veto list forces `tradability` to 0.** Enforced in
//!    [`Pulse::new`], not left to the caller to remember.
//!
//! `SCHEMA_VERSION` is bumped on any breaking field change. Consumers reject unknown
//! major versions rather than best-effort parsing a shape they do not understand.

use serde::{Deserialize, Serialize};

/// Bump on any breaking change to the wire shape.
pub const SCHEMA_VERSION: u32 = 1;

/// How the market is behaving. A property of the market, identical for every tenant.
///
/// # This is a DESCRIPTION, not a recommendation
///
/// `TrendingUp` does not mean "go long". Out-of-sample validation on six instruments
/// never used while building the classifier found **no directional edge**: mean IC
/// improvement −0.008, paired t −0.40, 3 of 6 improved. The in-sample result that
/// motivated the variance-ratio work (+0.111 and +0.139 on BTC and XAUT) did not
/// replicate anywhere. See `eval/FINDINGS.md`.
///
/// The label is retained because it describes measurable market behaviour, and the
/// per-user reasoning plane can legitimately use "this market is statistically
/// mean-reverting" to choose a strategy. Any consumer that maps this enum straight to a
/// trade direction is asserting an edge that has been tested and not found.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Regime {
    TrendingUp,
    TrendingDown,
    Ranging,
    VolatileChop,
    /// Statistically mean-reverting: the variance ratio is below 1, so moves tend to be
    /// given back rather than extended.
    ///
    /// Added 2026-08-02 after backtesting showed the EMA-stack classifier was
    /// systematically wrong-signed on both BTC and XAUT (regime IC -0.22, t -2.41 on
    /// gold at 24h). The variance ratio had already diagnosed it — VR medians of 0.978
    /// and 0.943, both mean-reverting — but nothing consumed that diagnosis. A
    /// trend-following label in a reverting market is worse than no label.
    MeanReverting,
}

/// A hard gate. Any veto present means "do not deploy risk here right now", regardless
/// of how good the weighted factors look.
///
/// These exist because a weighted sum can always be dragged positive by a few strong
/// components — a beautiful trend structure printed on a blown-out spread is still
/// untradeable. Vetoes are not weighted; they are absolute.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Veto {
    /// Bid/ask spread wider than the venue's normal band — slippage eats the edge.
    SpreadTooWide,
    /// Order book too thin to absorb a normal position without moving price.
    InsufficientDepth,
    /// Market data older than the staleness threshold. Never score stale facts.
    StaleFeed,
    /// Funding at an extreme: a crowded trade, and prime liquidation-hunt territory.
    FundingExtreme,
    /// Not enough history to compute the factors honestly.
    InsufficientHistory,
}

impl Veto {
    /// Short human-readable reason, for the agent feed and for debugging a zero score.
    pub fn reason(&self) -> &'static str {
        match self {
            Veto::SpreadTooWide => "spread wider than the tradable band",
            Veto::InsufficientDepth => "order book too thin to absorb a position",
            Veto::StaleFeed => "market data is stale",
            Veto::FundingExtreme => "funding at an extreme — crowded trade",
            Veto::InsufficientHistory => "not enough history to score honestly",
        }
    }
}

/// The weighted components of the tradability score, each normalised to `0.0..=1.0`.
///
/// Published alongside the score so a number is always explainable — both to the user
/// ("why is it 34?") and to the calibration job, which needs per-factor values to work
/// out which components actually carry predictive weight.
///
/// These are deliberately chosen to measure *different* things. Six indicators that all
/// measure trend are one signal, not six; weighting by indicator count rather than by
/// independent information is the confluence-inflation bug this design exists to avoid.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Factors {
    /// Agreement of the EMA stack across timeframes. Direction-agnostic: a clean
    /// downtrend scores as highly as a clean uptrend.
    pub trend_alignment: f64,
    /// ATR percentile against its own recent distribution, scored as a HUMP — too
    /// quiet means no movement to capture, too wild means stop-hunt territory. This is
    /// the one factor that is not monotonic, and treating it as monotonic is the most
    /// common way a volatility term makes a scorer worse.
    pub volatility_band: f64,
    /// Kaufman Efficiency Ratio: net directional travel divided by total path length.
    /// The single best trend-versus-noise discriminator, and it directly penalises chop.
    pub efficiency_ratio: f64,
    /// Session liquidity, deterministic from the clock. London-NY overlap scores high,
    /// the dead hours score low.
    pub liquidity_window: f64,
    /// Funding plus open-interest crowding. Low when positioning is one-sided.
    pub positioning: f64,
    /// Spread and depth quality. Distinct from the veto: the veto is the cliff, this is
    /// the gradient approaching it.
    pub book_quality: f64,
}

/// Objective market structure. Pure geometry of the chart — a fair value gap is a fair
/// value gap regardless of who is looking at it, which is why this is shared-plane data.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Structure {
    pub htf_bias: Option<String>,
    pub swing_high: Option<f64>,
    pub swing_low: Option<f64>,
    pub order_blocks: Vec<Level>,
    pub fvgs: Vec<Level>,
    pub liquidity_pools: Vec<Level>,
    pub key_levels: Vec<Level>,
}

/// A price zone with provenance. `high == low` for a single level.
///
/// `timeframe` is an owned `String` rather than `&'static str` so the type can round-trip
/// through `Deserialize` — the Python side and the calibration job both read pulses back.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Level {
    pub low: f64,
    pub high: f64,
    /// Which timeframe produced it, e.g. "1h". Callers rank by this.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeframe: Option<String>,
}

/// Raw measured context. Published so the per-user plane and the calibration job can
/// reason about the inputs without recomputing them.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
pub struct Context {
    pub atr_pct: f64,
    pub atr_percentile_30d: f64,
    pub funding_rate: f64,
    pub oi_delta_1h: f64,
    pub spread_bps: f64,
    pub btc_correlation_30d: f64,
}

/// One symbol's market pulse. Published to `market:pulse:{symbol}`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Pulse {
    /// Schema version. Consumers reject what they do not recognise.
    pub v: u32,
    pub symbol: String,
    /// When this pulse was computed (epoch millis).
    pub ts: i64,
    /// Timestamp of the newest market event it incorporates (epoch millis). Consumers
    /// check this, not `ts`, to decide staleness — a pulse recomputed on schedule from
    /// a dead feed has a fresh `ts` and stale facts.
    pub feed_ts: i64,
    pub regime: Regime,
    /// 0..=100. Zero whenever `vetoes` is non-empty.
    pub tradability: u8,
    pub vetoes: Vec<Veto>,
    pub factors: Factors,
    pub structure: Structure,
    pub context: Context,
    /// Price at `feed_ts`. Persisted with the snapshot so forward returns can be
    /// computed later — without it the score is unfalsifiable.
    pub reference_price: f64,
}

impl Pulse {
    /// Build a pulse, enforcing the veto invariant.
    ///
    /// `tradability` is clamped to `0..=100` and forced to 0 when any veto is present,
    /// so a caller cannot publish "vetoed but tradable" no matter what it passes.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        symbol: impl Into<String>,
        ts: i64,
        feed_ts: i64,
        regime: Regime,
        raw_tradability: f64,
        vetoes: Vec<Veto>,
        factors: Factors,
        structure: Structure,
        context: Context,
        reference_price: f64,
    ) -> Self {
        let tradability = if vetoes.is_empty() {
            raw_tradability.clamp(0.0, 100.0).round() as u8
        } else {
            0
        };

        Self {
            v: SCHEMA_VERSION,
            symbol: symbol.into(),
            ts,
            feed_ts,
            regime,
            tradability,
            vetoes,
            factors,
            structure,
            context,
            reference_price,
        }
    }

    /// Age of the underlying market data at `now`, in milliseconds. Never negative.
    ///
    /// Clamped at zero because the exchange's clock and ours are different clocks: a few
    /// milliseconds of skew routinely puts `feed_ts` ahead of local `now`. A negative
    /// age is nonsense, and letting it propagate would let a badly skewed clock make
    /// arbitrarily stale data look arbitrarily fresh.
    pub fn feed_age_ms(&self, now: i64) -> i64 {
        now.saturating_sub(self.feed_ts).max(0)
    }

    /// Fail-closed staleness check. The shared plane is a single point of failure for
    /// every tenant, so consumers refuse to run rather than trade on stale facts.
    pub fn is_stale(&self, now: i64, max_age_ms: i64) -> bool {
        self.feed_age_ms(now) > max_age_ms
    }

    /// Whether a consumer on this schema version can safely read this pulse.
    pub fn is_compatible(&self) -> bool {
        self.v == SCHEMA_VERSION
    }
}

#[cfg(test)]
mod tests {
    // The crate denies these because a panic in the signal plane takes down every
    // tenant's data source. In tests a panic IS the failure report, so they are allowed
    // here and nowhere else.
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

    use super::*;

    fn factors() -> Factors {
        Factors {
            trend_alignment: 0.8,
            volatility_band: 0.6,
            efficiency_ratio: 0.5,
            liquidity_window: 1.0,
            positioning: 0.4,
            book_quality: 0.9,
        }
    }

    fn pulse_with(vetoes: Vec<Veto>, raw: f64) -> Pulse {
        Pulse::new(
            "BTCUSDT",
            1_754_092_800_000,
            1_754_092_799_850,
            Regime::TrendingUp,
            raw,
            vetoes,
            factors(),
            Structure::default(),
            Context::default(),
            67_000.0,
        )
    }

    #[test]
    fn a_veto_forces_tradability_to_zero() {
        let p = pulse_with(vec![Veto::SpreadTooWide], 92.0);
        assert_eq!(p.tradability, 0, "vetoed pulse published a non-zero score");
    }

    #[test]
    fn every_veto_kind_zeroes_the_score() {
        for veto in [
            Veto::SpreadTooWide,
            Veto::InsufficientDepth,
            Veto::StaleFeed,
            Veto::FundingExtreme,
            Veto::InsufficientHistory,
        ] {
            assert_eq!(pulse_with(vec![veto.clone()], 100.0).tradability, 0);
        }
    }

    #[test]
    fn clean_pulse_keeps_its_score() {
        assert_eq!(pulse_with(vec![], 72.4).tradability, 72);
    }

    #[test]
    fn tradability_is_clamped_not_wrapped() {
        // A weighting bug must degrade to a bounded score, never wrap a u8.
        assert_eq!(pulse_with(vec![], 4000.0).tradability, 100);
        assert_eq!(pulse_with(vec![], -50.0).tradability, 0);
        assert_eq!(pulse_with(vec![], f64::NAN).tradability, 0);
    }

    #[test]
    fn staleness_uses_feed_ts_not_computation_ts() {
        // A pulse recomputed on schedule from a dead feed has a fresh `ts` and stale
        // facts. Anchoring staleness to `ts` would call that healthy.
        let p = pulse_with(vec![], 80.0);
        let now = p.ts + 200; // computed 200ms ago
        assert!(
            p.is_stale(now, 100),
            "staleness anchored to the wrong timestamp"
        );
    }

    #[test]
    fn feed_age_never_goes_negative_on_clock_skew() {
        let p = pulse_with(vec![], 80.0);
        assert_eq!(p.feed_age_ms(p.feed_ts - 5_000), 0);
    }

    #[test]
    fn round_trips_through_json_unchanged() {
        let p = pulse_with(vec![Veto::StaleFeed], 0.0);
        let json = serde_json::to_string(&p).expect("serialize");
        let back: Pulse = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(p, back);
    }

    #[test]
    fn wire_shape_matches_the_documented_contract() {
        // docs/MULTI_TENANCY.md is the contract the Python side is written against.
        // Renaming a field here silently breaks it, so pin the key names.
        let json = serde_json::to_value(pulse_with(vec![], 72.0)).expect("serialize");
        for key in [
            "v",
            "symbol",
            "ts",
            "feed_ts",
            "regime",
            "tradability",
            "vetoes",
            "factors",
            "structure",
            "context",
            "reference_price",
        ] {
            assert!(json.get(key).is_some(), "contract lost its `{key}` field");
        }
        for key in [
            "trend_alignment",
            "volatility_band",
            "efficiency_ratio",
            "liquidity_window",
            "positioning",
            "book_quality",
        ] {
            assert!(
                json.get("factors").and_then(|f| f.get(key)).is_some(),
                "factors lost `{key}`"
            );
        }
        assert_eq!(
            json.get("regime").and_then(|r| r.as_str()),
            Some("trending_up")
        );
    }

    #[test]
    fn a_pulse_can_never_carry_a_trade_decision() {
        // The rule that keeps synthesis per-user. If someone adds an entry/stop/target
        // to this struct, every user starts receiving the same trade and the
        // shared/per-user boundary in docs/MULTI_TENANCY.md is gone.
        let json = serde_json::to_value(pulse_with(vec![], 72.0)).expect("serialize");
        let obj = json.as_object().expect("pulse serialises to an object");
        for forbidden in [
            "entry",
            "entry_price",
            "stop",
            "stop_loss",
            "take_profit",
            "target",
            "direction",
            "side",
            "position_size",
        ] {
            assert!(
                !obj.contains_key(forbidden),
                "pulse gained `{forbidden}` — the shared plane must not emit trade decisions"
            );
        }
    }
}
