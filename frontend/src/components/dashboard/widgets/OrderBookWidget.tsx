"use client"

import { GlassCard } from "@/components/ui/glass-card"
import { useMarketStore } from "@/hooks/useMarketData"
import { safeNum, safeFixed } from "@/lib/utils"

export function OrderBookWidget() {
    const { orderBook } = useMarketStore()

    // Take top 10 asks (reversed to show lowest ask at bottom) and top 10 bids
    const asks = orderBook?.a.slice(0, 10).reverse() || []
    const bids = orderBook?.b.slice(0, 10) || []
    // Best ask may be absent if the book is empty; guard the [0][0] access.
    const bestAsk = orderBook?.a?.[0]?.[0]

    return (
        <GlassCard className="h-full flex flex-col overflow-hidden">
            <div className="p-3 border-b border-white/5">
                <h3 className="text-sm font-medium text-muted-foreground">Order Book</h3>
            </div>
            <div className="flex-1 font-mono text-xs flex flex-col">
                <div className="grid grid-cols-2 gap-2 p-2 text-muted-foreground/70 border-b border-white/5">
                    <span>Price (USDT)</span>
                    <span className="text-right">Amount (BTC)</span>
                </div>

                <div className="flex flex-col flex-1 min-h-0">
                    {/* Asks (Sells) - Red */}
                    <div className="flex-1 flex flex-col justify-end overflow-hidden">
                        {asks.map(([price, qty], i) => (
                            <div key={`ask-${i}`} className="grid grid-cols-2 gap-2 px-2 py-0.5 hover:bg-red-500/5 relative group">
                                <span className="text-red-400 z-10">{safeFixed(price, 2)}</span>
                                <span className="text-muted-foreground text-right z-10">{safeFixed(qty, 4)}</span>
                                <div className="absolute right-0 top-0 bottom-0 bg-red-500/10 transition-all duration-200" style={{ width: `${Math.min(safeNum(qty) * 100, 100)}%` }} />
                            </div>
                        ))}
                    </div>

                    <div className="border-t border-b border-white/10 my-1 py-1 text-center text-white font-bold bg-white/5">
                        {bestAsk !== undefined ? safeFixed(bestAsk, 2, '---') : '---'}
                    </div>

                    {/* Bids (Buys) - Green */}
                    <div className="flex-1 overflow-hidden">
                        {bids.map(([price, qty], i) => (
                            <div key={`bid-${i}`} className="grid grid-cols-2 gap-2 px-2 py-0.5 hover:bg-green-500/5 relative group">
                                <span className="text-green-400 z-10">{safeFixed(price, 2)}</span>
                                <span className="text-muted-foreground text-right z-10">{safeFixed(qty, 4)}</span>
                                <div className="absolute right-0 top-0 bottom-0 bg-green-500/10 transition-all duration-200" style={{ width: `${Math.min(safeNum(qty) * 100, 100)}%` }} />
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </GlassCard>
    )
}
