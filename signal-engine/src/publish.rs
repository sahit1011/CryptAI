//! Publish pulses to Redis.
//!
//! Writes both a durable key (`SET market:pulse:{symbol}`) and a fanout notification
//! (`PUBLISH`), because consumers need both shapes: a session starting mid-stream reads
//! the key for current state, while a running session subscribes for updates. Publishing
//! only to the channel would leave every new session blind until the next tick.
//!
//! Keys are deliberately NOT namespaced by user. That asymmetry against the per-user
//! plane's `user_id`-scoped keys is the tenancy boundary made visible in the key layout
//! (see `docs/MULTI_TENANCY.md`, invariant 7).

use redis::aio::ConnectionManager;
use redis::AsyncCommands;
use tracing::{debug, warn};

use crate::pulse::{GlobalPulse, Pulse};

pub const KEY_PREFIX: &str = "market:pulse:";
pub const CHANNEL_PREFIX: &str = "market:pulse:updates:";
/// The cross-market aggregate (FR-SIGNAL-2). Note it deliberately lives under the same
/// prefix and TTL discipline as the per-symbol keys: if the engine dies, "the market is
/// hot" must expire with it.
pub const GLOBAL_KEY: &str = "market:pulse:global";
pub const GLOBAL_CHANNEL: &str = "market:pulse:updates:GLOBAL";

/// TTL on each key, in seconds.
///
/// Load-bearing: if the engine dies, its keys must EXPIRE rather than sit in Redis
/// looking like current market state. A consumer's staleness check is the primary guard,
/// but a key that disappears turns a subtle "why is this data old" into an obvious
/// "there is no data", which is a much easier failure to diagnose at 3am.
pub const KEY_TTL_SECS: u64 = 120;

pub fn key_for(symbol: &str) -> String {
    format!("{KEY_PREFIX}{}", symbol.to_uppercase())
}

pub fn channel_for(symbol: &str) -> String {
    format!("{CHANNEL_PREFIX}{}", symbol.to_uppercase())
}

/// Publish one pulse. Errors are logged and swallowed: a Redis blip must not kill the
/// ingest loop, and the next tick will overwrite anyway.
pub async fn publish(conn: &mut ConnectionManager, pulse: &Pulse) -> bool {
    let payload = match serde_json::to_string(pulse) {
        Ok(p) => p,
        Err(e) => {
            warn!("failed to serialise pulse for {}: {e}", pulse.symbol);
            return false;
        }
    };

    let key = key_for(&pulse.symbol);
    if let Err(e) = conn.set_ex::<_, _, ()>(&key, &payload, KEY_TTL_SECS).await {
        warn!("failed to SET {key}: {e}");
        return false;
    }

    // Fanout is best-effort — the durable key is the source of truth.
    if let Err(e) = conn
        .publish::<_, _, ()>(channel_for(&pulse.symbol), &payload)
        .await
    {
        debug!("publish to channel failed (non-fatal): {e}");
    }

    true
}

/// Publish the cross-market aggregate. Same durable-key + best-effort-fanout shape,
/// same swallowed errors, as the per-symbol publish.
pub async fn publish_global(conn: &mut ConnectionManager, global: &GlobalPulse) -> bool {
    let payload = match serde_json::to_string(global) {
        Ok(p) => p,
        Err(e) => {
            warn!("failed to serialise the global pulse: {e}");
            return false;
        }
    };
    if let Err(e) = conn
        .set_ex::<_, _, ()>(GLOBAL_KEY, &payload, KEY_TTL_SECS)
        .await
    {
        warn!("failed to SET {GLOBAL_KEY}: {e}");
        return false;
    }
    if let Err(e) = conn.publish::<_, _, ()>(GLOBAL_CHANNEL, &payload).await {
        debug!("global publish to channel failed (non-fatal): {e}");
    }
    true
}

/// Connect with a ConnectionManager, which reconnects internally rather than requiring
/// the caller to rebuild the client on every blip.
pub async fn connect(url: &str) -> Result<ConnectionManager, redis::RedisError> {
    let client = redis::Client::open(url)?;
    ConnectionManager::new(client).await
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::*;

    #[test]
    fn keys_are_uppercased_and_unnamespaced() {
        assert_eq!(key_for("btcusdt"), "market:pulse:BTCUSDT");
        assert_eq!(key_for("BTCUSDT"), "market:pulse:BTCUSDT");
    }

    #[test]
    fn the_key_layout_carries_no_user_scope() {
        // Invariant 7: shared-plane keys are deliberately un-namespaced while per-user
        // keys are scoped by user_id. A user_id appearing here means shared and
        // per-user state have been conflated.
        let key = key_for("BTCUSDT");
        assert!(
            !key.contains("user"),
            "shared-plane key gained a user scope: {key}"
        );
        assert!(key.starts_with(KEY_PREFIX));
    }

    #[test]
    fn channel_and_key_are_distinct() {
        // If these collided, a PUBLISH would clobber the durable key.
        assert_ne!(key_for("BTCUSDT"), channel_for("BTCUSDT"));
    }

    #[test]
    fn ttl_outlives_a_normal_publish_interval_but_not_an_outage() {
        // Long enough that a slow tick does not expire a healthy key, short enough that
        // a dead engine's keys vanish quickly. Const blocks: the pin now fails at
        // COMPILE time, which is strictly earlier than a test run.
        const {
            assert!(KEY_TTL_SECS >= 60, "TTL too tight; a slow tick would expire live data");
        }
        const {
            assert!(KEY_TTL_SECS <= 300, "TTL too loose; a dead engine looks alive for too long");
        }
    }
}
