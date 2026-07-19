"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { getExchangeKeys, type ExchangeKeyStatus } from "@/lib/api"
import type { TicketDraft } from "@/lib/ticket"
import { riskReward } from "@/lib/ticket"

/*
 * ConfirmRouteDialog — the manual mode's trust contract. Before a bracket
 * routes to a real exchange API the trader sees exactly what goes out: the
 * bracket recap, the venue, the TESTNET badge, and WHICH key signs it (masked).
 * Backend errors surface inside the dialog — it never closes silently.
 */

export function ConfirmRouteDialog({
    open,
    onOpenChange,
    symbol,
    draft,
    pricePrecision,
    onConfirm,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    symbol: string
    draft: TicketDraft
    pricePrecision: number
    /** Returns true on success (dialog closes), false on failure (stays open). */
    onConfirm: () => Promise<boolean>
}) {
    const [keys, setKeys] = useState<ExchangeKeyStatus | null | "loading">("loading")
    const [isRouting, setRouting] = useState(false)
    const [routeError, setRouteError] = useState<string | null>(null)

    useEffect(() => {
        if (!open) return
        // Deferred (not sync-in-effect): reset then load the key status.
        let cancelled = false
        const t = setTimeout(() => {
            setKeys("loading")
            setRouteError(null)
            getExchangeKeys()
                .then((k) => { if (!cancelled) setKeys(k) })
                .catch(() => { if (!cancelled) setKeys(null) })
        }, 0)
        return () => { cancelled = true; clearTimeout(t) }
    }, [open])

    const rr = riskReward(draft)
    const hasKeys = keys !== "loading" && keys !== null && keys.connected

    const confirm = async () => {
        setRouting(true)
        setRouteError(null)
        const ok = await onConfirm()
        setRouting(false)
        if (ok) onOpenChange(false)
        else setRouteError("Routing failed — the exchange's reason is shown on the ticket.")
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!isRouting) onOpenChange(v) }}>
            <DialogContent className="max-w-sm">
                <DialogHeader>
                    <DialogTitle>Route bracket to exchange</DialogTitle>
                    <DialogDescription>
                        The risk gate sizes the position at placement; entry, stop and targets go out exactly as below.
                    </DialogDescription>
                </DialogHeader>

                {keys === "loading" ? (
                    <div className="h-32 animate-pulse rounded-md bg-elevated" />
                ) : !hasKeys ? (
                    <EmptyState
                        title="No exchange keys connected"
                        description="Connect BingX testnet keys in Settings to route manual orders. Until then, brackets can only be simulated."
                    >
                        <Link href="/dashboard?section=settings" className="text-xs text-accent-300 underline-offset-4 hover:underline">
                            Open Settings
                        </Link>
                    </EmptyState>
                ) : (
                    <div className="space-y-3">
                        {/* Bracket recap */}
                        <div className="overflow-hidden rounded-md border border-border">
                            <Row label="Symbol"><span className="text-xs font-semibold text-foreground">{symbol}</span></Row>
                            <Row label="Direction">
                                <span className={draft.direction === "LONG" ? "text-xs font-semibold text-profit" : "text-xs font-semibold text-loss"}>
                                    {draft.direction}
                                </span>
                            </Row>
                            <Row label="Entry"><Value className="text-xs text-foreground" value={draft.entry} decimals={pricePrecision} /></Row>
                            <Row label="Stop loss"><Value className="text-xs text-loss" value={draft.stopLoss} decimals={pricePrecision} /></Row>
                            {draft.takeProfits.map((tp, i) => (
                                <Row key={i} label={`TP${i + 1}`}><Value className="text-xs text-profit" value={tp} decimals={pricePrecision} /></Row>
                            ))}
                            <Row label="R:R (TP1)"><Value className="text-xs text-foreground" value={Number.isFinite(rr) ? rr : undefined} decimals={2} placeholder="—" /></Row>
                            <Row label="Size"><span className="text-[11px] text-subtle-foreground">computed by risk gate</span></Row>
                        </div>

                        {/* Venue + signing key */}
                        <div className="flex items-center justify-between rounded-md border border-border bg-elevated px-3 py-2">
                            <div className="flex flex-col">
                                <span className="text-xs font-medium uppercase text-foreground">{keys.exchange ?? "bingx"}</span>
                                <span className="num text-[10px] text-subtle-foreground">{keys.api_key_masked ?? "key on file"}</span>
                            </div>
                            {keys.is_testnet !== false && (
                                <span className="rounded-sm border border-warning/30 bg-warning-muted px-1.5 py-px text-[10px] font-medium uppercase tracking-wider text-warning">
                                    testnet
                                </span>
                            )}
                        </div>
                    </div>
                )}

                {routeError && <p className="text-[11px] leading-snug text-loss">{routeError}</p>}

                <DialogFooter>
                    <Button variant="ghost" size="sm" disabled={isRouting} onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button size="sm" disabled={!hasKeys || isRouting} onClick={() => void confirm()}>
                        {isRouting ? "Routing…" : "Route bracket"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between border-b border-border bg-surface px-3 py-1.5 last:border-b-0">
            <span className="label-md text-subtle-foreground">{label}</span>
            {children}
        </div>
    )
}
