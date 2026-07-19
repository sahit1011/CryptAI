"use client"

import { useEffect, useMemo, useState } from "react"
import { Value } from "@/components/ui/value"
import { EmptyState } from "@/components/ui/states"
import { useStore, type Signal, type Trade } from "@/store/useStore"
import { useTerminalStore } from "@/store/useTerminalStore"
import { getSetups, getSettings, type TradingMode } from "@/lib/api"
import { payloadToSignal } from "@/lib/signals"
import { symbolInfo } from "@/lib/chart/klines"
import { cn } from "@/lib/utils"

/*
 * SetupCards — the desk's proposals, with the lifecycle grammar made visible:
 *
 *   PROPOSED  — fresh suggestion (dashed levels when plotted)
 *   BOOKED    — a matching position opened (paper/auto booked it, or the
 *               trader routed it); the chart now shows solid position lines
 *   STALE     — superseded for its symbol or >30 min old: card dims, plot
 *               still allowed (it's history, not a lie)
 *
 * Actions: Plot (all modes — draws the levels), Execute (manual only —
 * prefills the ticket and hands the decision to the trader).
 */

const STALE_MS = 30 * 60 * 1000
const MAX_CARDS = 15
const ENTRY_MATCH_TOLERANCE = 0.005 // 0.5%

type Lifecycle = "proposed" | "booked" | "stale"

export function lifecycleOf(signal: Signal, signals: Signal[], openTrades: Trade[], now: number): Lifecycle {
    const booked = openTrades.some(
        (t) =>
            t.status === "OPEN" &&
            t.symbol === signal.symbol &&
            t.side === signal.direction &&
            signal.entry > 0 &&
            Math.abs(t.entry - signal.entry) / signal.entry < ENTRY_MATCH_TOLERANCE,
    )
    if (booked) return "booked"
    const newerExists = signals.some(
        (s) => s.symbol === signal.symbol && s.id !== signal.id &&
            new Date(s.ts).getTime() > new Date(signal.ts).getTime(),
    )
    if (newerExists || now - new Date(signal.ts).getTime() > STALE_MS) return "stale"
    return "proposed"
}

export function SetupCards({ compact = false }: { compact?: boolean }) {
    const signals = useStore((s) => s.signals)
    const addSignal = useStore((s) => s.addSignal)
    const activeTrades = useStore((s) => s.activeTrades)
    const symbol = useTerminalStore((s) => s.symbol)
    const setSymbol = useTerminalStore((s) => s.setSymbol)
    const plottedSignalId = useTerminalStore((s) => s.plottedSignalId)
    const setPlottedSignalId = useTerminalStore((s) => s.setPlottedSignalId)
    const setTicketPrefill = useTerminalStore((s) => s.setTicketPrefill)
    const [mode, setMode] = useState<TradingMode | null>(null)
    // Wall-clock lives in state (render must stay pure); refreshed each minute.
    const [now, setNow] = useState(0)

    // Hydrate shared setups once (WS keeps them live afterwards).
    useEffect(() => {
        let cancelled = false
        getSetups().then(({ setups }) => {
            if (cancelled || !Array.isArray(setups)) return
            for (const raw of [...setups].reverse()) {
                const sig = payloadToSignal(raw)
                if (sig) addSignal(sig)
            }
        }).catch(() => { /* WS hydration replays cover this */ })
        getSettings().then((s) => { if (!cancelled) setMode(s.trading_mode) }).catch(() => { })
        return () => { cancelled = true }
    }, [addSignal])

    // Staleness is time-derived — refresh each minute (deferred initial tick).
    useEffect(() => {
        const t = setTimeout(() => setNow(Date.now()), 0)
        const id = setInterval(() => setNow(Date.now()), 60_000)
        return () => { clearTimeout(t); clearInterval(id) }
    }, [])

    const cards = useMemo(() => signals.slice(0, MAX_CARDS), [signals])

    if (cards.length === 0) {
        return (
            <EmptyState
                title="No setups on the wire"
                description="The desk proposes setups while the engine is on — each one argued by the agents, then risk-checked. Arm the engine to see them arrive."
            />
        )
    }

    const plot = (signal: Signal) => {
        if (signal.symbol !== symbol) setSymbol(signal.symbol)
        setPlottedSignalId(signal.id)
    }

    const execute = (signal: Signal) => {
        setTicketPrefill({
            direction: signal.direction,
            entry: signal.entry,
            stopLoss: signal.stopLoss,
            takeProfits: signal.takeProfits,
            signalId: signal.id,
            confidence: signal.confidence,
        })
        document.getElementById("ticket-entry")?.focus()
    }

    return (
        // compact = the wide layout's 344px command rail: always one column
        // (the viewport-based md/xl breakpoints would wrongly split it).
        <div className={cn("grid gap-px bg-border", compact ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3")}>
            {cards.map((signal) => {
                const state = lifecycleOf(signal, signals, activeTrades, now)
                const info = symbolInfo(signal.symbol)
                const isPlotted = plottedSignalId === signal.id
                return (
                    <div
                        key={signal.id}
                        className={cn(
                            "flex flex-col gap-2 bg-surface p-3 transition-opacity duration-150",
                            state === "stale" && "opacity-60",
                        )}
                    >
                        <div className="flex items-center justify-between">
                            <span className="flex items-center gap-1.5">
                                <span className="text-xs font-semibold text-foreground">{signal.symbol}</span>
                                <span className={cn(
                                    "rounded-sm border px-1 py-px text-[9px] font-medium uppercase tracking-wider",
                                    signal.direction === "LONG"
                                        ? "border-profit/30 bg-profit/10 text-profit"
                                        : "border-loss/30 bg-loss/10 text-loss",
                                )}>
                                    {signal.direction}
                                </span>
                            </span>
                            <LifecycleChip state={state} />
                        </div>

                        {/* Confidence: mono % + 2px bar. */}
                        {signal.confidence != null && (
                            <div className="flex items-center gap-2">
                                <div className="h-0.5 flex-1 overflow-hidden rounded-full bg-muted">
                                    <div
                                        className="h-full bg-accent-400"
                                        style={{ width: `${Math.round(Math.min(1, Math.max(0, signal.confidence)) * 100)}%` }}
                                    />
                                </div>
                                <Value className="text-[10px] text-muted-foreground" value={signal.confidence * 100} decimals={0} suffix="%" />
                            </div>
                        )}

                        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-border bg-border">
                            <MicroCell label="Entry"><Value className="text-[11px] text-info" value={signal.entry} decimals={info.pricePrecision} /></MicroCell>
                            <MicroCell label="Stop"><Value className="text-[11px] text-loss" value={signal.stopLoss} decimals={info.pricePrecision} /></MicroCell>
                            <MicroCell label={signal.takeProfits.length > 1 ? `TP×${signal.takeProfits.length}` : "TP"}>
                                <Value className="text-[11px] text-profit" value={signal.takeProfits[0]} decimals={info.pricePrecision} placeholder="—" />
                            </MicroCell>
                        </div>

                        <div className="flex flex-wrap items-center gap-1.5">
                            {signal.riskReward != null && (
                                <span className="num text-[10px] text-muted-foreground">R:R <Value value={signal.riskReward} decimals={2} /></span>
                            )}
                            {signal.regime && <OutlineBadge>{signal.regime}</OutlineBadge>}
                            {signal.strategy && <OutlineBadge>{signal.strategy}</OutlineBadge>}
                            <span className="num ml-auto text-[10px] text-subtle-foreground">{ago(signal.ts, now)}</span>
                        </div>

                        {signal.reasoning && (
                            <details className="group">
                                <summary className="cursor-pointer list-none text-[10px] uppercase tracking-wider text-subtle-foreground transition-colors duration-150 hover:text-muted-foreground">
                                    Reasoning
                                </summary>
                                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{signal.reasoning}</p>
                            </details>
                        )}

                        <div className="mt-auto flex gap-1.5">
                            <button
                                onClick={() => plot(signal)}
                                className={cn(
                                    "flex-1 rounded-sm border px-2 py-1 text-[11px] font-medium transition-colors duration-150",
                                    isPlotted
                                        ? "border-accent/40 bg-accent-muted text-accent-300"
                                        : "border-border text-muted-foreground hover:text-foreground",
                                )}
                            >
                                {isPlotted ? "Plotted" : "Plot"}
                            </button>
                            {mode === "manual" && state !== "booked" && (
                                <button
                                    onClick={() => execute(signal)}
                                    className="flex-1 rounded-sm border border-accent/25 bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground transition-colors duration-150 hover:bg-primary-hover"
                                >
                                    Execute
                                </button>
                            )}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function LifecycleChip({ state }: { state: Lifecycle }) {
    if (state === "booked") {
        return <span className="rounded-sm border border-profit/30 bg-profit/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wider text-profit">Booked by the desk</span>
    }
    if (state === "stale") {
        return <span className="rounded-sm border border-border px-1.5 py-px text-[9px] font-medium uppercase tracking-wider text-subtle-foreground">stale</span>
    }
    return <span className="rounded-sm border border-info/30 bg-info-muted px-1.5 py-px text-[9px] font-medium uppercase tracking-wider text-info">proposed</span>
}

function MicroCell({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col items-center gap-px bg-surface px-1 py-1">
            <span className="text-[8px] uppercase tracking-wider text-subtle-foreground">{label}</span>
            {children}
        </div>
    )
}

function OutlineBadge({ children }: { children: React.ReactNode }) {
    return (
        <span className="rounded-sm border border-border px-1 py-px text-[9px] uppercase tracking-wider text-subtle-foreground">
            {children}
        </span>
    )
}

function ago(ts: string, now: number): string {
    const ms = now - new Date(ts).getTime()
    if (!Number.isFinite(ms) || ms < 0) return ""
    const m = Math.floor(ms / 60000)
    if (m < 1) return "just now"
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    return `${h}h ago`
}
