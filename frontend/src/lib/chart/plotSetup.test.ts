import { describe, expect, test } from "vitest"
import { signalLevels, positionLevels } from "./plotSetup"
import type { Signal, Trade } from "@/store/useStore"
import type { ChartPalette } from "./tokens"

const palette: ChartPalette = {
    profit: "rgb(0,200,0)", loss: "rgb(200,0,0)", info: "rgb(0,0,200)", warning: "rgb(200,200,0)",
    accent300: "rgb(1,1,1)", accent400: "rgb(2,2,2)", accent500: "rgb(3,3,3)",
    foreground: "rgb(4,4,4)", mutedFg: "rgb(5,5,5)", subtleFg: "rgb(6,6,6)",
    border: "rgb(7,7,7)", hairline: "rgb(8,8,8)", elevated: "rgb(9,9,9)",
}

const signal: Signal = {
    id: "s1", symbol: "BTCUSDT", direction: "LONG",
    entry: 100, stopLoss: 95, takeProfits: [110, 120], ts: new Date().toISOString(),
}

describe("signalLevels (PROPOSED — dashed)", () => {
    test("entry/stop/TPs map to info/loss/profit with percent labels", () => {
        const levels = signalLevels(signal, palette)
        expect(levels).toHaveLength(4)

        const [entry, stop, tp1, tp2] = levels
        expect(entry).toMatchObject({ value: 100, data: { color: palette.info, lineStyle: "dashed" } })
        expect(entry.data.label).toContain("AI ENTRY")

        expect(stop.value).toBe(95)
        expect(stop.data.color).toBe(palette.loss)
        expect(stop.data.label).toContain("−5.0%")

        expect(tp1.data.label).toContain("TP1 +10.0%")
        expect(tp2.data.label).toContain("TP2 +20.0%")
        expect(tp2.data.color).toBe(palette.profit)
    })

    test("drops non-finite / zero levels instead of plotting lies", () => {
        const junk: Signal = { ...signal, entry: 0, stopLoss: NaN, takeProfits: [0, -5, 110] }
        const levels = signalLevels(junk, palette)
        expect(levels).toHaveLength(1)
        expect(levels[0].value).toBe(110)
    })
})

describe("positionLevels (LIVE — solid)", () => {
    test("entry/SL/TP draw solid with side label", () => {
        const trade: Trade = {
            id: "t1", symbol: "BTCUSDT", side: "SHORT", entry: 200, current: 195,
            pnl: 5, pnlPercent: 2.5, status: "OPEN", stopLoss: 210, takeProfit: 180,
        }
        const levels = positionLevels(trade, palette)
        expect(levels).toHaveLength(3)
        expect(levels[0].data).toMatchObject({ lineStyle: "solid", color: palette.info })
        expect(levels[0].data.label).toContain("SHORT")
        expect(levels[1].data.color).toBe(palette.loss)
        expect(levels[2].data.color).toBe(palette.profit)
    })

    test("omits missing SL/TP rather than drawing zeros", () => {
        const trade: Trade = {
            id: "t2", symbol: "ETHUSDT", side: "LONG", entry: 3000, current: 3050,
            pnl: 50, pnlPercent: 1.6, status: "OPEN",
        }
        const levels = positionLevels(trade, palette)
        expect(levels).toHaveLength(1)
    })
})
