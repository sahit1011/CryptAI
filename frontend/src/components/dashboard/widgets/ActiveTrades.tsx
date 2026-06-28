"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { GlassCard } from "@/components/ui/glass-card"
import { useStore } from "@/store/useStore"
import { API_URL, apiHeaders } from "@/lib/api"
import { safeNum, safeFixed } from "@/lib/utils"

export function ActiveTrades() {
    const { activeTrades } = useStore()
    const [closing, setClosing] = useState(false)
    const [closeError, setCloseError] = useState<string | null>(null)

    // The backend exposes a single emergency control: POST /api/close-positions
    // dispatches a panic-close that reduces ALL open positions (there is no
    // per-position close endpoint). The button is therefore an "all positions"
    // control and is labelled as such so it never implies a single-position close.
    const handleCloseAll = async () => {
        if (closing) return
        const confirmed = window.confirm(
            "This closes ALL open positions via the backend's emergency control. Continue?"
        )
        if (!confirmed) return

        setClosing(true)
        setCloseError(null)
        try {
            const response = await fetch(`${API_URL}/api/close-positions`, {
                method: "POST",
                headers: apiHeaders(true),
            })
            if (!response.ok) {
                // 503 here means the backend has no API_AUTH_TOKEN configured, so
                // the destructive endpoint is intentionally disabled (fail-closed).
                const detail = await response.text().catch(() => "")
                throw new Error(`HTTP ${response.status}${detail ? `: ${detail}` : ""}`)
            }
            // Positions clear via the live WebSocket position feed once the
            // execution agent confirms the reduce-only close.
        } catch (e) {
            console.error("Failed to dispatch close-all-positions:", e)
            setCloseError(e instanceof Error ? e.message : String(e))
        } finally {
            setClosing(false)
        }
    }

    return (
        <GlassCard className="overflow-hidden">
            <div className="p-4 border-b border-white/5 flex items-center justify-between">
                <h3 className="font-semibold text-white">Active Positions</h3>
                <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleCloseAll}
                    disabled={closing || activeTrades.length === 0}
                    className="h-7 text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20"
                >
                    {closing ? "Closing…" : "Close All"}
                </Button>
            </div>
            {closeError && (
                <div className="px-4 py-2 text-xs text-red-400 border-b border-white/5">
                    Failed to close positions: {closeError}
                </div>
            )}
            <Table>
                <TableHeader className="bg-white/5">
                    <TableRow className="border-white/5 hover:bg-transparent">
                        <TableHead className="text-muted-foreground">Symbol</TableHead>
                        <TableHead className="text-muted-foreground">Side</TableHead>
                        <TableHead className="text-muted-foreground">Entry</TableHead>
                        <TableHead className="text-muted-foreground">Current</TableHead>
                        <TableHead className="text-muted-foreground text-right">PnL</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {activeTrades.length === 0 && (
                        <TableRow className="border-white/5 hover:bg-transparent">
                            <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                                No active positions
                            </TableCell>
                        </TableRow>
                    )}
                    {activeTrades.map((trade, index) => (
                        <TableRow key={`${trade.id}-${index}`} className="border-white/5 hover:bg-white/5 transition-colors">
                            <TableCell className="font-medium text-white">{trade.symbol}</TableCell>
                            <TableCell>
                                <Badge variant="outline" className={trade.side === 'LONG' ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"}>
                                    {trade.side}
                                </Badge>
                            </TableCell>
                            <TableCell className="text-muted-foreground font-mono">${safeNum(trade.entry).toLocaleString()}</TableCell>
                            <TableCell className="text-muted-foreground font-mono">${safeNum(trade.current).toLocaleString()}</TableCell>
                            <TableCell className={`text-right font-mono ${safeNum(trade.pnl) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                ${safeFixed(trade.pnl, 2)} ({safeFixed(trade.pnlPercent, 2)}%)
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </GlassCard>
    )
}
