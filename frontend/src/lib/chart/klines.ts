/**
 * Kline plumbing for the terminal chart — pure, unit-tested.
 *
 * - SYMBOLS / INTERVALS: the desk's instrument + timeframe registries.
 * - normalizeKlines: raw Binance rows → klinecharts KLineData (ms timestamps).
 * - fetchKlines: same-origin /api/klines proxy (Binance → fallbacks), with
 *   endTime pagination for pan-back history.
 * - bucketKline: folds a live 1m bar into the active interval's forming candle —
 *   BTC streams 1m over the backend WS; bucketing keeps every timeframe live
 *   instead of only 1m (a fresh bucket opens when the 1m bar crosses the
 *   interval boundary).
 */

export interface KLineBar {
    // Index signature matches klinecharts' KLineData contract (extra numeric
    // fields ride along; Bucket's bookkeeping fields are numbers too).
    [key: string]: number
    timestamp: number
    open: number
    high: number
    low: number
    close: number
    volume: number
}

export interface SymbolInfo {
    ticker: string
    label: string
    pricePrecision: number
    volumePrecision: number
}

export const SYMBOLS: SymbolInfo[] = [
    { ticker: "BTCUSDT", label: "BTC", pricePrecision: 1, volumePrecision: 3 },
    { ticker: "ETHUSDT", label: "ETH", pricePrecision: 2, volumePrecision: 2 },
    { ticker: "XAUTUSDT", label: "Gold", pricePrecision: 1, volumePrecision: 2 },
]

export function symbolInfo(ticker: string): SymbolInfo {
    return SYMBOLS.find((s) => s.ticker === ticker) ?? SYMBOLS[0]
}

export interface IntervalInfo {
    /** Binance interval string (what /api/klines expects). */
    id: string
    /** klinecharts period. */
    span: number
    type: "minute" | "hour" | "day"
    ms: number
}

export const INTERVALS: IntervalInfo[] = [
    { id: "5m", span: 5, type: "minute", ms: 5 * 60_000 },
    { id: "15m", span: 15, type: "minute", ms: 15 * 60_000 },
    { id: "30m", span: 30, type: "minute", ms: 30 * 60_000 },
    { id: "1h", span: 1, type: "hour", ms: 60 * 60_000 },
    { id: "4h", span: 4, type: "hour", ms: 4 * 60 * 60_000 },
    { id: "1d", span: 1, type: "day", ms: 24 * 60 * 60_000 },
]

export function intervalInfo(id: string): IntervalInfo {
    return INTERVALS.find((i) => i.id === id) ?? INTERVALS[0]
}

/** Raw Binance kline row: [openTime, open, high, low, close, volume, ...]. */
export type RawKline = [number, string, string, string, string, string, ...unknown[]]

export function normalizeKlines(raw: unknown): KLineBar[] {
    if (!Array.isArray(raw)) return []
    const bars: KLineBar[] = []
    for (const row of raw as RawKline[]) {
        if (!Array.isArray(row) || row.length < 6) continue
        const timestamp = Number(row[0])
        const open = Number(row[1])
        const high = Number(row[2])
        const low = Number(row[3])
        const close = Number(row[4])
        const volume = Number(row[5])
        if (!Number.isFinite(timestamp) || !Number.isFinite(close)) continue
        bars.push({ timestamp, open, high, low, close, volume: Number.isFinite(volume) ? volume : 0 })
    }
    bars.sort((a, b) => a.timestamp - b.timestamp)
    return bars
}

/**
 * Fetch bars from the same-origin proxy. `endTime` (ms, exclusive-ish) enables
 * pan-back pagination; omitted = most recent window.
 */
export async function fetchKlines(
    ticker: string,
    interval: string,
    limit = 500,
    endTime?: number,
): Promise<KLineBar[]> {
    const params = new URLSearchParams({ symbol: ticker, interval, limit: String(limit) })
    if (endTime != null && Number.isFinite(endTime)) params.set("endTime", String(Math.floor(endTime)))
    const res = await fetch(`/api/klines?${params.toString()}`, { cache: "no-store" })
    if (!res.ok) throw new Error(`Market data request failed (${res.status})`)
    return normalizeKlines(await res.json())
}

/**
 * Fold a live 1m bar into the forming candle of `intervalMs`.
 *
 * Returns the bar to push into the chart (klinecharts merges by timestamp:
 * equal → overwrite forming candle, greater → append new candle).
 *
 * `current` is the previously-forming bucket for this interval (or null on
 * boot/interval switch). Volume: Binance 1m frames carry the 1m bar's CUMULATIVE
 * volume, so the bucket sums closed minutes and replaces the live minute's
 * contribution on every tick (tracked via `lastMinuteTs`/`lastMinuteVol`).
 */
export interface Bucket extends KLineBar {
    lastMinuteTs: number
    lastMinuteVol: number
}

export function bucketKline(oneMinBar: KLineBar, intervalMs: number, current: Bucket | null): Bucket {
    const bucketTs = Math.floor(oneMinBar.timestamp / intervalMs) * intervalMs

    if (!current || current.timestamp !== bucketTs) {
        // New interval bucket opens with this minute's state.
        return {
            timestamp: bucketTs,
            open: oneMinBar.open,
            high: oneMinBar.high,
            low: oneMinBar.low,
            close: oneMinBar.close,
            volume: oneMinBar.volume,
            lastMinuteTs: oneMinBar.timestamp,
            lastMinuteVol: oneMinBar.volume,
        }
    }

    const sameMinute = current.lastMinuteTs === oneMinBar.timestamp
    // Replace the forming minute's volume contribution; add a new minute's.
    const volume = sameMinute
        ? current.volume - current.lastMinuteVol + oneMinBar.volume
        : current.volume + oneMinBar.volume

    return {
        timestamp: bucketTs,
        open: current.open,
        high: Math.max(current.high, oneMinBar.high),
        low: Math.min(current.low, oneMinBar.low),
        close: oneMinBar.close,
        volume,
        lastMinuteTs: oneMinBar.timestamp,
        lastMinuteVol: oneMinBar.volume,
    }
}

/** Parse a backend WS kline frame (raw Binance event) → 1m KLineBar, or null. */
export function parseWsKline(data: unknown): { symbol: string; bar: KLineBar } | null {
    const d = (data ?? {}) as Record<string, unknown>
    const k = d.k as Record<string, unknown> | undefined
    if (!k) return null
    const timestamp = Number(k.t)
    const open = Number(k.o)
    const high = Number(k.h)
    const low = Number(k.l)
    const close = Number(k.c)
    const volume = Number(k.v)
    if (!Number.isFinite(timestamp) || !Number.isFinite(close)) return null
    return {
        symbol: String(d.s ?? k.s ?? "").toUpperCase(),
        bar: { timestamp, open, high, low, close, volume: Number.isFinite(volume) ? volume : 0 },
    }
}
