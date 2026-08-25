"use client"

import { useEffect, useState } from "react"
import { Value, PnL } from "@/components/ui/value"
import { useStore } from "@/store/useStore"
import { useTerminalStore } from "@/store/useTerminalStore"
import { SYMBOLS } from "@/lib/chart/klines"
import { API_URL } from "@/lib/api"
import { describeActivity, type ActivityDisplay, type ActivityTone, type PulseResponse } from "@/lib/pulse"
import { cn } from "@/lib/utils"

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
                <Activity />
                <Provenance />
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

/** Honest per-symbol data provenance, derived from what actually arrived. */
function Provenance() {
    const tickers = useTerminalStore((s) => s.tickers)
    const parts = SYMBOLS.map((s) => {
        const t = tickers[s.ticker]
        return `${s.label} ${t?.source === "ws" ? "live" : "5s poll"}`
    })
    return (
        <span className="hidden text-[10px] text-subtle-foreground lg:block" title="Data provenance — what streams vs polls, per symbol">
            {parts.join(" · ")}
        </span>
    )
}

/*
 * Activity — the measured hour rank plus live tradability, from GET /api/pulse.
 * All interpretation (including every honesty rule) lives in lib/pulse.ts and is
 * tested there; this only renders what it returns. Polls slowly on purpose: the
 * rank changes hourly and the badge is context, not a trading signal.
 */
const PULSE_POLL_MS = 60_000

const TONE_CLASS: Record<ActivityTone, string> = {
    peak: "text-profit",
    active: "text-info",
    quiet: "text-subtle-foreground",
    neutral: "text-subtle-foreground",
}

function Activity() {
    const [display, setDisplay] = useState<ActivityDisplay | null>(null)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const r = await fetch(`${API_URL}/api/pulse`, { cache: "no-store" })
                const body = r.ok ? ((await r.json()) as PulseResponse) : null
                if (!cancelled) setDisplay(describeActivity(body))
            } catch {
                // A failed request is "unknown", which describeActivity renders honestly.
                if (!cancelled) setDisplay(describeActivity(null))
            }
        }
        const t = setTimeout(load, 0)
        const id = setInterval(load, PULSE_POLL_MS)
        return () => { cancelled = true; clearTimeout(t); clearInterval(id) }
    }, [])

    if (!display) return null
    return (
        <span className="hidden shrink-0 items-baseline gap-1.5 md:flex" title={display.title}>
            <span className="label-md text-subtle-foreground">{display.label}</span>
            <span className={cn("num text-[10px]", TONE_CLASS[display.tone])}>{display.rank}</span>
            {display.live && (
                <span className="num text-[10px] text-subtle-foreground">{display.live}</span>
            )}
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
