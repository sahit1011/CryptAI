"use client"

import { useMemo, useState } from "react"
import { Value, PnL } from "@/components/ui/value"
import { EmptyState, LoadingState, ErrorState } from "@/components/ui/states"
import { useClosedTrades } from "@/hooks/useClosedTrades"
import { computeTradeStats } from "@/lib/tradeStats"
import { symbolInfo } from "@/lib/chart/klines"
import { cn } from "@/lib/utils"

/*
 * HistoryTab — realized performance: a stat strip derived from every closed
 * trade, then the tape itself. Per-symbol filter chips; a row expands to the
 * strategy/exit detail.
 */

export function HistoryTab() {
    const { closed, loading, error } = useClosedTrades(200)
    const [symbolFilter, setSymbolFilter] = useState<string | null>(null)
    const [expandedId, setExpandedId] = useState<string | null>(null)

    const stats = useMemo(() => computeTradeStats(closed), [closed])
    const rows = useMemo(
        () => (symbolFilter ? closed.filter((t) => t.symbol === symbolFilter) : closed),
        [closed, symbolFilter],
    )

    if (loading && closed.length === 0) return <LoadingState title="Loading trade history…" />
    if (error && closed.length === 0) {
        return <ErrorState title="History unavailable" description="The trades API didn't answer." error={error} />
    }
    if (closed.length === 0) {
        return (
            <EmptyState
                title="No closed trades yet"
                description="Realized performance builds here as brackets exit — take-profit, stop, or manual close."
            />
        )
    }

    return (
        <div className="flex flex-col">
            {/* Realized stat strip — one bordered gap-px band. */}
            <div className="grid shrink-0 grid-cols-3 gap-px border-b border-border bg-border md:grid-cols-6">
                <Stat label="Realized P&L"><PnL className="text-sm" value={stats.realizedPnl} money decimals={2} /></Stat>
                <Stat label="Win rate"><Value className="text-sm text-foreground" value={stats.winRate} decimals={0} suffix="%" /></Stat>
                <Stat label="Profit factor"><Value className="text-sm text-foreground" value={Number.isFinite(stats.profitFactor) ? stats.profitFactor : undefined} decimals={2} placeholder="—" /></Stat>
                <Stat label="Best / worst">
                    <span className="flex items-baseline gap-1.5">
                        <PnL className="text-xs" value={stats.best} money decimals={0} />
                        <PnL className="text-xs" value={stats.worst} money decimals={0} />
                    </span>
                </Stat>
                <Stat label="Avg win"><PnL className="text-sm" value={stats.avgWin} money decimals={2} /></Stat>
                <Stat label="Avg loss"><PnL className="text-sm" value={-Math.abs(stats.avgLoss)} money decimals={2} /></Stat>
            </div>

            {/* Symbol filter chips (only symbols that actually traded). */}
            {stats.perSymbol.length > 1 && (
                <div className="flex shrink-0 items-center gap-1 border-b border-border px-3 py-1.5">
                    <FilterChip active={symbolFilter === null} onClick={() => setSymbolFilter(null)}>All</FilterChip>
                    {stats.perSymbol.map((s) => (
                        <FilterChip key={s.symbol} active={symbolFilter === s.symbol} onClick={() => setSymbolFilter(s.symbol)}>
                            {s.symbol}
                        </FilterChip>
                    ))}
                </div>
            )}

            <div className="min-w-0 overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse">
                    <thead>
                        <tr className="border-b border-border">
                            {["Symbol", "Side", "Entry", "Exit", "P&L", "P&L %", "Exit reason", "Strategy"].map((h) => (
                                <th key={h} className="label-md px-3 py-1.5 text-left font-medium text-subtle-foreground">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {rows.map((t) => {
                            const info = symbolInfo(t.symbol)
                            const isExpanded = expandedId === t.id
                            return (
                                <FragmentRow key={t.id}>
                                    <tr
                                        className="h-7 cursor-pointer hover:bg-elevated/60"
                                        onClick={() => setExpandedId(isExpanded ? null : t.id)}
                                    >
                                        <td className="px-3 text-xs font-semibold text-foreground">{t.symbol}</td>
                                        <td className="px-3">
                                            <span className={cn(
                                                "rounded-sm border px-1 py-px text-[9px] font-medium uppercase tracking-wider",
                                                t.side === "LONG" ? "border-profit/30 bg-profit/10 text-profit" : "border-loss/30 bg-loss/10 text-loss",
                                            )}>
                                                {t.side}
                                            </span>
                                        </td>
                                        <td className="px-3"><Value className="text-[11px] text-muted-foreground" value={t.entry} decimals={info.pricePrecision} /></td>
                                        <td className="px-3"><Value className="text-[11px] text-muted-foreground" value={t.current} decimals={info.pricePrecision} /></td>
                                        <td className="px-3"><PnL className="text-[11px]" value={t.pnl} money decimals={2} /></td>
                                        <td className="px-3"><PnL className="text-[11px]" value={t.pnlPercent} decimals={2} suffix="%" /></td>
                                        <td className="px-3"><span className="num text-[11px] text-subtle-foreground">{t.exitReason ?? "—"}</span></td>
                                        <td className="px-3"><span className="text-[11px] text-subtle-foreground">{t.strategy ?? "—"}</span></td>
                                    </tr>
                                    {isExpanded && (
                                        <tr className="bg-elevated/40">
                                            <td colSpan={8} className="px-3 py-2">
                                                <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted-foreground">
                                                    {t.entryTime && <span>Opened <span className="num">{new Date(t.entryTime).toLocaleString()}</span></span>}
                                                    {t.exitTime && <span>Closed <span className="num">{new Date(t.exitTime).toLocaleString()}</span></span>}
                                                    {t.leverage != null && <span>Leverage <span className="num">{t.leverage}x</span></span>}
                                                    {t.confidence != null && <span>Confidence <span className="num">{Math.round(t.confidence * 100)}%</span></span>}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </FragmentRow>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

// React needs a keyed wrapper for the row+detail pair; a plain fragment can't
// carry the hover group, so this is a pass-through.
function FragmentRow({ children }: { children: React.ReactNode }) {
    return <>{children}</>
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col gap-0.5 bg-surface px-3 py-2">
            <span className="text-[9px] uppercase tracking-wider text-subtle-foreground">{label}</span>
            {children}
        </div>
    )
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
    return (
        <button
            onClick={onClick}
            className={cn(
                "num rounded-sm border px-1.5 py-0.5 text-[10px] transition-colors duration-150",
                active ? "border-accent/40 bg-accent-muted text-accent-300" : "border-border text-muted-foreground hover:text-foreground",
            )}
        >
            {children}
        </button>
    )
}
