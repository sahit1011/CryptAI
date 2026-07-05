"use client"

import { BookOpen } from "lucide-react"

import { Card } from "@/components/ui/card"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { ConnectionStatus } from "@/components/ui/connection-status"
import { useMarketStore } from "@/hooks/useMarketData"
import { cn, safeNum } from "@/lib/utils"

const LEVELS = 12

type Level = { price: number; qty: number }

/** Parse raw [price, qty] tuples into finite numbers, dropping malformed rows. */
function parseLevels(rows: [string, string][] | undefined, count: number): Level[] {
    if (!rows) return []
    const out: Level[] = []
    for (const row of rows) {
        const price = safeNum(row?.[0], NaN)
        const qty = safeNum(row?.[1], NaN)
        if (Number.isFinite(price) && Number.isFinite(qty) && qty > 0) {
            out.push({ price, qty })
        }
        if (out.length >= count) break
    }
    return out
}

/** A single book row with a data-driven depth bar sized relative to the book max. */
function BookRow({
    level,
    maxQty,
    side,
}: {
    level: Level
    maxQty: number
    side: "ask" | "bid"
}) {
    const width = maxQty > 0 ? Math.min((level.qty / maxQty) * 100, 100) : 0
    const isAsk = side === "ask"
    return (
        <div className="relative grid grid-cols-2 gap-2 px-3 py-[3px] leading-tight">
            <div
                aria-hidden
                className={cn(
                    "absolute inset-y-0 right-0 transition-[width] duration-200",
                    isAsk ? "bg-loss-muted" : "bg-profit-muted",
                )}
                style={{ width: `${width}%` }}
            />
            <Value
                className={cn("relative z-10 text-xs", isAsk ? "text-loss" : "text-profit")}
                value={level.price}
                decimals={2}
            />
            <Value
                className="relative z-10 text-right text-xs text-muted-foreground"
                value={level.qty}
                decimals={4}
            />
        </div>
    )
}

export function OrderBookWidget() {
    const { orderBook, status } = useMarketStore()

    // Asks reversed so the lowest ask sits just above the spread; bids descend.
    const asks = parseLevels(orderBook?.a, LEVELS).reverse()
    const bids = parseLevels(orderBook?.b, LEVELS)

    const bestAsk = asks.length ? asks[asks.length - 1].price : undefined
    const bestBid = bids.length ? bids[0].price : undefined
    const spread =
        bestAsk !== undefined && bestBid !== undefined ? bestAsk - bestBid : undefined
    const spreadPct =
        spread !== undefined && bestBid ? (spread / bestBid) * 100 : undefined
    const mid =
        bestAsk !== undefined && bestBid !== undefined
            ? (bestAsk + bestBid) / 2
            : bestAsk ?? bestBid

    // Data-driven depth scale: bars are sized against the deepest visible level.
    const maxQty = Math.max(
        0,
        ...asks.map((l) => l.qty),
        ...bids.map((l) => l.qty),
    )

    const hasBook = asks.length > 0 || bids.length > 0

    return (
        <Card className="flex h-full flex-col overflow-hidden py-0">
            <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
                <div className="flex items-center gap-2">
                    <BookOpen className="size-4 text-muted-foreground" />
                    <h3 className="heading-4">Order Book</h3>
                </div>
                <ConnectionStatus status={status} />
            </div>

            {/* Column headers */}
            <div className="grid grid-cols-2 gap-2 border-b border-border px-3 py-1.5">
                <span className="label-md">Price · USDT</span>
                <span className="label-md text-right">Amount · BTC</span>
            </div>

            {hasBook ? (
                <div className="scroll-terminal flex min-h-0 flex-1 flex-col">
                    {/* Asks */}
                    <div className="flex flex-1 flex-col justify-end overflow-hidden">
                        {asks.map((level, i) => (
                            <BookRow key={`ask-${i}`} level={level} maxQty={maxQty} side="ask" />
                        ))}
                    </div>

                    {/* Spread / mid marker */}
                    <div className="flex items-center justify-between border-y border-border-strong bg-elevated px-3 py-1.5">
                        <Value
                            className="text-sm font-semibold text-foreground"
                            value={mid}
                            decimals={2}
                        />
                        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                            <span className="label-md">Spread</span>
                            <Value value={spread} decimals={2} />
                            {spreadPct !== undefined ? (
                                <Value value={spreadPct} decimals={3} prefix="(" suffix="%)" />
                            ) : null}
                        </span>
                    </div>

                    {/* Bids */}
                    <div className="flex-1 overflow-hidden">
                        {bids.map((level, i) => (
                            <BookRow key={`bid-${i}`} level={level} maxQty={maxQty} side="bid" />
                        ))}
                    </div>
                </div>
            ) : (
                <div className="flex flex-1 items-center justify-center">
                    <EmptyState
                        icon={<BookOpen />}
                        title="No order book data"
                        description={
                            status === "open"
                                ? "Waiting for the first depth update from the feed."
                                : "The market feed is offline — order book will populate once connected."
                        }
                    />
                </div>
            )}
        </Card>
    )
}
