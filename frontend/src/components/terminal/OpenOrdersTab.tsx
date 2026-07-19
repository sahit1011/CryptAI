"use client"

import { useEffect, useState } from "react"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { useStore } from "@/store/useStore"
import { getOpenOrders, cancelOrder } from "@/lib/api"
import { mapOpenOrders, type OpenOrder } from "@/lib/orders"
import { symbolInfo } from "@/lib/chart/klines"
import { cn } from "@/lib/utils"

/*
 * OpenOrdersTab — the bracket's working legs (SL/TP), live.
 *
 * WS `open_orders` frames are the authoritative set (published by the engine on
 * every portfolio update); a REST seed covers the refresh race. Cancel routes
 * through DELETE /api/orders/{id} — paper cancels settle in the daemon's
 * long-lived engine and the next frame confirms.
 */

function age(updateTime: number): string {
    if (!updateTime) return "—"
    const ms = Date.now() - updateTime
    if (!Number.isFinite(ms) || ms < 0) return "—"
    const m = Math.floor(ms / 60000)
    if (m < 1) return "just now"
    if (m < 60) return `${m}m`
    const h = Math.floor(m / 60)
    return h < 48 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}d`
}

/** What the order does in bracket terms — traders read intent, not API enums. */
function intentOf(order: OpenOrder): string {
    const t = order.type.toUpperCase()
    if (t.includes("STOP")) return "Stop loss"
    if (t === "LIMIT" && order.reduceOnly) return "Take profit"
    if (t === "LIMIT") return "Limit entry"
    return t || "Order"
}

export function OpenOrdersTab() {
    const openOrders = useStore((s) => s.openOrders)
    const setOpenOrders = useStore((s) => s.setOpenOrders)
    const [canceling, setCanceling] = useState<string | null>(null)
    const [cancelError, setCancelError] = useState<string | null>(null)

    // REST seed once — WS frames overwrite with the authoritative set.
    useEffect(() => {
        let cancelled = false
        if (useStore.getState().openOrders.length > 0) return
        getOpenOrders().then(({ orders }) => {
            if (cancelled) return
            const mapped = mapOpenOrders(orders)
            if (mapped.length > 0 && useStore.getState().openOrders.length === 0) {
                setOpenOrders(mapped)
            }
        }).catch(() => { /* seed is best-effort; WS frames cover it */ })
        return () => { cancelled = true }
    }, [setOpenOrders])

    const cancel = async (order: OpenOrder) => {
        setCanceling(order.orderId)
        setCancelError(null)
        try {
            const result = await cancelOrder(order.orderId, order.symbol)
            if (result.canceled === false) {
                setCancelError(typeof result.error === "string" ? result.error : "Cancel was refused.")
            }
            // Success: the authoritative removal arrives on the next open_orders frame.
        } catch (e) {
            setCancelError(e instanceof Error ? e.message : "Cancel failed")
        }
        setCanceling(null)
    }

    if (openOrders.length === 0) {
        return (
            <EmptyState
                title="No working orders"
                description="A bracket's resting legs — stop loss and take-profits — appear here the moment it books, and leave as they fill or cancel."
            />
        )
    }

    return (
        <div className="min-w-0 overflow-x-auto">
            {cancelError && <p className="px-3 pt-2 text-[11px] text-loss">{cancelError}</p>}
            <table className="w-full min-w-[720px] border-collapse">
                <thead>
                    <tr className="border-b border-border">
                        {["Symbol", "Intent", "Side", "Qty", "Limit", "Trigger", "Status", "Age", ""].map((h) => (
                            <th key={h} className="label-md px-3 py-1.5 text-left font-medium text-subtle-foreground">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-border">
                    {openOrders.map((o) => {
                        const info = symbolInfo(o.symbol)
                        return (
                            <tr key={o.orderId} className="h-7 hover:bg-elevated/60">
                                <td className="px-3 text-xs font-semibold text-foreground">{o.symbol}</td>
                                <td className="px-3">
                                    <span className={cn(
                                        "text-[11px]",
                                        intentOf(o) === "Stop loss" ? "text-loss" : intentOf(o) === "Take profit" ? "text-profit" : "text-muted-foreground",
                                    )}>
                                        {intentOf(o)}
                                    </span>
                                </td>
                                <td className="px-3">
                                    <span className={cn(
                                        "rounded-sm border px-1 py-px text-[9px] font-medium uppercase tracking-wider",
                                        o.side === "BUY" ? "border-profit/30 bg-profit/10 text-profit" : "border-loss/30 bg-loss/10 text-loss",
                                    )}>
                                        {o.side}
                                    </span>
                                </td>
                                <td className="px-3"><Value className="text-[11px] text-muted-foreground" value={o.qty} decimals={info.volumePrecision} /></td>
                                <td className="px-3"><Value className="text-[11px] text-foreground" value={o.price > 0 ? o.price : undefined} decimals={info.pricePrecision} placeholder="—" /></td>
                                <td className="px-3"><Value className="text-[11px] text-warning" value={o.stopPrice > 0 ? o.stopPrice : undefined} decimals={info.pricePrecision} placeholder="—" /></td>
                                <td className="px-3"><span className="num text-[10px] uppercase tracking-wider text-subtle-foreground">{o.status}</span></td>
                                <td className="px-3"><span className="num text-[11px] text-subtle-foreground">{age(o.updateTime)}</span></td>
                                <td className="px-3 text-right">
                                    <button
                                        disabled={canceling === o.orderId}
                                        onClick={() => void cancel(o)}
                                        className="rounded-sm border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors duration-150 hover:border-loss/30 hover:text-loss disabled:opacity-50"
                                    >
                                        {canceling === o.orderId ? "Canceling…" : "Cancel"}
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
