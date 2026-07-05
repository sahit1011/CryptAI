"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Inbox, ShieldAlert } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Card } from "@/components/ui/card"
import { Value, PnL } from "@/components/ui/value"
import { ConnectionStatus } from "@/components/ui/connection-status"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states"
import { useStore, type Trade } from "@/store/useStore"
import { useMarketStore } from "@/hooks/useMarketData"
import { closePositions, API_URL, apiHeaders } from "@/lib/api"

/**
 * ActiveTrades — the live open-positions terminal.
 *
 * Data sources (real backend only, never fabricated):
 *   1. WebSocket `position_update` / `update_trade` (see useMarketData) is the
 *      AUTHORITATIVE live feed and is written into `store.activeTrades`.
 *   2. On mount we ALSO seed from `GET /api/trades?limit=50` (OPEN rows) so the
 *      table is populated before the first WS frame arrives. Once the store has
 *      live positions, that store data wins.
 *
 * TODO(multi-tenancy): `GET /api/trades` and the `/ws` feed are currently a single
 * global account. When per-user accounts land, this must scope to the signed-in
 * user's positions (send the Supabase session, filter server-side) so one user
 * never sees another's open risk. Do NOT ship multi-user without that scoping.
 */

function toOpenTrade(raw: unknown): Trade | null {
    const t = (raw ?? {}) as Record<string, unknown>
    const status = String(t.status ?? "OPEN").toUpperCase()
    // Only OPEN rows are "active positions"; closed rows belong in history.
    if (status === "CLOSED" || t.exitTime) return null
    const symbol = String(t.symbol ?? "")
    if (!symbol) return null
    return {
        id: String(t.id ?? t.position_id ?? `${symbol}-open`),
        symbol,
        side: (t.side as Trade["side"]) ?? "LONG",
        entry: Number(t.entry ?? 0),
        current: Number(t.current ?? 0),
        pnl: Number(t.pnl ?? 0),
        pnlPercent: Number(t.pnlPercent ?? 0),
        status: "OPEN",
        entryTime: t.entryTime as string | undefined,
        strategy: t.strategy as string | undefined,
        leverage: t.leverage != null ? Number(t.leverage) : undefined,
    }
}

export function ActiveTrades() {
    const { activeTrades } = useStore()
    const status = useMarketStore((s) => s.status)

    const [seeded, setSeeded] = useState<Trade[]>([])
    const [loading, setLoading] = useState(true)
    const [fetchError, setFetchError] = useState<string | null>(null)

    const [closing, setClosing] = useState(false)
    const [closeError, setCloseError] = useState<string | null>(null)

    // Seed OPEN positions from the REST endpoint until the WS feed takes over.
    const fetchOpen = useCallback(async () => {
        setLoading(true)
        setFetchError(null)
        try {
            const res = await fetch(`${API_URL}/api/trades?limit=50`, {
                cache: "no-store",
                headers: apiHeaders(),
            })
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()
            const list = Array.isArray(data?.trades) ? data.trades : []
            setSeeded(list.map(toOpenTrade).filter((t: Trade | null): t is Trade => t !== null))
        } catch (e) {
            setFetchError(e instanceof Error ? e.message : String(e))
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchOpen()
    }, [fetchOpen])

    // The live WS store wins once it has positions; otherwise fall back to the
    // REST seed. Never merge fabricated data — both branches are real backend rows.
    const rows = useMemo<Trade[]>(
        () => (activeTrades.length > 0 ? activeTrades : seeded),
        [activeTrades, seeded],
    )

    // The backend exposes a single emergency control: POST /api/close-positions
    // dispatches a panic-close that reduces ALL open positions (there is no
    // per-position endpoint). Routed through the SAME-ORIGIN Next server route,
    // which holds the server-only admin secret — the browser never sees it. A 503
    // means CRYPTAI_ADMIN_TOKEN isn't configured (destructive control off).
    const handleCloseAll = useCallback(async () => {
        if (closing) return
        const confirmed = window.confirm(
            "This closes ALL open positions via the backend's emergency control. Continue?",
        )
        if (!confirmed) return

        setClosing(true)
        setCloseError(null)
        try {
            await closePositions()
            // Positions clear via the live WS position feed once the execution
            // agent confirms the reduce-only close.
        } catch (e) {
            console.error("Failed to dispatch close-all-positions:", e)
            setCloseError(e instanceof Error ? e.message : String(e))
        } finally {
            setClosing(false)
        }
    }, [closing])

    const showLoading = loading && rows.length === 0
    const showEmpty = !showLoading && !fetchError && rows.length === 0

    return (
        <Card className="gap-0 overflow-hidden py-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div className="flex items-center gap-3">
                    <h3 className="heading-4 text-foreground">Active Positions</h3>
                    <ConnectionStatus status={status} />
                </div>
                <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleCloseAll}
                    disabled={closing || rows.length === 0}
                >
                    <ShieldAlert />
                    {closing ? "Closing…" : "Close All"}
                </Button>
            </div>

            {closeError && (
                <div className="border-b border-border bg-loss-muted px-4 py-2 text-xs text-loss">
                    Failed to close positions: {closeError}
                </div>
            )}

            {showLoading ? (
                <LoadingState title="Loading positions…" />
            ) : showEmpty ? (
                <EmptyState
                    icon={<Inbox />}
                    title="No open positions"
                    description="Open positions appear here in real time as the execution agent places trades."
                />
            ) : fetchError && rows.length === 0 ? (
                <ErrorState
                    icon={<ShieldAlert />}
                    title="Couldn’t load positions"
                    description="The positions endpoint is unreachable. The live feed will still update this table if it connects."
                    error={fetchError}
                    onRetry={fetchOpen}
                />
            ) : (
                <Table>
                    <TableHeader>
                        <TableRow className="border-border hover:bg-transparent">
                            <TableHead className="text-muted-foreground">Symbol</TableHead>
                            <TableHead className="text-muted-foreground">Side</TableHead>
                            <TableHead className="text-right text-muted-foreground">Entry</TableHead>
                            <TableHead className="text-right text-muted-foreground">Mark</TableHead>
                            <TableHead className="text-right text-muted-foreground">PnL</TableHead>
                            <TableHead className="text-right text-muted-foreground">%</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {rows.map((trade, index) => (
                            <TableRow
                                key={`${trade.id}-${index}`}
                                className="border-border transition-colors hover:bg-elevated"
                            >
                                <TableCell className="font-medium text-foreground">
                                    {trade.symbol}
                                </TableCell>
                                <TableCell>
                                    <Badge variant={trade.side === "LONG" ? "profit" : "loss"}>
                                        {trade.side}
                                    </Badge>
                                </TableCell>
                                <TableCell className="text-right">
                                    <Value value={trade.entry} prefix="$" />
                                </TableCell>
                                <TableCell className="text-right">
                                    <Value value={trade.current} prefix="$" />
                                </TableCell>
                                <TableCell className="text-right">
                                    <PnL value={trade.pnl} prefix="$" />
                                </TableCell>
                                <TableCell className="text-right">
                                    <PnL value={trade.pnlPercent} percent />
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
        </Card>
    )
}
