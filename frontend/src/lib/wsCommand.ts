/**
 * WS market-subscription command bus.
 *
 * The socket lives inside useMarketData's effect; the terminal decides which
 * market channels it wants (per the backend protocol:
 * `{"op":"subscribe","channels":["ticker.ETHUSDT","kline.1m.ETHUSDT","depth.ETHUSDT"]}`).
 * This module bridges the two without threading refs through React:
 * useMarketData registers a sender on open (null on close); the terminal sets
 * the desired channel set on symbol change. Desired state is replayed on every
 * (re)connect, so subscriptions survive reconnects.
 *
 * The base BTCUSDT streams are always-on server-side — subscribing to them is
 * harmless but unnecessary, so callers only pass non-base channels.
 */

type Sender = (payload: string) => void

let sender: Sender | null = null
let desired = new Set<string>()
let acknowledged = new Set<string>()

function send(op: "subscribe" | "unsubscribe", channels: string[]): void {
    if (!sender || channels.length === 0) return
    try {
        sender(JSON.stringify({ op, channels }))
    } catch { /* socket raced shut — the next registerWsSender replays desired */ }
}

/** useMarketData calls this with a live sender on open, and null on close. */
export function registerWsSender(fn: Sender | null): void {
    sender = fn
    acknowledged = new Set()
    if (fn && desired.size > 0) {
        send("subscribe", [...desired])
        acknowledged = new Set(desired)
    }
}

/** Declare the full set of desired market channels (diffed against the last set). */
export function setMarketSubscriptions(channels: string[]): void {
    const next = new Set(channels)
    const toAdd = [...next].filter((c) => !acknowledged.has(c))
    const toRemove = [...acknowledged].filter((c) => !next.has(c))
    desired = next
    if (!sender) return
    send("unsubscribe", toRemove)
    send("subscribe", toAdd)
    acknowledged = next
}

/** The channels the terminal wants for one symbol (empty for the base symbol). */
export function channelsForSymbol(symbol: string): string[] {
    if (symbol === "BTCUSDT") return [] // base streams are always-on
    return [`ticker.${symbol}`, `depth.${symbol}`, `kline.1m.${symbol}`]
}
