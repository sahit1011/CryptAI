"use client"

import { useEffect, useRef, useState } from "react"
import type { Chart } from "klinecharts"
import { X, SlidersHorizontal } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ErrorState } from "@/components/ui/states"
import { useTerminalStore } from "@/store/useTerminalStore"
import { useStore } from "@/store/useStore"
import { buildChartStyles } from "@/lib/chart/theme"
import { chartPalette } from "@/lib/chart/tokens"
import { registerTerminalOverlays } from "@/lib/chart/overlays"
import { setChartHandle, getPlotManager } from "@/lib/chart/chartHandle"
import { PlotManager } from "@/lib/chart/plotSetup"
import { subscribeKlineBus } from "@/lib/chart/klineBus"
import {
    INTERVALS, intervalInfo, symbolInfo, fetchKlines, bucketKline, type Bucket,
} from "@/lib/chart/klines"
import { cn } from "@/lib/utils"

/*
 * ChartPanel — klinecharts v10 canvas + the 32px toolbar row.
 *
 * Live data doctrine: WS 1m frames reach the chart via the kline ref bus
 * (never React state), bucketed client-side into the active interval so every
 * timeframe stays live; non-streamed symbols poll-splice the last two bars.
 * The canvas is transparent — this container owns the background.
 */

// Indicators offered in the toolbar. Overlay group renders ON the candles;
// pane group opens its own sub-pane.
const OVERLAY_INDICATORS = ["MA", "EMA", "BOLL", "SMA", "SAR"] as const
const PANE_INDICATORS = ["VOL", "MACD", "RSI", "KDJ"] as const
const CANDLE_PANE_SET = new Set<string>(OVERLAY_INDICATORS)

const BTC_POLL_MS = 15_000  // WS-streamed: poll is only a resync safety net
const POLL_MS = 5_000       // non-streamed symbols: poll IS the live feed

export function ChartPanel() {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<Chart | null>(null)
    const appliedIndicatorsRef = useRef<Set<string>>(new Set())
    const [isReady, setIsReady] = useState(false)
    const [loadError, setLoadError] = useState<string | null>(null)

    const symbol = useTerminalStore((s) => s.symbol)
    const interval = useTerminalStore((s) => s.interval)
    const setIntervalId = useTerminalStore((s) => s.setInterval)
    const activeIndicators = useTerminalStore((s) => s.activeIndicators)
    const plottedSignalId = useTerminalStore((s) => s.plottedSignalId)
    const setPlottedSignalId = useTerminalStore((s) => s.setPlottedSignalId)

    // --- Mount / dispose (StrictMode-safe; klinecharts must be dynamically
    // imported — its module scope touches window and breaks SSR). -------------
    useEffect(() => {
        let disposed = false
        let cleanup: (() => void) | undefined

        async function mount() {
            const kc = await import("klinecharts")
            if (disposed || !containerRef.current) return
            registerTerminalOverlays(kc)

            const chart = kc.init(containerRef.current, { locale: "en-US" })
            if (!chart) return
            chartRef.current = chart
            chart.setStyles("dark")
            chart.setStyles(buildChartStyles())

            // Subscription registry keyed by ticker-period; unsubscribeBar tears down.
            const subs = new Map<string, () => void>()

            chart.setDataLoader({
                getBars: async ({ type, timestamp, symbol: sym, period, callback }) => {
                    const info = INTERVALS.find((i) => i.span === period.span && i.type === period.type) ?? intervalInfo("15m")
                    try {
                        // 'forward' = older bars (pan-back): page with endTime.
                        const endTime = type === "forward" && timestamp != null ? timestamp - 1 : undefined
                        const bars = await fetchKlines(sym.ticker, info.id, 500, endTime)
                        setLoadError(null)
                        callback(bars, { forward: bars.length === 500, backward: false })
                    } catch (e) {
                        setLoadError(e instanceof Error ? e.message : "Market data unavailable")
                        callback([], { forward: false, backward: false })
                    }
                },
                subscribeBar: ({ symbol: sym, period, callback }) => {
                    const info = INTERVALS.find((i) => i.span === period.span && i.type === period.type) ?? intervalInfo("15m")
                    const key = `${sym.ticker}-${period.span}${period.type}`
                    let bucket: Bucket | null = null

                    // WS 1m frames → interval bucket → forming candle (BTC streams today).
                    const unsubBus = subscribeKlineBus((ticker, bar) => {
                        if (ticker !== sym.ticker) return
                        bucket = bucketKline(bar, info.ms, bucket)
                        callback({ ...bucket })
                    })

                    // Poll-splice the last two bars: live feed for non-streamed
                    // symbols, drift-resync for the streamed one.
                    const pollMs = sym.ticker === "BTCUSDT" ? BTC_POLL_MS : POLL_MS
                    let stopped = false
                    const poll = async () => {
                        if (stopped) return
                        try {
                            const bars = await fetchKlines(sym.ticker, info.id, 2)
                            if (stopped) return
                            for (const b of bars) callback(b)
                            // Re-seed the bucket from the authoritative forming bar.
                            const last = bars[bars.length - 1]
                            if (last) bucket = { ...last, lastMinuteTs: last.timestamp, lastMinuteVol: last.volume }
                        } catch { /* transient poll failure — WS/next poll covers it */ }
                    }
                    const timer = setInterval(poll, pollMs)
                    const onVisible = () => { if (document.visibilityState === "visible") void poll() }
                    document.addEventListener("visibilitychange", onVisible)

                    subs.set(key, () => {
                        stopped = true
                        unsubBus()
                        clearInterval(timer)
                        document.removeEventListener("visibilitychange", onVisible)
                    })
                },
                unsubscribeBar: ({ symbol: sym, period }) => {
                    const key = `${sym.ticker}-${period.span}${period.type}`
                    subs.get(key)?.()
                    subs.delete(key)
                },
            })

            // Apply current workspace state (post-await: props may already be set).
            const s = useTerminalStore.getState()
            const si = symbolInfo(s.symbol)
            chart.setSymbol({ ticker: si.ticker, pricePrecision: si.pricePrecision, volumePrecision: si.volumePrecision })
            const ii = intervalInfo(s.interval)
            chart.setPeriod({ span: ii.span, type: ii.type })

            const plot = new PlotManager(chart, chartPalette())
            setChartHandle(chart, plot)
            appliedIndicatorsRef.current = new Set()
            setIsReady(true)

            cleanup = () => {
                for (const un of subs.values()) un()
                subs.clear()
                setChartHandle(null, null)
                kc.dispose(containerRef.current!)
                chartRef.current = null
            }
        }
        void mount()

        return () => {
            disposed = true
            setIsReady(false)
            cleanup?.()
        }
    }, [])

    // --- Symbol / timeframe: the data loader pipeline re-runs automatically ---
    useEffect(() => {
        if (!isReady) return
        const si = symbolInfo(symbol)
        getPlotManager()?.clearAll()
        // Keep a plot that belongs to the incoming symbol (SetupCards switches
        // symbol and plots in one gesture); clear anything else.
        const plottedId = useTerminalStore.getState().plottedSignalId
        const plotted = plottedId ? useStore.getState().signals.find((s) => s.id === plottedId) : null
        if (plotted && plotted.symbol === symbol) {
            getPlotManager()?.plotSignal(plotted)
        } else if (plottedId) {
            setPlottedSignalId(null)
        }
        chartRef.current?.setSymbol({ ticker: si.ticker, pricePrecision: si.pricePrecision, volumePrecision: si.volumePrecision })
    }, [symbol, isReady, setPlottedSignalId])

    useEffect(() => {
        if (!isReady) return
        const ii = intervalInfo(interval)
        chartRef.current?.setPeriod({ span: ii.span, type: ii.type })
    }, [interval, isReady])

    // --- Indicator set → chart panes (diffed, so toggles are incremental) -----
    useEffect(() => {
        const chart = chartRef.current
        if (!chart || !isReady) return
        const applied = appliedIndicatorsRef.current
        const wanted = new Set(activeIndicators)

        for (const name of applied) {
            if (!wanted.has(name)) {
                chart.removeIndicator({ name })
                applied.delete(name)
            }
        }
        for (const name of wanted) {
            if (applied.has(name)) continue
            if (CANDLE_PANE_SET.has(name)) {
                chart.createIndicator({ name, paneId: "candle_pane" }, true)
            } else {
                chart.createIndicator(name)
            }
            applied.add(name)
        }
    }, [activeIndicators, isReady])

    // --- AI lifecycle: PROPOSED plot follows plottedSignalId ------------------
    useEffect(() => {
        const plot = getPlotManager()
        if (!plot || !isReady) return
        if (!plottedSignalId) {
            plot.clearSignal()
            return
        }
        const signal = useStore.getState().signals.find((s) => s.id === plottedSignalId)
        if (signal) plot.plotSignal(signal)
    }, [plottedSignalId, isReady])

    // --- LIVE positions: solid level groups synced from position frames ------
    useEffect(() => {
        if (!isReady) return
        const sync = () => {
            const plot = getPlotManager()
            if (!plot) return
            plot.syncPositions(useStore.getState().activeTrades, useTerminalStore.getState().symbol)
        }
        sync()
        const unsub = useStore.subscribe((state, prev) => {
            if (state.activeTrades !== prev.activeTrades) sync()
        })
        return unsub
    }, [isReady, symbol])

    return (
        <div className="flex h-full flex-col">
            {/* Toolbar: 32px — timeframes left, indicator + plot controls right. */}
            <div className="flex h-8 shrink-0 items-center justify-between border-b border-border bg-surface pr-2">
                <div className="flex h-full items-center">
                    {INTERVALS.map((i, idx) => (
                        <button
                            key={i.id}
                            onClick={() => setIntervalId(i.id)}
                            title={`Timeframe ${i.id} (${idx + 1})`}
                            className={cn(
                                "num h-full px-3 text-[11px] transition-colors duration-150",
                                interval === i.id
                                    ? "bg-elevated text-foreground"
                                    : "text-muted-foreground hover:text-foreground",
                            )}
                        >
                            {i.id}
                        </button>
                    ))}
                </div>

                <div className="flex items-center gap-1.5">
                    {plottedSignalId && (
                        <button
                            onClick={() => setPlottedSignalId(null)}
                            className="flex items-center gap-1 rounded-sm border border-border bg-elevated px-2 py-0.5 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
                        >
                            AI setup plotted
                            <X className="size-3" />
                        </button>
                    )}
                    <IndicatorMenu />
                </div>
            </div>

            {/* Canvas (transparent) — the container owns the background. */}
            <div className="relative min-h-0 flex-1 bg-background">
                <div ref={containerRef} className="h-full w-full" />
                {loadError && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/85">
                        <ErrorState
                            title="Chart data unavailable"
                            description="The market-data proxy didn't answer. It retries automatically as you pan; or reload the page."
                            error={loadError}
                        />
                    </div>
                )}
            </div>
        </div>
    )
}

function IndicatorMenu() {
    const activeIndicators = useTerminalStore((s) => s.activeIndicators)
    const toggleIndicator = useTerminalStore((s) => s.toggleIndicator)

    const group = (title: string, names: readonly string[]) => (
        <div>
            <p className="label-md mb-1.5 text-subtle-foreground">{title}</p>
            <div className="flex flex-wrap gap-1">
                {names.map((name) => (
                    <button
                        key={name}
                        onClick={() => toggleIndicator(name)}
                        className={cn(
                            "num rounded-sm border px-2 py-1 text-[11px] transition-colors duration-150",
                            activeIndicators.includes(name)
                                ? "border-accent/40 bg-accent-muted text-accent-300"
                                : "border-border text-muted-foreground hover:text-foreground",
                        )}
                    >
                        {name}
                    </button>
                ))}
            </div>
        </div>
    )

    return (
        <Popover>
            <PopoverTrigger asChild>
                <button
                    title="Indicators (i)"
                    className="flex items-center gap-1.5 rounded-sm px-2 py-1 text-[11px] text-muted-foreground transition-colors duration-150 hover:bg-elevated hover:text-foreground"
                >
                    <SlidersHorizontal className="size-3" />
                    Indicators
                </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64 space-y-3 p-3">
                {group("On chart", OVERLAY_INDICATORS)}
                {group("Panes", PANE_INDICATORS)}
            </PopoverContent>
        </Popover>
    )
}
