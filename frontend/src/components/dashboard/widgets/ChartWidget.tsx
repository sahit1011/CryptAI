"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
    createChart,
    ColorType,
    CrosshairMode,
    LineStyle,
    CandlestickSeries,
    HistogramSeries,
    type IChartApi,
    type ISeriesApi,
    type IPriceLine,
    type Time,
    type CandlestickData,
    type HistogramData,
} from "lightweight-charts"
import { RefreshCw } from "lucide-react"

import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Value } from "@/components/ui/value"
import { LoadingState, ErrorState } from "@/components/ui/states"
import { useMarketStore } from "@/hooks/useMarketData"
import { useStore } from "@/store/useStore"
import { cn, safeNum } from "@/lib/utils"

type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d"

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"]

const INTERVAL_SECONDS: Record<Timeframe, number> = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

interface OHLC {
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

interface CurrentCandle {
    time: number
    open: number
    high: number
    low: number
    close: number
}

/**
 * Raw Binance kline row: [openTime, open, high, low, close, volume, ...].
 * We only read the leading fields; the rest are ignored.
 */
type Kline = [number, string, string, string, string, string, ...unknown[]]

/**
 * Resolve a design token to a concrete rgb()/rgba() string for lightweight-charts.
 *
 * The tokens are authored in oklch (and some use color-mix); lightweight-charts is a
 * canvas lib whose color parser only understands rgb/hex/named colors and THROWS on
 * lab()/oklch()/color-mix() — which previously crashed the whole Markets tab. We let
 * the browser do the conversion: apply `var(--x)` to a throwaway element and read back
 * getComputedStyle().color, which the browser always normalizes to rgb/rgba.
 */
function token(name: string, fallback: string): string {
    if (typeof window === "undefined") return fallback
    try {
        const el = document.createElement("div")
        el.style.color = `var(${name})`
        el.style.display = "none"
        document.body.appendChild(el)
        const rgb = getComputedStyle(el).color
        document.body.removeChild(el)
        return rgb && rgb.startsWith("rgb") ? rgb : fallback
    } catch {
        return fallback
    }
}

/** Turn an rgb()/rgba() string into rgba() with the given alpha (for fills). */
function withAlpha(rgb: string, alpha: number): string {
    const m = rgb.match(/rgba?\(([^)]+)\)/)
    if (!m) return rgb
    const [r, g, b] = m[1].split(",").map((s) => s.trim())
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function getCandleStartTime(tf: Timeframe): number {
    const now = Math.floor(Date.now() / 1000)
    const interval = INTERVAL_SECONDS[tf]
    return Math.floor(now / interval) * interval
}

function formatCountdown(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
}

export function ChartWidget() {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)
    const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null)
    const currentCandleRef = useRef<CurrentCandle | null>(null)
    const priceLinesRef = useRef<IPriceLine[]>([])

    const [timeframe, setTimeframe] = useState<Timeframe>("1m")
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [ohlc, setOhlc] = useState<OHLC | null>(null)
    const [secondsLeft, setSecondsLeft] = useState(0)
    const [currentPrice, setCurrentPrice] = useState(0)

    const { ticker } = useMarketStore()
    const { activeTrades } = useStore()

    // --- Historical data fetch (real Binance market data) -------------------
    const fetchHistorical = useCallback(async (interval: Timeframe) => {
        setIsLoading(true)
        setError(null)
        try {
            // Same-origin proxy (src/app/api/klines) — the browser can't hit Binance
            // directly (no CORS headers); the server route fetches + falls back.
            const url = `/api/klines?symbol=BTCUSDT&interval=${interval}&limit=500`
            const res = await fetch(url)
            if (!res.ok) throw new Error(`Market data request failed (${res.status})`)
            const raw: unknown = await res.json()
            if (!Array.isArray(raw)) throw new Error("Unexpected market data response")

            const rows = raw as Kline[]
            const chartData: CandlestickData<Time>[] = rows.map((k) => ({
                time: Math.floor(safeNum(k[0]) / 1000) as Time,
                open: safeNum(k[1]),
                high: safeNum(k[2]),
                low: safeNum(k[3]),
                close: safeNum(k[4]),
            }))

            // Candles/volume follow P&L semantics: up = profit green, down = loss red
            // (NOT the brand chart palette, which is crimson-led after the rebrand).
            const upVol = withAlpha(token("--color-profit", "rgb(62,207,142)"), 0.28)
            const downVol = withAlpha(token("--color-loss", "rgb(229,72,77)"), 0.28)
            const volumeData: HistogramData<Time>[] = rows.map((k) => {
                const open = safeNum(k[1])
                const close = safeNum(k[4])
                return {
                    time: Math.floor(safeNum(k[0]) / 1000) as Time,
                    value: safeNum(k[5]),
                    color: close >= open ? upVol : downVol,
                }
            })

            // Seed the live candle from the most recent historical bar.
            if (chartData.length > 0) {
                const last = chartData[chartData.length - 1]
                const currentTime = getCandleStartTime(interval)
                currentCandleRef.current =
                    last.time === currentTime
                        ? { time: currentTime, open: last.open, high: last.high, low: last.low, close: last.close }
                        : { time: currentTime, open: last.close, high: last.close, low: last.close, close: last.close }
            }

            return { chartData, volumeData }
        } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to load chart data"
            setError(message)
            return { chartData: [], volumeData: [] }
        } finally {
            setIsLoading(false)
        }
    }, [])

    // --- Chart init ---------------------------------------------------------
    useEffect(() => {
        if (!chartContainerRef.current) return

        const surface = token("--color-surface", "#111318")
        const gridColor = token("--color-border", "rgba(255,255,255,0.08)")
        const axisText = token("--color-subtle-foreground", "#7d818c")
        const crosshair = token("--color-border-strong", "rgba(255,255,255,0.14)")
        // Candles follow P&L semantics: up = profit green, down = loss red.
        const upColor = token("--color-profit", "rgb(62,207,142)")
        const downColor = token("--color-loss", "rgb(229,72,77)")

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: surface },
                textColor: axisText,
                fontFamily: "var(--font-geist-mono)",
                attributionLogo: false,
            },
            grid: {
                vertLines: { color: gridColor },
                horzLines: { color: gridColor },
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight || 400,
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
            rightPriceScale: { borderColor: gridColor },
            localization: {
                timeFormatter: (time: number) =>
                    new Date(time * 1000).toLocaleTimeString("en-IN", {
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                        timeZone: "Asia/Kolkata",
                    }),
                // Candle data is USD; show the axis + crosshair in the user's currency.
                priceFormatter: (price: number) => {
                    const { currency, inrRate } = useStore.getState()
                    if (currency === "INR") {
                        const inr = price * (inrRate || 87.5)
                        return "₹" + inr.toLocaleString("en-IN", { maximumFractionDigits: inr >= 1000 ? 0 : 2 })
                    }
                    return "$" + price.toLocaleString("en-US", { maximumFractionDigits: price >= 1000 ? 0 : 2 })
                },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { width: 1, color: crosshair, style: LineStyle.Dashed },
                horzLine: { width: 1, color: crosshair, style: LineStyle.Dashed },
            },
        })

        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor,
            downColor,
            borderVisible: false,
            wickUpColor: upColor,
            wickDownColor: downColor,
            priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        })

        const volumeSeries = chart.addSeries(HistogramSeries, {
            priceFormat: { type: "volume" },
            priceScaleId: "volume",
        })
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        })
        candleSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.1, bottom: 0.25 },
        })

        chartRef.current = chart
        candleSeriesRef.current = candleSeries
        volumeSeriesRef.current = volumeSeries

        chart.subscribeCrosshairMove((param) => {
            const data = param.time
                ? (param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined)
                : undefined
            if (!data) {
                setOhlc(null)
                return
            }
            const volume = param.seriesData.get(volumeSeries) as HistogramData<Time> | undefined
            setOhlc({
                time: new Date((param.time as number) * 1000).toLocaleString("en-IN", {
                    timeZone: "Asia/Kolkata",
                    dateStyle: "short",
                    timeStyle: "medium",
                }),
                open: data.open,
                high: data.high,
                low: data.low,
                close: data.close,
                volume: volume?.value ?? 0,
            })
        })

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight || 400,
                })
            }
        }
        window.addEventListener("resize", handleResize)

        // Track the CONTAINER's size, not just the window. Hovering/clicking the chart
        // makes the OHLC readout appear in the header, which shrinks the chart area — the
        // canvas kept its old pixel size and visibly glitched/overflowed. ResizeObserver
        // re-fits the chart to its box on any layout change (header, sidebar, tab switch).
        const ro =
            typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => handleResize()) : null
        if (ro && chartContainerRef.current) ro.observe(chartContainerRef.current)

        return () => {
            window.removeEventListener("resize", handleResize)
            ro?.disconnect()
            chart.remove()
            chartRef.current = null
            candleSeriesRef.current = null
            volumeSeriesRef.current = null
            priceLinesRef.current = []
        }
    }, [])

    // --- Load historical on timeframe change --------------------------------
    const loadTimeframe = useCallback(
        (tf: Timeframe) => {
            void fetchHistorical(tf).then(({ chartData, volumeData }) => {
                if (chartData.length > 0 && candleSeriesRef.current && volumeSeriesRef.current) {
                    candleSeriesRef.current.setData(chartData)
                    volumeSeriesRef.current.setData(volumeData)
                    chartRef.current?.timeScale().fitContent()
                }
            })
        },
        [fetchHistorical],
    )

    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return
        loadTimeframe(timeframe)
    }, [timeframe, loadTimeframe])

    // --- Countdown to next candle -------------------------------------------
    useEffect(() => {
        const interval = setInterval(() => {
            const now = Math.floor(Date.now() / 1000)
            const seconds = INTERVAL_SECONDS[timeframe]
            const start = Math.floor(now / seconds) * seconds
            setSecondsLeft(start + seconds - now)
        }, 1000)
        return () => clearInterval(interval)
    }, [timeframe])

    // --- Aggregate live ticker into the current candle ----------------------
    useEffect(() => {
        if (!ticker || !candleSeriesRef.current) return
        const price = safeNum(ticker.c, NaN)
        if (!Number.isFinite(price)) return

        setCurrentPrice(price)
        const currentTime = getCandleStartTime(timeframe)

        if (!currentCandleRef.current || currentCandleRef.current.time !== currentTime) {
            currentCandleRef.current = { time: currentTime, open: price, high: price, low: price, close: price }
        } else {
            const c = currentCandleRef.current
            c.high = Math.max(c.high, price)
            c.low = Math.min(c.low, price)
            c.close = price
        }

        try {
            candleSeriesRef.current.update({
                time: currentTime as Time,
                open: currentCandleRef.current.open,
                high: currentCandleRef.current.high,
                low: currentCandleRef.current.low,
                close: currentCandleRef.current.close,
            })
        } catch {
            // Ignore stale-timestamp updates when history is newer than the tick.
        }
    }, [ticker, timeframe])

    // --- Trade overlay lines (entry / SL / TP) in token colors --------------
    useEffect(() => {
        const series = candleSeriesRef.current
        if (!series) return

        for (const line of priceLinesRef.current) series.removePriceLine(line)
        priceLinesRef.current = []

        const entryColor = token("--color-chart-2", "#4a9eff")
        const slColor = token("--color-loss", "#e5484d")
        const tpColor = token("--color-profit", "#3ecf8e")

        for (const trade of activeTrades) {
            if (Number.isFinite(trade.entry)) {
                priceLinesRef.current.push(
                    series.createPriceLine({
                        price: trade.entry,
                        color: entryColor,
                        lineWidth: 1,
                        lineStyle: LineStyle.Solid,
                        axisLabelVisible: true,
                        title: `${trade.side} ENTRY`,
                    }),
                )
            }
            if (trade.stopLoss != null && Number.isFinite(trade.stopLoss)) {
                priceLinesRef.current.push(
                    series.createPriceLine({
                        price: trade.stopLoss,
                        color: slColor,
                        lineWidth: 1,
                        lineStyle: LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: "SL",
                    }),
                )
            }
            if (trade.takeProfit != null && Number.isFinite(trade.takeProfit)) {
                priceLinesRef.current.push(
                    series.createPriceLine({
                        price: trade.takeProfit,
                        color: tpColor,
                        lineWidth: 1,
                        lineStyle: LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: "TP",
                    }),
                )
            }
        }
    }, [activeTrades])

    return (
        <Card className="flex h-full flex-col overflow-hidden py-0">
            {/* Header: symbol + timeframe switcher. STABLE layout — the OHLC readout is
                a floating overlay on the chart (below), NOT here, so it can't shift the
                timeframe buttons as the crosshair moves. */}
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
                <h3 className="heading-4 truncate">
                    BTC/USDT · <span className="num text-muted-foreground">{timeframe.toUpperCase()}</span>
                </h3>

                <div className="flex shrink-0 gap-0.5">
                    {TIMEFRAMES.map((tf) => (
                        <Button
                            key={tf}
                            variant="ghost"
                            size="sm"
                            onClick={() => setTimeframe(tf)}
                            className={cn(
                                "h-7 px-2 text-xs",
                                timeframe === tf && "bg-accent-muted text-accent-300 hover:bg-accent-muted",
                            )}
                        >
                            {tf.toUpperCase()}
                        </Button>
                    ))}
                </div>
            </div>

            {/* Chart canvas + overlays */}
            <div className="relative min-h-0 flex-1">
                <div ref={chartContainerRef} className="h-full w-full" />

                {/* OHLC readout — floats over the chart (TradingView-style legend) so it
                    never affects the header/button layout. */}
                {ohlc ? (
                    <div className="pointer-events-none absolute left-3 top-2 z-20 flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md bg-background/70 px-2 py-1 text-xs backdrop-blur-sm">
                        <span className="label-md">O</span>
                        <Value className="text-xs" value={ohlc.open} decimals={2} money />
                        <span className="label-md">H</span>
                        <Value className="text-xs text-profit" value={ohlc.high} decimals={2} money />
                        <span className="label-md">L</span>
                        <Value className="text-xs text-loss" value={ohlc.low} decimals={2} money />
                        <span className="label-md">C</span>
                        <Value
                            className={cn(
                                "text-xs font-semibold",
                                ohlc.close >= ohlc.open ? "text-profit" : "text-loss",
                            )}
                            value={ohlc.close}
                            decimals={2}
                            money
                        />
                        <span className="label-md ml-1">Vol</span>
                        <Value className="text-xs text-muted-foreground" value={ohlc.volume} decimals={2} />
                    </div>
                ) : null}

                {isLoading ? (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/80 backdrop-blur-sm">
                        <LoadingState title="Loading chart data…" />
                    </div>
                ) : null}

                {error && !isLoading ? (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/90 backdrop-blur-sm">
                        <ErrorState
                            icon={<RefreshCw />}
                            title="Couldn't load market data"
                            description="The historical price feed is unavailable."
                            error={error}
                            onRetry={() => loadTimeframe(timeframe)}
                        />
                    </div>
                ) : null}

                {/* Next-candle countdown (TradingView-style) */}
                {!isLoading && !error && secondsLeft > 0 && currentPrice > 0 ? (
                    <div className="pointer-events-none absolute right-0 top-1/3 z-20 flex items-center">
                        <span className="num rounded-l-md border border-border-strong bg-elevated px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {formatCountdown(secondsLeft)}
                        </span>
                    </div>
                ) : null}

                {/* Honest placeholder: agent chart annotations are not wired yet. */}
                <div className="pointer-events-none absolute left-4 top-4 z-20">
                    <span className="rounded-md border border-border bg-elevated/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur-sm">
                        Agent annotations · Coming soon
                    </span>
                </div>
            </div>
        </Card>
    )
}
