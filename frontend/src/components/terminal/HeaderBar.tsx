"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { ChevronDown, Power } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ConnectionStatus } from "@/components/ui/connection-status"
import { Value, PnL } from "@/components/ui/value"
import { Badge } from "@/components/ui/badge"
import { useMarketStore } from "@/hooks/useMarketData"
import { useTerminalStore, type TickerStats } from "@/store/useTerminalStore"
import { useStore } from "@/store/useStore"
import { getEngine, setEngine, getSettings, type EngineStatus, type TradingMode } from "@/lib/api"
import { SYMBOLS, symbolInfo } from "@/lib/chart/klines"
import { cn, safeNum } from "@/lib/utils"

/*
 * HeaderBar — 44px. The screen's single accent moment lives here: the serif
 * wordmark beside the EnginePill. Everything else is structural: symbol
 * switcher (+ last / 24hΔ), 24h stats, mode badge, connection, $/₹.
 */

const TICKER_POLL_MS = 5_000

/** Poll /api/ticker for every desk symbol; the BTC WS frame overrides. */
function useTickerFeed() {
    const setTickerStats = useTerminalStore((s) => s.setTickerStats)
    const wsTicker = useMarketStore((s) => s.ticker)

    useEffect(() => {
        let stopped = false
        const poll = async () => {
            if (stopped) return
            try {
                const res = await fetch("/api/ticker", { cache: "no-store" })
                if (!res.ok) return
                const { ticks } = (await res.json()) as {
                    ticks?: {
                        symbol: string; lastPrice: string; priceChangePercent: string
                        openPrice?: string; highPrice?: string; lowPrice?: string
                        volume?: string; quoteVolume?: string
                    }[]
                }
                if (stopped || !ticks) return
                for (const sym of SYMBOLS) {
                    const t = ticks.find((x) => x.symbol === sym.ticker)
                    if (!t) continue
                    // A fresh WS ticker wins for the streamed symbol.
                    const existing = useTerminalStore.getState().tickers[sym.ticker]
                    if (existing?.source === "ws" && Date.now() - existing.at < TICKER_POLL_MS * 2) continue
                    setTickerStats(sym.ticker, {
                        last: safeNum(t.lastPrice),
                        pctChange: safeNum(t.priceChangePercent),
                        open: t.openPrice != null ? safeNum(t.openPrice) : undefined,
                        high: t.highPrice != null ? safeNum(t.highPrice) : undefined,
                        low: t.lowPrice != null ? safeNum(t.lowPrice) : undefined,
                        volume: t.volume != null ? safeNum(t.volume) : undefined,
                        quoteVolume: t.quoteVolume != null ? safeNum(t.quoteVolume) : undefined,
                        source: "poll",
                        at: Date.now(),
                    })
                }
            } catch { /* silent poll failure — provenance badges disclose staleness */ }
        }
        void poll()
        const id = setInterval(poll, TICKER_POLL_MS)
        return () => { stopped = true; clearInterval(id) }
    }, [setTickerStats])

    // BTC live frame (raw Binance 24hrTicker carries o/h/l/v/q).
    useEffect(() => {
        if (!wsTicker) return
        const raw = wsTicker as typeof wsTicker & { o?: string; h?: string; l?: string }
        setTickerStats(String(wsTicker.s ?? "BTCUSDT").toUpperCase(), {
            last: safeNum(wsTicker.c),
            pctChange: safeNum(wsTicker.P),
            open: raw.o != null ? safeNum(raw.o) : undefined,
            high: raw.h != null ? safeNum(raw.h) : undefined,
            low: raw.l != null ? safeNum(raw.l) : undefined,
            volume: safeNum(wsTicker.v) || undefined,
            quoteVolume: safeNum(wsTicker.q) || undefined,
            source: "ws",
            at: Date.now(),
        })
    }, [wsTicker, setTickerStats])
}

export function HeaderBar() {
    useTickerFeed()
    const status = useMarketStore((s) => s.status)
    const currency = useStore((s) => s.currency)
    const setCurrency = useStore((s) => s.setCurrency)

    return (
        <header className="flex h-11 shrink-0 items-center justify-between bg-surface pl-4 pr-3">
            <div className="flex min-w-0 items-center gap-4">
                {/* Brand cluster — the one accent moment. */}
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard"
                        className="font-serif text-lg italic tracking-[-0.01em] text-accent-300 transition-colors duration-150 hover:text-accent-200"
                    >
                        CryptAI
                    </Link>
                    <EnginePill />
                </div>

                <div className="h-5 w-px bg-border" aria-hidden />

                <SymbolSwitcher />
                <TickerStatsInline />
            </div>

            <div className="flex items-center gap-2.5">
                <ModeBadge />
                <div className="hidden md:block">
                    <ConnectionStatus status={status} />
                </div>
                <div className="flex overflow-hidden rounded-md border border-border">
                    {(["USD", "INR"] as const).map((c) => (
                        <button
                            key={c}
                            onClick={() => setCurrency(c)}
                            className={cn(
                                "num px-2 py-0.5 text-[11px] transition-colors duration-150",
                                currency === c ? "bg-accent-muted text-accent-300" : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            {c === "USD" ? "$" : "₹"}
                        </button>
                    ))}
                </div>
            </div>
        </header>
    )
}

/* ------------------------------- EnginePill -------------------------------- */

const ENGINE_POLL_MS = 30_000
const ENGINE_WARN_S = 15 * 60
const DURATIONS: { label: string; seconds: number }[] = [
    { label: "30 min", seconds: 1800 },
    { label: "2 h", seconds: 7200 },
    { label: "8 h", seconds: 28800 },
]

function fmtCountdown(s: number): string {
    if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
    if (s >= 60) return `${Math.floor(s / 60)}m`
    return `${s}s`
}

function EnginePill() {
    const [engine, setEngineState] = useState<EngineStatus | null>(null)
    const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
    const [isBusy, setBusy] = useState(false)

    useEffect(() => {
        let stopped = false
        const load = () => getEngine().then((e) => {
            if (stopped) return
            setEngineState(e)
            setSecondsLeft(e.expires_in_seconds)
        }).catch(() => { /* status stays unknown; pill renders off */ })
        void load()
        const id = setInterval(load, ENGINE_POLL_MS)
        return () => { stopped = true; clearInterval(id) }
    }, [])

    // Local countdown between polls.
    useEffect(() => {
        if (secondsLeft == null || secondsLeft <= 0) return
        const id = setInterval(() => setSecondsLeft((s) => (s != null && s > 0 ? s - 1 : s)), 1000)
        return () => clearInterval(id)
    }, [secondsLeft != null && secondsLeft > 0]) // eslint-disable-line react-hooks/exhaustive-deps

    const isOn = Boolean(engine?.enabled)
    const isAdmin = Boolean(engine?.is_admin)
    const isExpiring = isOn && secondsLeft != null && secondsLeft < ENGINE_WARN_S

    const toggle = async (enabled: boolean, duration?: number) => {
        setBusy(true)
        try {
            const e = await setEngine(enabled, duration ?? null)
            setEngineState(e)
            setSecondsLeft(e.expires_in_seconds)
        } catch { /* non-admin or backend down — pill re-syncs on next poll */ }
        setBusy(false)
    }

    const pill = (
        <span
            title={isOn ? undefined : "The analysis loop is paused — setups resume when an admin arms it"}
            className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px]",
                isOn
                    ? isExpiring
                        ? "border-warning/30 bg-warning-muted text-warning"
                        : "border-accent/30 bg-accent-muted text-accent-300"
                    : "border-border text-subtle-foreground",
            )}
        >
            <span className={cn("size-1.5 rounded-full", isOn ? "animate-pulse-subtle bg-current" : "bg-current opacity-50")} />
            {isOn ? (
                <>Engine on{secondsLeft != null && <span className="num">· {fmtCountdown(secondsLeft)}</span>}</>
            ) : (
                "Engine off"
            )}
        </span>
    )

    if (!isAdmin) return pill

    return (
        <Popover>
            <PopoverTrigger asChild>
                <button className="transition-opacity duration-150 hover:opacity-80" disabled={isBusy}>{pill}</button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-52 p-2">
                <p className="label-md mb-2 text-subtle-foreground">AI engine</p>
                <div className="flex flex-col gap-1">
                    {DURATIONS.map((d) => (
                        <button
                            key={d.seconds}
                            disabled={isBusy}
                            onClick={() => void toggle(true, d.seconds)}
                            className="flex items-center justify-between rounded-md px-2 py-1.5 text-left text-xs text-foreground transition-colors duration-150 hover:bg-elevated"
                        >
                            Run for {d.label}
                            <Power className="size-3 text-accent-300" />
                        </button>
                    ))}
                    <button
                        disabled={isBusy || !isOn}
                        onClick={() => void toggle(false)}
                        className="rounded-md px-2 py-1.5 text-left text-xs text-loss transition-colors duration-150 hover:bg-elevated disabled:opacity-40"
                    >
                        Turn off
                    </button>
                </div>
            </PopoverContent>
        </Popover>
    )
}

/* ----------------------------- SymbolSwitcher ------------------------------ */

function SymbolSwitcher() {
    const symbol = useTerminalStore((s) => s.symbol)
    const setSymbol = useTerminalStore((s) => s.setSymbol)
    const tickers = useTerminalStore((s) => s.tickers)
    const [isOpen, setOpen] = useState(false)
    const active = symbolInfo(symbol)
    const stats: TickerStats | undefined = tickers[symbol]

    return (
        <Popover open={isOpen} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    id="symbol-switcher"
                    title="Switch symbol (/)"
                    className="flex items-center gap-2 rounded-md px-2 py-1 transition-colors duration-150 hover:bg-elevated"
                >
                    <span className="text-sm font-semibold text-foreground">{active.ticker}</span>
                    {stats && (
                        <>
                            <Value className="financial-sm text-foreground" value={stats.last} decimals={active.pricePrecision} />
                            <PnL className="text-[11px]" value={stats.pctChange} decimals={2} suffix="%" showSign />
                        </>
                    )}
                    <ChevronDown className="size-3.5 text-subtle-foreground" />
                </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-1">
                {SYMBOLS.map((s) => {
                    const t = tickers[s.ticker]
                    return (
                        <button
                            key={s.ticker}
                            onClick={() => { setSymbol(s.ticker); setOpen(false) }}
                            className={cn(
                                "flex w-full items-center justify-between rounded-md px-2.5 py-2 transition-colors duration-150 hover:bg-elevated",
                                s.ticker === symbol && "bg-elevated",
                            )}
                        >
                            <span className="flex items-baseline gap-2">
                                <span className="text-xs font-semibold text-foreground">{s.ticker}</span>
                                <span className="text-[11px] text-subtle-foreground">{s.label}</span>
                            </span>
                            {t ? (
                                <span className="flex items-baseline gap-2.5">
                                    <Value className="num text-xs text-foreground" value={t.last} decimals={s.pricePrecision} />
                                    <PnL className="num w-16 text-right text-[11px]" value={t.pctChange} decimals={2} suffix="%" showSign />
                                </span>
                            ) : (
                                <span className="text-[11px] text-subtle-foreground">—</span>
                            )}
                        </button>
                    )
                })}
            </PopoverContent>
        </Popover>
    )
}

/* ---------------------------- TickerStatsInline ---------------------------- */

function TickerStatsInline() {
    const symbol = useTerminalStore((s) => s.symbol)
    const stats = useTerminalStore((s) => s.tickers[symbol])
    const info = symbolInfo(symbol)
    if (!stats) return null

    const cell = (label: string, value: number | undefined, decimals: number) =>
        value != null && Number.isFinite(value) ? (
            <span className="hidden items-baseline gap-1 xl:flex">
                <span className="label-md text-subtle-foreground">{label}</span>
                <Value className="num text-[11px] text-muted-foreground" value={value} decimals={decimals} />
            </span>
        ) : null

    return (
        <div className="flex items-center gap-4">
            {cell("24h H", stats.high, info.pricePrecision)}
            {cell("24h L", stats.low, info.pricePrecision)}
            {cell("Vol", stats.volume, 0)}
            {cell("Turnover", stats.quoteVolume, 0)}
        </div>
    )
}

/* -------------------------------- ModeBadge -------------------------------- */

function ModeBadge() {
    const [mode, setMode] = useState<TradingMode | null>(null)

    useEffect(() => {
        let stopped = false
        const load = () => getSettings().then((s) => { if (!stopped) setMode(s.trading_mode) }).catch(() => { })
        void load()
        const onVisible = () => { if (document.visibilityState === "visible") void load() }
        document.addEventListener("visibilitychange", onVisible)
        return () => { stopped = true; document.removeEventListener("visibilitychange", onVisible) }
    }, [])

    if (!mode) return null
    const variant = mode === "auto" ? "default" : mode === "manual" ? "warning" : mode === "paper" ? "info" : "outline"
    return <Badge variant={variant} className="uppercase">{mode}</Badge>
}
