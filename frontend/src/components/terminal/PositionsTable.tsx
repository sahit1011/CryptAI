"use client"

import { useEffect, useState } from "react"
import { Value, PnL } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { useStore, type Trade } from "@/store/useStore"
import { API_URL, authHeaders } from "@/lib/api"
import { symbolInfo } from "@/lib/chart/klines"
import { safeNum, cn } from "@/lib/utils"

/*
 * PositionsTable — live positions with running P&L. WS position frames are the
 * authoritative set; a REST seed covers the refresh race. Close routes through
 * POST /api/positions/close (per-user, per-position) — NEVER the global panic
 * control. If the close API isn't deployed yet the button explains itself
 * instead of pretending.
 */

async function seedOpenTrades(): Promise<Trade[]> {
    const res = await fetch(`${API_URL}/api/trades?limit=100`, { headers: await authHeaders(), cache: "no-store" })
    if (!res.ok) return []
    const data = await res.json()
    const rows: Record<string, unknown>[] = Array.isArray(data?.trades) ? data.trades : []
    return rows
        .filter((t) => t.status === "OPEN")
        .map((t) => ({
            id: String(t.id ?? `${t.symbol}-seed`),
            symbol: String(t.symbol ?? ""),
            side: (t.side as Trade["side"]) ?? "LONG",
            entry: safeNum(t.entry),
            current: safeNum(t.current),
            pnl: safeNum(t.pnl),
            pnlPercent: safeNum(t.pnlPercent),
            status: "OPEN" as const,
            entryTime: t.entryTime as string | undefined,
            strategy: t.strategy as string | undefined,
            leverage: t.leverage != null ? safeNum(t.leverage) : undefined,
        }))
}

function age(entryTime?: string): string {
    if (!entryTime) return "—"
    const ms = Date.now() - new Date(entryTime).getTime()
    if (!Number.isFinite(ms) || ms < 0) return "—"
    const m = Math.floor(ms / 60000)
    if (m < 60) return `${m}m`
    const h = Math.floor(m / 60)
    if (h < 48) return `${h}h ${m % 60}m`
    return `${Math.floor(h / 24)}d`
}

export function PositionsTable() {
    const activeTrades = useStore((s) => s.activeTrades)
    const setTrades = useStore((s) => s.setTrades)
    const [closing, setClosing] = useState<string | null>(null)
    const [closeError, setCloseError] = useState<string | null>(null)

    // Seed from REST once — WS frames overwrite with the authoritative set.
    useEffect(() => {
        let cancelled = false
        if (useStore.getState().activeTrades.length > 0) return
        seedOpenTrades().then((trades) => {
            if (cancelled || trades.length === 0) return
            if (useStore.getState().activeTrades.length === 0) setTrades(trades)
        }).catch(() => { /* seed is best-effort */ })
        return () => { cancelled = true }
    }, [setTrades])

    const open = activeTrades.filter((t) => t.status === "OPEN")

    const closePosition = async (trade: Trade) => {
        setClosing(trade.id)
        setCloseError(null)
        try {
            const res = await fetch(`${API_URL}/api/positions/close`, {
                method: "POST",
                headers: await authHeaders(true),
                body: JSON.stringify({ symbol: trade.symbol, position_id: trade.id }),
            })
            if (res.status === 404 || res.status === 405) {
                setCloseError("Per-position close isn't deployed on this backend yet — redeploy the API to enable it.")
            } else if (!res.ok) {
                const body = await res.json().catch(() => null)
                setCloseError(typeof body?.detail === "string" ? body.detail : `Close failed (HTTP ${res.status})`)
            }
            // Success: the authoritative removal arrives on the next position_update frame.
        } catch (e) {
            setCloseError(e instanceof Error ? e.message : "Close failed")
        }
        setClosing(null)
    }

    if (open.length === 0) {
        return (
            <EmptyState
                title="No open positions"
                description="Positions appear here the moment a bracket books — paper fills included. The AI tab shows what the desk is considering."
            />
        )
    }

    return (
        <div className="min-w-0 overflow-x-auto">
            {closeError && <p className="px-3 pt-2 text-[11px] text-loss">{closeError}</p>}
            <table className="w-full min-w-[760px] border-collapse">
                <thead>
                    <tr className="border-b border-border">
                        {["Symbol", "Side", "Entry", "Mark", "uPnL", "uPnL %", "SL", "TP", "Age", ""].map((h) => (
                            <th key={h} className="label-md px-3 py-1.5 text-left font-medium text-subtle-foreground">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-border">
                    {open.map((t) => {
                        const info = symbolInfo(t.symbol)
                        return (
                            <tr key={t.id} className="h-7 hover:bg-elevated/60">
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
                                <td className="px-3"><Value className="text-[11px] text-foreground" value={t.current} decimals={info.pricePrecision} /></td>
                                <td className="px-3"><PnL className="text-[11px]" value={t.pnl} money decimals={2} /></td>
                                <td className="px-3"><PnL className="text-[11px]" value={t.pnlPercent} decimals={2} suffix="%" /></td>
                                <td className="px-3"><Value className="text-[11px] text-loss/80" value={t.stopLoss ?? undefined} decimals={info.pricePrecision} placeholder="—" /></td>
                                <td className="px-3"><Value className="text-[11px] text-profit/80" value={t.takeProfit ?? undefined} decimals={info.pricePrecision} placeholder="—" /></td>
                                <td className="px-3"><span className="num text-[11px] text-subtle-foreground">{age(t.entryTime)}</span></td>
                                <td className="px-3 text-right">
                                    <button
                                        disabled={closing === t.id}
                                        onClick={() => void closePosition(t)}
                                        className="rounded-sm border border-loss/30 bg-loss/10 px-2 py-0.5 text-[10px] font-medium text-loss transition-colors duration-150 hover:bg-loss/20 disabled:opacity-50"
                                    >
                                        {closing === t.id ? "Closing…" : "Close"}
                                    </button>
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}
