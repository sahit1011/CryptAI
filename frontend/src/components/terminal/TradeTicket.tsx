"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Plus, X, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { useTerminalStore } from "@/store/useTerminalStore"
import { useStore } from "@/store/useStore"
import { getSettings, executeSetup, type TradingMode } from "@/lib/api"
import { validateTicket, riskReward, stopDistancePct, toExecutePayload, type TicketDraft } from "@/lib/ticket"
import { symbolInfo } from "@/lib/chart/klines"
import { ConfirmRouteDialog } from "./ConfirmRouteDialog"
import { cn } from "@/lib/utils"

/*
 * TradeTicket — a BRACKET ticket. The risk gate owns sizing (no qty field,
 * ever); the trader owns geometry: direction, entry, stop, up to three TPs.
 *
 * Per mode:
 *   paper  → "Simulate bracket": ONE click, no dialog — simulated fills don't
 *            deserve friction.
 *   manual → "Review & route": confirm dialog with the bracket recap, exchange,
 *            TESTNET badge and the user's masked key. The confirm step is the
 *            brand's trust contract.
 *   auto   → inputs replaced: the desk trades this account; you watch.
 *   off    → honest empty state linking to Settings.
 */

const MAX_TPS = 3
const SUCCESS_HOLD_MS = 4000

type SubmitState =
    | { kind: "idle" }
    | { kind: "pending" }
    | { kind: "success"; message: string }
    | { kind: "error"; message: string }

export function TradeTicket() {
    const symbol = useTerminalStore((s) => s.symbol)
    const prefill = useTerminalStore((s) => s.ticketPrefill)
    const setTicketPrefill = useTerminalStore((s) => s.setTicketPrefill)
    const tickers = useTerminalStore((s) => s.tickers)
    const info = symbolInfo(symbol)

    const [mode, setMode] = useState<TradingMode | null>(null)
    const [direction, setDirection] = useState<"LONG" | "SHORT">("LONG")
    const [entry, setEntry] = useState("")
    const [stopLoss, setStopLoss] = useState("")
    const [tps, setTps] = useState<string[]>(["", ""])
    const [isConfirmOpen, setConfirmOpen] = useState(false)
    const [submit, setSubmit] = useState<SubmitState>({ kind: "idle" })
    // Present only when the draft was loaded from an AI setup (keeps machine
    // scores flowing to the risk gate; hand-built brackets omit it).
    const [aiConfidence, setAiConfidence] = useState<number | undefined>(undefined)

    // Trading mode: load once, refresh on tab focus (Settings may change it).
    useEffect(() => {
        let stopped = false
        const load = () => getSettings().then((s) => { if (!stopped) setMode(s.trading_mode) }).catch(() => { if (!stopped) setMode("paper") })
        void load()
        const onVisible = () => { if (document.visibilityState === "visible") void load() }
        document.addEventListener("visibilitychange", onVisible)
        return () => { stopped = true; document.removeEventListener("visibilitychange", onVisible) }
    }, [])

    // Consume prefills (book row click / AI setup Execute). Deferred, not sync-in-effect.
    useEffect(() => {
        if (!prefill) return
        const t = setTimeout(() => {
            if (prefill.direction) setDirection(prefill.direction)
            if (prefill.entry != null) setEntry(String(prefill.entry))
            if (prefill.stopLoss != null) setStopLoss(String(prefill.stopLoss))
            if (prefill.takeProfits && prefill.takeProfits.length > 0) {
                setTps(prefill.takeProfits.slice(0, MAX_TPS).map(String))
            }
            setAiConfidence(prefill.signalId != null ? prefill.confidence : undefined)
            setSubmit({ kind: "idle" })
        }, 0)
        return () => clearTimeout(t)
    }, [prefill])

    const draft: TicketDraft = useMemo(() => ({
        direction,
        entry: Number(entry),
        stopLoss: Number(stopLoss),
        takeProfits: tps.map(Number).filter((n) => Number.isFinite(n) && n > 0),
    }), [direction, entry, stopLoss, tps])

    const hasInput = entry !== "" || stopLoss !== "" || tps.some((t) => t !== "")
    const errors = useMemo(() => (hasInput ? validateTicket(draft) : []), [draft, hasInput])
    const isValid = hasInput && errors.length === 0
    const rr = riskReward(draft)
    const stopPct = stopDistancePct(draft)

    const doSubmit = useCallback(async () => {
        setSubmit({ kind: "pending" })
        try {
            const result = await executeSetup(toExecutePayload(symbol, draft, aiConfidence))
            const isLive = Boolean((result as { live?: boolean }).live)
            const approved = (result as { approved?: boolean }).approved !== false
            const reasons = (result as { reasons?: string[] }).reasons
            if (!approved) {
                setSubmit({ kind: "error", message: `Risk gate rejected: ${(reasons ?? ["no reason given"]).join("; ")}` })
                return false
            }
            const message = isLive ? "Bracket routed to the exchange" : "Simulated bracket placed"
            setSubmit({ kind: "success", message })
            useStore.getState().addLog({
                id: crypto.randomUUID(),
                timestamp: new Date().toLocaleTimeString(),
                agent: "EXECUTION",
                message: `${message}: ${direction} ${symbol} @ ${draft.entry}`,
                severity: "success",
            })
            setTicketPrefill(null)
            setTimeout(() => setSubmit((s) => (s.kind === "success" ? { kind: "idle" } : s)), SUCCESS_HOLD_MS)
            return true
        } catch (e) {
            setSubmit({ kind: "error", message: e instanceof Error ? e.message : "Placement failed" })
            return false
        }
    }, [symbol, draft, direction, aiConfidence, setTicketPrefill])

    if (mode === null) {
        return <div className="h-[300px] animate-pulse bg-surface" />
    }

    if (mode === "off") {
        return (
            <EmptyState
                className="py-10"
                title="Trading is off"
                description="Turn on a mode in Settings to arm the ticket — paper for virtual funds, manual to route your own brackets."
            >
                <Link href="/dashboard?section=settings" className="text-xs text-accent-300 underline-offset-4 hover:underline">
                    Open Settings
                </Link>
            </EmptyState>
        )
    }

    if (mode === "auto") {
        return (
            <div className="flex flex-col gap-3 p-4">
                <div className="flex h-6 items-center justify-between">
                    <span className="label-md text-subtle-foreground">Trade ticket</span>
                    <span className="rounded-sm border border-accent/30 bg-accent-muted px-1.5 py-px text-[10px] font-medium uppercase tracking-wider text-accent-300">auto</span>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                    AUTO — the desk trades this account. Every approved setup books through your
                    risk gate without a click. You watch; the Wire narrates.
                </p>
                <p className="text-[11px] text-subtle-foreground">
                    Newest setups appear in the AI tab — plot one to see its levels on the chart.
                </p>
            </div>
        )
    }

    const last = tickers[symbol]?.last

    return (
        <div className="flex flex-col gap-2.5 p-3">
            <div className="flex h-5 items-center justify-between">
                <span className="label-md text-subtle-foreground">Trade ticket · bracket</span>
                <span
                    className="flex items-center gap-1 text-[10px] text-subtle-foreground"
                    title="Position size is computed by the deterministic risk gate at placement — the ticket has no quantity field by design."
                >
                    <ShieldCheck className="size-3" /> risk-gate sized
                </span>
            </div>

            {/* Direction — success/destructive tints, never solid fills. */}
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border">
                {(["LONG", "SHORT"] as const).map((d) => (
                    <button
                        key={d}
                        onClick={() => setDirection(d)}
                        className={cn(
                            "py-1.5 text-xs font-semibold transition-colors duration-150",
                            direction === d
                                ? d === "LONG" ? "bg-profit-muted text-profit" : "bg-loss-muted text-loss"
                                : "bg-surface text-muted-foreground hover:text-foreground",
                        )}
                    >
                        {d}
                    </button>
                ))}
            </div>

            <Field label="Entry" htmlFor="ticket-entry">
                <Input
                    id="ticket-entry"
                    inputMode="decimal"
                    placeholder={last ? last.toFixed(info.pricePrecision) : "0.0"}
                    value={entry}
                    onChange={(e) => setEntry(e.target.value)}
                    className="num h-7 text-xs"
                />
            </Field>
            <Field label="Stop loss" htmlFor="ticket-stop">
                <Input
                    id="ticket-stop"
                    inputMode="decimal"
                    placeholder="0.0"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    className="num h-7 text-xs"
                />
            </Field>

            {tps.map((tp, i) => (
                <Field key={i} label={`TP${i + 1}`} htmlFor={`ticket-tp-${i}`}>
                    <div className="flex gap-1">
                        <Input
                            id={`ticket-tp-${i}`}
                            inputMode="decimal"
                            placeholder="0.0"
                            value={tp}
                            onChange={(e) => setTps((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))}
                            className="num h-7 flex-1 text-xs"
                        />
                        {tps.length > 1 && (
                            <button
                                aria-label={`Remove TP${i + 1}`}
                                onClick={() => setTps((prev) => prev.filter((_, j) => j !== i))}
                                className="flex w-6 items-center justify-center rounded-md border border-border text-subtle-foreground transition-colors duration-150 hover:text-loss"
                            >
                                <X className="size-3" />
                            </button>
                        )}
                    </div>
                </Field>
            ))}
            {tps.length < MAX_TPS && (
                <button
                    onClick={() => setTps((prev) => [...prev, ""])}
                    className="flex items-center gap-1 self-start text-[11px] text-subtle-foreground transition-colors duration-150 hover:text-foreground"
                >
                    <Plus className="size-3" /> Add take-profit
                </button>
            )}

            {/* Computed preview — the gate owns size. */}
            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-border bg-border">
                <Cell label="R:R (TP1)">
                    <Value className="text-xs text-foreground" value={Number.isFinite(rr) ? rr : undefined} decimals={2} placeholder="—" />
                </Cell>
                <Cell label="Stop dist.">
                    <Value className="text-xs text-foreground" value={Number.isFinite(stopPct) ? stopPct : undefined} decimals={2} suffix="%" placeholder="—" />
                </Cell>
                <Cell label="Size">
                    <span className="text-[10px] leading-4 text-subtle-foreground">risk gate</span>
                </Cell>
            </div>

            {errors.length > 0 && (
                <ul className="space-y-0.5">
                    {errors.map((e) => (
                        <li key={e} className="text-[11px] leading-snug text-loss">{e}</li>
                    ))}
                </ul>
            )}
            {submit.kind === "error" && (
                <p className="text-[11px] leading-snug text-loss">{submit.message}</p>
            )}
            {submit.kind === "success" && (
                <p className="text-[11px] leading-snug text-profit">{submit.message}</p>
            )}

            {mode === "paper" ? (
                <Button
                    size="sm"
                    disabled={!isValid || submit.kind === "pending"}
                    onClick={() => void doSubmit()}
                    className="h-8 text-xs"
                >
                    {submit.kind === "pending" ? "Placing…" : "Simulate bracket"}
                </Button>
            ) : (
                <>
                    <Button
                        size="sm"
                        disabled={!isValid || submit.kind === "pending"}
                        onClick={() => setConfirmOpen(true)}
                        className="h-8 text-xs"
                    >
                        Review &amp; route
                    </Button>
                    <ConfirmRouteDialog
                        open={isConfirmOpen}
                        onOpenChange={setConfirmOpen}
                        symbol={symbol}
                        draft={draft}
                        pricePrecision={info.pricePrecision}
                        onConfirm={doSubmit}
                    />
                </>
            )}
        </div>
    )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center gap-2">
            <label htmlFor={htmlFor} className="label-md w-16 shrink-0 text-subtle-foreground">{label}</label>
            <div className="flex-1">{children}</div>
        </div>
    )
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col items-center gap-0.5 bg-surface px-1 py-1.5">
            <span className="text-[9px] uppercase tracking-wider text-subtle-foreground">{label}</span>
            {children}
        </div>
    )
}
