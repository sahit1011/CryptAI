"use client"

import { Card } from "@/components/ui/card"
import { useMarketStore } from "@/hooks/useMarketData"
import { LoadingState, ErrorState } from "@/components/ui/states"
import { Value, PnL } from "@/components/ui/value"
import { ArrowUp, ArrowDown, Activity, WifiOff } from "lucide-react"
import { cn, safeNum } from "@/lib/utils"

/*
 * Live BTC/USDT ticker. Renders real WS data only — honest loading/offline states
 * until the feed provides a ticker. Numbers are monospace via <Value>/<PnL>.
 */
export function TickerWidget() {
    const ticker = useMarketStore((s) => s.ticker)
    const status = useMarketStore((s) => s.status)

    if (!ticker) {
        // No data yet: distinguish "still connecting" from "feed down". Compact
        // fixed height so the empty state matches the populated card instead of
        // stretching to fill the column.
        const down = status === "error" || status === "closed"
        return (
            <Card className="min-h-[168px] justify-center">
                {down ? (
                    <ErrorState
                        icon={<WifiOff />}
                        title="Market feed offline"
                        description="Waiting to reconnect to the live market data stream."
                    />
                ) : (
                    <LoadingState icon={<Activity />} title="Connecting to market data…" />
                )}
            </Card>
        )
    }

    const changePercent = safeNum(ticker.P)
    const isPositive = changePercent >= 0

    return (
        <Card className="relative overflow-hidden py-0">
            {/* Accent rail flips emerald/red with the 24h direction. */}
            <div
                className={cn(
                    "absolute inset-y-0 left-0 w-0.5 transition-colors duration-300",
                    isPositive ? "bg-profit" : "bg-loss",
                )}
            />
            <div className="p-5">
                <div className="flex items-start justify-between">
                    <div>
                        <h3 className="label-md mb-1">BTC/USDT</h3>
                        <Value
                            value={ticker.c}
                            decimals={2}
                            money
                            className="text-3xl font-semibold text-foreground tracking-tight"
                        />
                    </div>
                    <div
                        className={cn(
                            "flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium",
                            isPositive ? "bg-profit-muted text-profit" : "bg-loss-muted text-loss",
                        )}
                    >
                        {isPositive ? (
                            <ArrowUp className="h-3.5 w-3.5" />
                        ) : (
                            <ArrowDown className="h-3.5 w-3.5" />
                        )}
                        <PnL value={changePercent} percent showSign={false} className="text-sm" />
                    </div>
                </div>

                <div className="mt-5 grid grid-cols-2 gap-4">
                    <div>
                        <p className="label-md">24h Change</p>
                        <PnL value={ticker.p} decimals={2} money className="mt-1 text-sm" />
                    </div>
                    <div>
                        <p className="label-md">24h Volume (BTC)</p>
                        <Value value={ticker.v} decimals={2} className="mt-1 block text-sm text-foreground" />
                    </div>
                </div>
            </div>
        </Card>
    )
}
