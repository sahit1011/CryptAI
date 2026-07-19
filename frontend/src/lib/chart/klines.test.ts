import { describe, expect, test } from "vitest"
import { normalizeKlines, bucketKline, parseWsKline, intervalInfo, symbolInfo, type Bucket } from "./klines"

describe("normalizeKlines", () => {
    test("maps raw Binance rows to sorted numeric bars", () => {
        // Arrange — out of order, string prices (Binance shape)
        const raw = [
            [2000, "10", "12", "9", "11", "5"],
            [1000, "9", "10", "8", "10", "3"],
        ]

        // Act
        const bars = normalizeKlines(raw)

        // Assert
        expect(bars).toHaveLength(2)
        expect(bars[0].timestamp).toBe(1000)
        expect(bars[1]).toMatchObject({ timestamp: 2000, open: 10, high: 12, low: 9, close: 11, volume: 5 })
    })

    test("drops malformed rows and non-arrays", () => {
        expect(normalizeKlines(null)).toEqual([])
        expect(normalizeKlines([[1000, "1"]])).toEqual([])
        expect(normalizeKlines([["not-a-ts", "1", "2", "0.5", "1.5", "1"]])).toEqual([])
    })
})

describe("bucketKline (1m → interval)", () => {
    const M15 = 15 * 60_000

    test("opens a new bucket aligned to the interval boundary", () => {
        // Arrange — a 1m bar at 16:07 lands in the 16:00 15m bucket
        const oneMin = { timestamp: 7 * 60_000, open: 100, high: 105, low: 99, close: 104, volume: 2 }

        // Act
        const b = bucketKline(oneMin, M15, null)

        // Assert
        expect(b.timestamp).toBe(0) // floor(7m / 15m) * 15m
        expect(b).toMatchObject({ open: 100, high: 105, low: 99, close: 104, volume: 2 })
    })

    test("same forming minute replaces its volume contribution (cumulative frames)", () => {
        const first = bucketKline({ timestamp: 60_000, open: 100, high: 101, low: 99, close: 100.5, volume: 3 }, M15, null)
        // Same minute ticks again with a HIGHER cumulative volume
        const second = bucketKline({ timestamp: 60_000, open: 100, high: 102, low: 98, close: 101, volume: 5 }, M15, first)

        expect(second.volume).toBe(5) // replaced, not summed (3 → 5, not 8)
        expect(second.high).toBe(102)
        expect(second.low).toBe(98)
        expect(second.open).toBe(100) // bucket open never changes
    })

    test("a new minute inside the same bucket adds volume and extends OHLC", () => {
        const first = bucketKline({ timestamp: 0, open: 100, high: 101, low: 99, close: 100.5, volume: 3 }, M15, null)
        const second = bucketKline({ timestamp: 60_000, open: 100.5, high: 103, low: 100, close: 102, volume: 2 }, M15, first)

        expect(second.timestamp).toBe(0)
        expect(second.volume).toBe(5) // 3 + 2
        expect(second.high).toBe(103)
        expect(second.close).toBe(102)
    })

    test("crossing the interval boundary opens a fresh bucket", () => {
        const first = bucketKline({ timestamp: 14 * 60_000, open: 100, high: 101, low: 99, close: 100.5, volume: 3 }, M15, null)
        const second = bucketKline({ timestamp: 15 * 60_000, open: 100.5, high: 101, low: 100, close: 100.8, volume: 1 }, M15, first as Bucket)

        expect(second.timestamp).toBe(15 * 60_000)
        expect(second.open).toBe(100.5)
        expect(second.volume).toBe(1)
    })
})

describe("parseWsKline", () => {
    test("parses a raw Binance kline event", () => {
        const frame = { e: "kline", s: "BTCUSDT", k: { t: 1000, o: "100", h: "101", l: "99", c: "100.5", v: "3.2" } }
        const parsed = parseWsKline(frame)
        expect(parsed).not.toBeNull()
        expect(parsed!.symbol).toBe("BTCUSDT")
        expect(parsed!.bar).toMatchObject({ timestamp: 1000, close: 100.5, volume: 3.2 })
    })

    test("returns null for junk", () => {
        expect(parseWsKline(null)).toBeNull()
        expect(parseWsKline({ s: "BTCUSDT" })).toBeNull()
        expect(parseWsKline({ k: { t: "nope", c: "abc" } })).toBeNull()
    })
})

describe("registries", () => {
    test("intervalInfo falls back to 5m and symbolInfo to BTC", () => {
        expect(intervalInfo("nonsense").id).toBe("5m")
        expect(symbolInfo("NOPEUSDT").ticker).toBe("BTCUSDT")
        expect(intervalInfo("4h")).toMatchObject({ span: 4, type: "hour" })
    })
})
