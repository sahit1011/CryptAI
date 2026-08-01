//! CryptAI signal engine — the shared signal plane.
//!
//! This crate is the one universal component in the architecture (see
//! `docs/MULTI_TENANCY.md`). It is **not an agent**: no LLM, no `user_id`, no awareness
//! that users exist. It computes objective facts about the market — identical for every
//! tenant — and publishes them for the per-user reasoning plane to interpret.
//!
//! Its cost is O(1) in user count, which is the whole reason the split exists.
//!
//! # Layout
//! - [`pulse`] — the wire contract. The only interface to the rest of the system.
//! - [`indicators`] — deterministic math. Pure, total, no I/O.
//! - [`scoring`] — veto gates, weighted factors, regime classification.
//!
//! # Two invariants
//! - A pulse carries **facts and scores, never a trade decision**.
//! - A non-empty veto list forces `tradability` to 0, enforced in the constructor.

pub mod indicators;
pub mod pulse;
pub mod quant;
pub mod scoring;

pub use indicators::Candle;
pub use pulse::{Context, Factors, Level, Pulse, Regime, Structure, Veto, SCHEMA_VERSION};
pub use quant::{hurst_exponent, variance_ratio, yang_zhang, Ohlc, VarianceRatio, YangZhang};
