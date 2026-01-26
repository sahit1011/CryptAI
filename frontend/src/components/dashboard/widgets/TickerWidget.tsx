"use client"

import { GlassCard } from "@/components/ui/glass-card"
import { useMarketStore } from "@/hooks/useMarketData"
import { ArrowUp, ArrowDown, Activity } from "lucide-react"
import { cn } from "@/lib/utils"

export function TickerWidget() {
    const { ticker, isConnected } = useMarketStore()

    if (!ticker) {
        return (
            <GlassCard className="h-full">
                <div className="p-6 flex items-center justify-center h-full">
                    <div className="flex items-center gap-2 text-muted-foreground animate-pulse">
                        <Activity className="h-4 w-4" />
                        <span>Connecting to Market Data...</span>
                    </div>
                </div>
            </GlassCard>
        )
    }

    const price = parseFloat(ticker.c).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    const change = parseFloat(ticker.p)
    const changePercent = parseFloat(ticker.P)
    const isPositive = change >= 0

    return (
        <GlassCard className="overflow-hidden relative">
            <div className={cn(
                "absolute top-0 left-0 w-1 h-full transition-colors duration-300",
                isPositive ? "bg-emerald-500" : "bg-red-500"
            )} />
            <div className="p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h3 className="text-muted-foreground text-sm font-medium mb-1">BTC/USDT</h3>
                        <div className="text-4xl font-bold text-white tracking-tight font-mono">
                            ${price}
                        </div>
                    </div>
                    <div className={cn(
                        "flex items-center px-2.5 py-1 rounded-full text-sm font-medium border",
                        isPositive ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" : "bg-red-500/10 text-red-500 border-red-500/20"
                    )}>
                        {isPositive ? <ArrowUp className="h-4 w-4 mr-1" /> : <ArrowDown className="h-4 w-4 mr-1" />}
                        {Math.abs(changePercent).toFixed(2)}%
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4 mt-6">
                    <div>
                        <p className="text-muted-foreground text-xs uppercase tracking-wider">24h Volume (BTC)</p>
                        <p className="text-white font-mono mt-1">{parseFloat(ticker.v).toFixed(2)}</p>
                    </div>
                    <div>
                        <p className="text-muted-foreground text-xs uppercase tracking-wider">24h Quote (USDT)</p>
                        <p className="text-white font-mono mt-1">{(parseFloat(ticker.q) / 1000000).toFixed(2)}M</p>
                    </div>
                </div>
            </div>
        </GlassCard>
    )
}
