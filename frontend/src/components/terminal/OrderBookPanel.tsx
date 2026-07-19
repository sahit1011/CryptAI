"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { useMarketStore } from "@/hooks/useMarketData"
import { useTerminalStore } from "@/store/useTerminalStore"
import { symbolInfo } from "@/lib/chart/klines"
import { cn } from "@/lib/utils"

/*
 * OrderBookPanel — asks over spread over bids, depth bars behind the numbers.
 *
 * Provenance is disclosed, never faked: BTC's top-of-book comes from the
 * backend's live L5 WS diff (badge "L5 · live"), extended/refreshed by a 5s
 * REST snapshot; the other desk symbols are snapshot-only ("REST · 5s") until
 * the WS subscribe protocol lands. Book values NEVER animate — instant style
 * writes on a throttled commit cadence, per the motion doctrine.
 *
 * Row click prefills the ticket's entry price.
 */

type Level = [number, number] // [price, qty]

const SNAPSHOT_MS = 5_000
const WS_FRESH_MS = 3_000
const COMMIT_MS = 300
const ROWS_PER_SIDE = 11

/** Group levels into price buckets (asks round up, bids round down). Pure. */
export function aggregateLevels(levels: Level[], step: number, side: "ask" | "bid"): Level[] {
    if (step <= 0) return levels
    const buckets = new Map<number, number>()
    for (const [price, qty] of levels) {
        if (qty <= 0) continue
        const bucket = side === "ask" ? Math.ceil(price / step) * step : Math.floor(price / step) * step
        buckets.set(bucket, (buckets.get(bucket) ?? 0) + qty)
    }
    const out = [...buckets.entries()] as Level[]
    out.sort((a, b) => (side === "ask" ? a[0] - b[0] : b[0] - a[0]))
    return out
}

/** Per-symbol precision steps (raw tick → coarser groupings). */
function stepsFor(ticker: string): number[] {
    if (ticker === "ETHUSDT") return [0.01, 0.1, 1]
    return [0.1, 1, 10] // BTC, XAUT
}

interface BookState {
    asks: Level[]
    bids: Level[]
    source: "ws+rest" | "rest"
    at: number
}

function parseLevels(raw: unknown): Level[] {
    if (!Array.isArray(raw)) return []
    const out: Level[] = []
    for (const row of raw as [string, string][]) {
        const price = Number(row?.[0])
        const qty = Number(row?.[1])
        if (Number.isFinite(price) && Number.isFinite(qty) && qty > 0) out.push([price, qty])
    }
    return out
}

export function OrderBookPanel() {
    const symbol = useTerminalStore((s) => s.symbol)
    const setTicketPrefill = useTerminalStore((s) => s.setTicketPrefill)
    const info = symbolInfo(symbol)
    const steps = stepsFor(symbol)
    const [step, setStep] = useState(steps[0])
    const [book, setBook] = useState<BookState | null>(null)

    // Latest snapshots live in refs; a 300ms commit tick writes to state so the
    // DOM updates at a readable cadence regardless of WS frame rate.
    const restRef = useRef<{ asks: Level[]; bids: Level[]; at: number } | null>(null)
    const wsAtRef = useRef(0)

    // Reset the precision step when the symbol changes (deferred, not sync-in-effect).
    useEffect(() => {
        restRef.current = null
        const t = setTimeout(() => { setStep(stepsFor(symbol)[0]); setBook(null) }, 0)
        return () => clearTimeout(t)
    }, [symbol])

    // REST snapshot poll — every symbol, 5s.
    useEffect(() => {
        let stopped = false
        const poll = async () => {
            if (stopped) return
            try {
                const res = await fetch(`/api/depth?symbol=${symbol}&limit=50`, { cache: "no-store" })
                if (!res.ok || stopped) return
                const d = await res.json()
                restRef.current = { asks: parseLevels(d.asks), bids: parseLevels(d.bids), at: Date.now() }
            } catch { /* snapshot missing — the last one keeps rendering with its honest timestamp */ }
        }
        void poll()
        const id = setInterval(poll, SNAPSHOT_MS)
        return () => { stopped = true; clearInterval(id) }
    }, [symbol])

    // WS L5 freshness marker (the frames themselves are read at commit time).
    useEffect(() => {
        const unsub = useMarketStore.subscribe((state, prev) => {
            if (state.orderBook !== prev.orderBook) wsAtRef.current = Date.now()
        })
        return unsub
    }, [])

    // Commit tick: merge REST + (BTC-only) WS L5 → one BookState.
    useEffect(() => {
        const id = setInterval(() => {
            const rest = restRef.current
            const wsBook = useMarketStore.getState().orderBook
            const isWsFresh = symbol === "BTCUSDT" && wsBook != null && Date.now() - wsAtRef.current < WS_FRESH_MS

            if (!rest && !isWsFresh) return

            let asks: Level[] = rest?.asks ?? []
            let bids: Level[] = rest?.bids ?? []
            if (isWsFresh && wsBook) {
                const wsAsks = parseLevels(wsBook.a)
                const wsBids = parseLevels(wsBook.b)
                if (wsAsks.length && wsBids.length) {
                    // L5 owns the top of book; REST extends beyond its range.
                    const maxWsAsk = Math.max(...wsAsks.map((l) => l[0]))
                    const minWsBid = Math.min(...wsBids.map((l) => l[0]))
                    asks = [...wsAsks, ...asks.filter(([p]) => p > maxWsAsk)]
                    bids = [...wsBids, ...bids.filter(([p]) => p < minWsBid)]
                }
            }
            setBook((prev) => {
                const next: BookState = {
                    asks, bids,
                    source: isWsFresh ? "ws+rest" : "rest",
                    at: rest?.at ?? Date.now(),
                }
                // Skip state churn when nothing changed since last commit.
                if (prev && prev.asks === next.asks && prev.bids === next.bids && prev.source === next.source) return prev
                return next
            })
        }, COMMIT_MS)
        return () => clearInterval(id)
    }, [symbol])

    const view = useMemo(() => {
        if (!book) return null
        const asks = aggregateLevels(book.asks, step, "ask").slice(0, ROWS_PER_SIDE)
        const bids = aggregateLevels(book.bids, step, "bid").slice(0, ROWS_PER_SIDE)
        if (asks.length === 0 || bids.length === 0) return null

        let cum = 0
        const askRows = asks.map(([price, qty]) => ({ price, qty, cum: (cum += qty) }))
        const askMax = cum
        cum = 0
        const bidRows = bids.map(([price, qty]) => ({ price, qty, cum: (cum += qty) }))
        const bidMax = cum

        const bestAsk = asks[0][0]
        const bestBid = bids[0][0]
        const mid = (bestAsk + bestBid) / 2
        const spread = bestAsk - bestBid
        const spreadBps = mid > 0 ? (spread / mid) * 10_000 : 0

        return { askRows: askRows.reverse(), bidRows, askMax, bidMax, mid, spread, spreadBps }
    }, [book, step])

    return (
        <div className="flex h-full flex-col">
            <div className="flex h-6 shrink-0 items-center justify-between border-b border-border px-3">
                <span className="label-md text-subtle-foreground">Order book</span>
                <div className="flex items-center gap-2">
                    <span
                        className="num text-[10px] text-subtle-foreground"
                        title={book?.source === "ws+rest"
                            ? "Top of book streams live (L5 WS); depth refreshes every 5s"
                            : "Snapshot refreshes every 5s — live multi-symbol streaming lands with the WS subscribe protocol"}
                    >
                        {book?.source === "ws+rest" ? "L5 · live" : "REST · 5s"}
                    </span>
                    <div className="flex overflow-hidden rounded-sm border border-border">
                        {steps.map((s) => (
                            <button
                                key={s}
                                onClick={() => setStep(s)}
                                className={cn(
                                    "num px-1.5 py-px text-[10px] transition-colors duration-150",
                                    step === s ? "bg-elevated text-foreground" : "text-subtle-foreground hover:text-foreground",
                                )}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {!view ? (
                <EmptyState
                    className="flex-1"
                    title="Waiting for depth"
                    description="The order-book snapshot hasn't answered yet. It retries every 5 seconds."
                />
            ) : (
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                    {/* Column header */}
                    <div className="flex shrink-0 items-center justify-between px-3 py-1">
                        <span className="label-md text-subtle-foreground">Price</span>
                        <span className="label-md text-subtle-foreground">Size</span>
                        <span className="label-md text-subtle-foreground">Sum</span>
                    </div>

                    {/* Asks (descending toward the spread) */}
                    <div className="flex flex-1 flex-col justify-end overflow-hidden">
                        {view.askRows.map((r) => (
                            <BookRow key={`a-${r.price}`} side="ask" row={r} max={view.askMax}
                                precision={info.pricePrecision}
                                onClick={() => setTicketPrefill({ entry: r.price })} />
                        ))}
                    </div>

                    {/* Spread row */}
                    <div className="flex shrink-0 items-center justify-between bg-elevated px-3 py-1">
                        <Value className="financial-sm text-foreground" value={view.mid} decimals={info.pricePrecision} />
                        <span className="num text-[10px] text-subtle-foreground">
                            spread <Value className="text-muted-foreground" value={view.spread} decimals={info.pricePrecision} />
                            {" · "}
                            <Value className="text-muted-foreground" value={view.spreadBps} decimals={1} suffix=" bps" />
                        </span>
                    </div>

                    {/* Bids */}
                    <div className="flex flex-1 flex-col overflow-hidden">
                        {view.bidRows.map((r) => (
                            <BookRow key={`b-${r.price}`} side="bid" row={r} max={view.bidMax}
                                precision={info.pricePrecision}
                                onClick={() => setTicketPrefill({ entry: r.price })} />
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

function BookRow({
    side, row, max, precision, onClick,
}: {
    side: "ask" | "bid"
    row: { price: number; qty: number; cum: number }
    max: number
    precision: number
    onClick: () => void
}) {
    const barWidth = max > 0 ? Math.min(100, (row.cum / max) * 100) : 0
    return (
        <button
            onClick={onClick}
            title="Click to prefill the ticket entry"
            className="relative flex h-5 shrink-0 items-center justify-between px-3 text-left hover:bg-elevated"
        >
            <span
                aria-hidden
                className={cn("absolute inset-y-0 right-0", side === "ask" ? "bg-loss-muted" : "bg-profit-muted")}
                style={{ width: `${barWidth}%` }}
            />
            <Value
                className={cn("relative z-10 text-[11px]", side === "ask" ? "text-loss" : "text-profit")}
                value={row.price}
                decimals={precision}
            />
            <Value className="relative z-10 text-[11px] text-muted-foreground" value={row.qty} decimals={3} />
            <Value className="relative z-10 text-[11px] text-subtle-foreground" value={row.cum} decimals={3} />
        </button>
    )
}
