
"use client"

import { useEffect, useRef, useState } from "react"
import {
    createChart,
    ColorType,
    IChartApi,
    ISeriesApi,
    Time,
    CandlestickSeries,
    HistogramSeries,
    CandlestickData,
    HistogramData,
    CrosshairMode
} from "lightweight-charts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useMarketStore } from "@/hooks/useMarketData"
import { useStore } from "@/store/useStore"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'

interface OHLCData {
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

export function ChartWidget() {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)
    const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null)
    const currentCandleRef = useRef<CurrentCandle | null>(null)
    const [timeframe, setTimeframe] = useState<Timeframe>('1m')
    const [isLoading, setIsLoading] = useState(true)
    const [ohlcData, setOhlcData] = useState<OHLCData | null>(null)
    const [secondsLeft, setSecondsLeft] = useState<number>(0)
    const [currentPrice, setCurrentPrice] = useState<number>(0)
    const { ticker } = useMarketStore()
    const { activeTrades } = useStore()
    const priceLinesRef = useRef<any[]>([])

    // Get interval in seconds for each timeframe
    const getIntervalSeconds = (tf: Timeframe): number => {
        const intervals: Record<Timeframe, number> = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400,
        }
        return intervals[tf]
    }

    // Get the current candle's start time based on timeframe
    const getCurrentCandleTime = (tf: Timeframe): number => {
        const now = Math.floor(Date.now() / 1000)
        const interval = getIntervalSeconds(tf)
        return Math.floor(now / interval) * interval
    }

    // Fetch historical data from Binance
    const fetchHistoricalData = async (interval: Timeframe) => {
        try {
            setIsLoading(true)
            const limit = 500 // Get last 500 candles
            const url = `https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=${interval}&limit=${limit}`

            const response = await fetch(url)
            const data = await response.json()

            // Transform Binance kline data to lightweight-charts format
            const chartData: CandlestickData<Time>[] = data.map((kline: any) => ({
                time: Math.floor(kline[0] / 1000) as Time, // Convert ms to seconds
                open: parseFloat(kline[1]),
                high: parseFloat(kline[2]),
                low: parseFloat(kline[3]),
                close: parseFloat(kline[4]),
            }))

            // Transform volume data
            const volumeData: HistogramData<Time>[] = data.map((kline: any) => {
                const open = parseFloat(kline[1])
                const close = parseFloat(kline[4])
                return {
                    time: Math.floor(kline[0] / 1000) as Time,
                    value: parseFloat(kline[5]), // Volume
                    color: close >= open ? '#22c55e40' : '#ef444440', // Green for up, red for down
                }
            })

            // Initialize current candle with the last historical candle
            if (chartData.length > 0) {
                const lastCandle = chartData[chartData.length - 1]
                const currentTime = getCurrentCandleTime(interval)

                // If the last candle is the current candle time, use it
                if (lastCandle.time === currentTime) {
                    currentCandleRef.current = {
                        time: currentTime,
                        open: lastCandle.open,
                        high: lastCandle.high,
                        low: lastCandle.low,
                        close: lastCandle.close,
                    }
                } else {
                    // Otherwise, start a new candle with the last close price
                    currentCandleRef.current = {
                        time: currentTime,
                        open: lastCandle.close,
                        high: lastCandle.close,
                        low: lastCandle.close,
                        close: lastCandle.close,
                    }
                }
            }

            return { chartData, volumeData }
        } catch (error) {
            console.error('Error fetching historical data:', error)
            return { chartData: [], volumeData: [] }
        } finally {
            setIsLoading(false)
        }
    }

    // Initialize Chart
    useEffect(() => {
        if (!chartContainerRef.current) return

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#111827' },
                textColor: '#9ca3af',
            },
            grid: {
                vertLines: { color: '#1f2937' },
                horzLines: { color: '#1f2937' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            localization: {
                timeFormatter: (time: number) => {
                    const date = new Date(time * 1000)
                    return date.toLocaleTimeString('en-IN', {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false,
                        timeZone: 'Asia/Kolkata'
                    })
                },
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: {
                    width: 1,
                    color: '#6b7280',
                    style: 0,
                },
                horzLine: {
                    width: 1,
                    color: '#6b7280',
                    style: 0,
                },
            },
        })

        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
            priceFormat: {
                type: 'price',
                precision: 2,
                minMove: 0.01,
            },
        })

        // Add volume series
        const volumeSeries = chart.addSeries(HistogramSeries, {
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: 'volume',
        })

        // Configure volume scale
        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8, // Volume takes bottom 20% of chart
                bottom: 0,
            },
        })

        // Configure price scale
        candleSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.1,
                bottom: 0.25, // Leave room for volume
            },
        })

        chartRef.current = chart
        candleSeriesRef.current = candleSeries
        volumeSeriesRef.current = volumeSeries

        // Subscribe to crosshair move to show OHLC data
        chart.subscribeCrosshairMove((param) => {
            if (!param.time || !param.seriesData.get(candleSeries)) {
                setOhlcData(null)
                return
            }

            const data = param.seriesData.get(candleSeries) as CandlestickData<Time>
            const volumeData = param.seriesData.get(volumeSeries) as HistogramData<Time>

            if (data) {
                const timestamp = new Date((param.time as number) * 1000)
                setOhlcData({
                    time: timestamp.toLocaleString('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        dateStyle: 'short',
                        timeStyle: 'medium'
                    }),
                    open: data.open,
                    high: data.high,
                    low: data.low,
                    close: data.close,
                    volume: volumeData?.value || 0,
                })
            }
        })

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth })
            }
        }

        window.addEventListener('resize', handleResize)

        return () => {
            window.removeEventListener('resize', handleResize)
            chart.remove()
        }
    }, [])

    // Load historical data when timeframe changes
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return

        fetchHistoricalData(timeframe).then(({ chartData, volumeData }) => {
            if (chartData.length > 0 && candleSeriesRef.current && volumeSeriesRef.current) {
                candleSeriesRef.current.setData(chartData)
                volumeSeriesRef.current.setData(volumeData)
            }
        })
    }, [timeframe])

    // Update countdown timer
    useEffect(() => {
        const interval = setInterval(() => {
            const now = Math.floor(Date.now() / 1000)
            const intervalSeconds = getIntervalSeconds(timeframe)
            const currentCandleTime = Math.floor(now / intervalSeconds) * intervalSeconds
            const nextCandleTime = currentCandleTime + intervalSeconds
            const remaining = nextCandleTime - now
            setSecondsLeft(remaining)
        }, 1000)

        return () => clearInterval(interval)
    }, [timeframe])

    // Update with live ticker data - properly aggregate into current candle
    useEffect(() => {
        if (!ticker || !candleSeriesRef.current) return

        const price = parseFloat(ticker.c)
        if (isNaN(price)) return

        setCurrentPrice(price) // Track current price for timer positioning

        const currentTime = getCurrentCandleTime(timeframe)

        // Check if we need to start a new candle
        if (!currentCandleRef.current || currentCandleRef.current.time !== currentTime) {
            // Start a new candle
            currentCandleRef.current = {
                time: currentTime,
                open: price,
                high: price,
                low: price,
                close: price,
            }
        } else {
            // Update current candle
            currentCandleRef.current.high = Math.max(currentCandleRef.current.high, price)
            currentCandleRef.current.low = Math.min(currentCandleRef.current.low, price)
            currentCandleRef.current.close = price
        }

        // Update the chart with the current candle
        // Only update if this is a valid time (not older than existing data)
        try {
            const candleData = {
                time: currentTime as Time,
                open: currentCandleRef.current.open,
                high: currentCandleRef.current.high,
                low: currentCandleRef.current.low,
                close: currentCandleRef.current.close,
            }

            candleSeriesRef.current.update(candleData)
        } catch (error) {
            // Silently ignore errors from updating with same/old timestamp
            // This can happen when historical data is more recent than live data
        }
    }, [ticker, timeframe])

    const timeframes: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1d']

    const formatSecondsLeft = (seconds: number): string => {
        const mins = Math.floor(seconds / 60)
        const secs = seconds % 60
        return `${mins}:${secs.toString().padStart(2, '0')}`
    }

    // Manage Trade Lines (Entry, SL, TP)
    useEffect(() => {
        if (!candleSeriesRef.current) return

        // Clear existing lines
        priceLinesRef.current.forEach(line => {
            candleSeriesRef.current?.removePriceLine(line)
        })
        priceLinesRef.current = []

        // Add lines for each active trade
        activeTrades.forEach(trade => {
            // Entry Line (Blue)
            const entryLine = candleSeriesRef.current?.createPriceLine({
                price: trade.entry,
                color: '#3b82f6', // Blue-500
                lineWidth: 1,
                lineStyle: 0, // Solid
                axisLabelVisible: true,
                title: `${trade.side} ENTRY`,
            })
            if (entryLine) priceLinesRef.current.push(entryLine)

            // Stop Loss (Red)
            if (trade.stopLoss) {
                const slLine = candleSeriesRef.current?.createPriceLine({
                    price: trade.stopLoss,
                    color: '#ef4444', // Red-500
                    lineWidth: 1,
                    lineStyle: 0, // Solid
                    axisLabelVisible: true,
                    title: 'SL',
                })
                if (slLine) priceLinesRef.current.push(slLine)
            }

            // Take Profit (Green)
            if (trade.takeProfit) {
                const tpLine = candleSeriesRef.current?.createPriceLine({
                    price: trade.takeProfit,
                    color: '#22c55e', // Green-500
                    lineWidth: 1,
                    lineStyle: 0, // Solid
                    axisLabelVisible: true,
                    title: 'TP',
                })
                if (tpLine) priceLinesRef.current.push(tpLine)
            }
        })

    }, [activeTrades])

    return (
        <Card className="bg-[#111827] border-gray-800 h-full flex flex-col">
            <CardHeader className="pb-2 border-b border-gray-800">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <CardTitle className="text-sm font-medium text-gray-400">
                            BTC/USDT • {timeframe.toUpperCase()}
                        </CardTitle>
                        {ohlcData && (
                            <div className="flex items-center gap-3 text-xs font-mono">
                                <span className="text-gray-500">O</span>
                                <span className="text-gray-300">{ohlcData.open.toFixed(2)}</span>
                                <span className="text-gray-500">H</span>
                                <span className="text-green-400">{ohlcData.high.toFixed(2)}</span>
                                <span className="text-gray-500">L</span>
                                <span className="text-red-400">{ohlcData.low.toFixed(2)}</span>
                                <span className="text-gray-500">C</span>
                                <span className={cn(
                                    "font-semibold",
                                    ohlcData.close >= ohlcData.open ? "text-green-400" : "text-red-400"
                                )}>{ohlcData.close.toFixed(2)}</span>
                                <span className="text-gray-500 ml-2">Vol</span>
                                <span className="text-gray-300">{ohlcData.volume.toFixed(2)}</span>
                            </div>
                        )}
                    </div>
                    <div className="flex gap-1">
                        {timeframes.map((tf) => (
                            <Button
                                key={tf}
                                variant="ghost"
                                size="sm"
                                onClick={() => setTimeframe(tf)}
                                className={cn(
                                    "h-7 px-2 text-xs",
                                    timeframe === tf
                                        ? "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30"
                                        : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
                                )}
                            >
                                {tf.toUpperCase()}
                            </Button>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-0 flex-1 relative">
                {isLoading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-[#111827]/80 z-10">
                        <div className="text-gray-400 text-sm flex items-center gap-2">
                            <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                            Loading chart data...
                        </div>
                    </div>
                )}
                <div ref={chartContainerRef} className="w-full h-full" />

                {/* Countdown Timer Overlay - TradingView Style */}
                {secondsLeft > 0 && currentPrice > 0 && (
                    <div className="absolute right-0 top-1/3 pointer-events-none z-20 flex items-center">
                        <div className="bg-[#1e222d] border border-gray-700 text-gray-300 text-[10px] font-mono px-1.5 py-0.5">
                            {formatSecondsLeft(secondsLeft)}
                        </div>
                    </div>
                )}

                {/* Placeholder for future agent chart annotations (e.g. order
                    blocks). No real annotation feed is wired yet, so it is clearly
                    marked as a demo rather than presented as a live signal. */}
                <div className="absolute top-4 left-4 pointer-events-none">
                    <div className="bg-white/5 border border-white/10 text-muted-foreground text-xs px-2 py-1 rounded backdrop-blur-sm mb-2">
                        Agent annotations · Coming soon
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
