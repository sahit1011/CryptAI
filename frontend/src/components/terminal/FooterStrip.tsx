"use client"

import { useEffect, useState } from "react"
import { Value, PnL } from "@/components/ui/value"
import { useStore } from "@/store/useStore"

/*
 * FooterStrip — 28px account strip: equity · balance · unrealized · realized ·
 * win rate · trades, plus the data-provenance legend and a UTC/IST clock.
 * Numbers come from the live portfolio (WS balance frames / REST seed) — never
 * invented.
 */

export function FooterStrip() {
    const portfolio = useStore((s) => s.portfolio)
    const hasData = portfolio.totalValue > 0 || portfolio.balance > 0

    return (
        <footer className="flex h-7 shrink-0 items-center justify-between border-t border-border bg-surface pl-3 pr-3">
            <div className="flex min-w-0 items-center divide-x divide-border overflow-x-auto">
                {hasData ? (
                    <>
                        <Cell label="Equity"><Value className="text-[11px] text-foreground" value={portfolio.totalValue} money decimals={2} /></Cell>
                        <Cell label="Balance"><Value className="text-[11px] text-muted-foreground" value={portfolio.balance} money decimals={2} /></Cell>
                        <Cell label="uPnL"><PnL className="text-[11px]" value={portfolio.unrealizedPnl} money decimals={2} /></Cell>
                        <Cell label="Realized"><PnL className="text-[11px]" value={portfolio.realizedPnl} money decimals={2} /></Cell>
                        <Cell label="Win"><Value className="text-[11px] text-muted-foreground" value={portfolio.winRate} decimals={0} suffix="%" /></Cell>
                        <Cell label="Trades"><Value className="text-[11px] text-muted-foreground" value={portfolio.totalTrades} decimals={0} /></Cell>
                        {portfolio.mode && (
                            <Cell label="Account">
                                <span className="text-[10px] font-medium uppercase tracking-wider text-info">{portfolio.mode}</span>
                            </Cell>
                        )}
                    </>
                ) : (
                    <span className="px-2 text-[11px] text-subtle-foreground">Waiting for account data…</span>
                )}
            </div>

            <div className="flex shrink-0 items-center gap-3">
                <span className="hidden text-[10px] text-subtle-foreground lg:block" title="Data provenance — what streams vs polls">
                    BTC live · ETH/Gold 5s poll
                </span>
                <Clock />
            </div>
        </footer>
    )
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <span className="flex shrink-0 items-baseline gap-1.5 px-2.5 first:pl-0">
            <span className="label-md text-subtle-foreground">{label}</span>
            {children}
        </span>
    )
}

function Clock() {
    const [now, setNow] = useState<Date | null>(null)
    useEffect(() => {
        // Deferred (not sync-in-effect): first tick lands on the next task.
        const t = setTimeout(() => setNow(new Date()), 0)
        const id = setInterval(() => setNow(new Date()), 30_000)
        return () => { clearTimeout(t); clearInterval(id) }
    }, [])
    if (!now) return null
    const utc = now.toLocaleTimeString("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit" })
    const ist = now.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })
    return (
        <span className="num text-[10px] text-subtle-foreground">
            UTC {utc} · IST {ist}
        </span>
    )
}
