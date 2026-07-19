/**
 * Working-order mapping — pure and unit-tested.
 *
 * The backend emits one BingX-like dict shape from both the paper engine and
 * the exchange read-through: {orderId, symbol, side, type, origQty, price,
 * stopPrice, status, reduceOnly, updateTime}. This maps it to the UI's shape,
 * dropping malformed rows instead of rendering lies.
 */

export interface OpenOrder {
    orderId: string
    symbol: string
    side: "BUY" | "SELL"
    type: string
    qty: number
    /** Limit price (0 = none, e.g. stop-market). */
    price: number
    /** Stop trigger price (0 = none). */
    stopPrice: number
    status: string
    reduceOnly: boolean
    updateTime: number
}

export function mapOpenOrders(raw: unknown): OpenOrder[] {
    if (!Array.isArray(raw)) return []
    const orders: OpenOrder[] = []
    for (const row of raw as Record<string, unknown>[]) {
        if (!row || typeof row !== "object") continue
        const orderId = String(row.orderId ?? "")
        const symbol = String(row.symbol ?? "").toUpperCase()
        const side = String(row.side ?? "").toUpperCase()
        const qty = Number(row.origQty ?? row.quantity ?? 0)
        if (!orderId || !symbol || (side !== "BUY" && side !== "SELL") || !Number.isFinite(qty) || qty <= 0) continue
        orders.push({
            orderId,
            symbol,
            side,
            type: String(row.type ?? "").toUpperCase(),
            qty,
            price: Number(row.price ?? 0) || 0,
            stopPrice: Number(row.stopPrice ?? 0) || 0,
            status: String(row.status ?? "NEW").toUpperCase(),
            reduceOnly: Boolean(row.reduceOnly),
            updateTime: Number(row.updateTime ?? 0) || 0,
        })
    }
    // Newest first — matches every other tape on the desk.
    orders.sort((a, b) => b.updateTime - a.updateTime)
    return orders
}
