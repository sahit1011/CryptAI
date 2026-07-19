import { describe, expect, test } from "vitest"
import { validateTicket, riskReward, stopDistancePct, toExecutePayload } from "./ticket"

const LONG = { direction: "LONG" as const, entry: 100, stopLoss: 95, takeProfits: [110, 120] }
const SHORT = { direction: "SHORT" as const, entry: 100, stopLoss: 105, takeProfits: [90] }

describe("validateTicket", () => {
    test("accepts a well-formed LONG and SHORT bracket", () => {
        expect(validateTicket(LONG)).toEqual([])
        expect(validateTicket(SHORT)).toEqual([])
    })

    test("rejects non-positive entry/stop and missing TPs", () => {
        expect(validateTicket({ ...LONG, entry: 0 })).toContain("Entry must be a positive price.")
        expect(validateTicket({ ...LONG, stopLoss: -1 })).toContain("Stop loss must be a positive price.")
        expect(validateTicket({ ...LONG, takeProfits: [] })).toContain("At least one take-profit level is required.")
    })

    test("rejects LONG geometry with stop above entry or TP below entry", () => {
        expect(validateTicket({ ...LONG, stopLoss: 101 })).toContain("LONG: stop loss must sit below entry.")
        expect(validateTicket({ ...LONG, takeProfits: [99] })).toContain("LONG: every take-profit must sit above entry.")
    })

    test("rejects SHORT geometry with stop below entry or TP above entry", () => {
        expect(validateTicket({ ...SHORT, stopLoss: 99 })).toContain("SHORT: stop loss must sit above entry.")
        expect(validateTicket({ ...SHORT, takeProfits: [101] })).toContain("SHORT: every take-profit must sit below entry.")
    })
})

describe("riskReward", () => {
    test("LONG: (TP1 - entry) / (entry - stop)", () => {
        expect(riskReward(LONG)).toBeCloseTo(2) // (110-100)/(100-95)
    })
    test("SHORT: (entry - TP1) / (stop - entry)", () => {
        expect(riskReward(SHORT)).toBeCloseTo(2) // (100-90)/(105-100)
    })
    test("NaN when the geometry is degenerate", () => {
        expect(riskReward({ ...LONG, stopLoss: 100 })).toBeNaN()
        expect(riskReward({ ...LONG, takeProfits: [] })).toBeNaN()
    })
})

describe("stopDistancePct", () => {
    test("absolute stop distance as % of entry", () => {
        expect(stopDistancePct(LONG)).toBeCloseTo(5)
        expect(stopDistancePct(SHORT)).toBeCloseTo(5)
    })
})

describe("toExecutePayload", () => {
    test("maps the draft to the execute-setup body, dropping junk TPs", () => {
        const payload = toExecutePayload("BTCUSDT", { ...LONG, takeProfits: [110, NaN, 0, 120] })
        expect(payload).toEqual({
            symbol: "BTCUSDT",
            direction: "LONG",
            entry_price: 100,
            stop_loss: 95,
            take_profit_levels: [110, 120],
        })
    })

    test("hand-built brackets omit confidence; AI-prefilled ones carry it", () => {
        expect(toExecutePayload("BTCUSDT", LONG)).not.toHaveProperty("confidence_score")
        expect(toExecutePayload("BTCUSDT", LONG, 0.82)).toMatchObject({ confidence_score: 0.82 })
        expect(toExecutePayload("BTCUSDT", LONG, NaN)).not.toHaveProperty("confidence_score")
    })
})
