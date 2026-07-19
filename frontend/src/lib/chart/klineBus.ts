/**
 * Kline ref bus — WS market frames → chart, OUTSIDE React.
 *
 * The backend relays Binance 1m kline frames over the app WebSocket. Routing
 * them through React state would re-render on every tick; instead
 * useMarketData publishes onto this module-level bus and the chart's
 * dataLoader subscribes directly (per the terminal's performance doctrine:
 * motion marks state changes, data flows through refs).
 */
import type { KLineBar } from "./klines"

type KlineListener = (symbol: string, bar: KLineBar) => void

const listeners = new Set<KlineListener>()

export function subscribeKlineBus(listener: KlineListener): () => void {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
}

export function publishKline(symbol: string, bar: KLineBar): void {
    for (const l of listeners) {
        try { l(symbol, bar) } catch { /* one bad listener never breaks the bus */ }
    }
}
