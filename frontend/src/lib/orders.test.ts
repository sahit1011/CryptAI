import { describe, expect, test } from "vitest"
import { mapOpenOrders } from "./orders"

describe("mapOpenOrders", () => {
    test("maps BingX-like rows to UI orders, newest first", () => {
        // Arrange — a bracket's two legs (paper-engine shape, string numerics)
        const raw = [
            { orderId: "1", symbol: "btcusdt", side: "SELL", type: "STOP_MARKET", origQty: "0.03", price: "0", stopPrice: "63439", status: "NEW", reduceOnly: true, updateTime: 100 },
            { orderId: "2", symbol: "BTCUSDT", side: "SELL", type: "LIMIT", origQty: "0.03", price: "66659", stopPrice: "0", status: "NEW", reduceOnly: true, updateTime: 200 },
        ]

        // Act
        const orders = mapOpenOrders(raw)

        // Assert
        expect(orders).toHaveLength(2)
        expect(orders[0].orderId).toBe("2") // newest first
        expect(orders[0]).toMatchObject({ symbol: "BTCUSDT", side: "SELL", type: "LIMIT", qty: 0.03, price: 66659, stopPrice: 0, reduceOnly: true })
        expect(orders[1]).toMatchObject({ type: "STOP_MARKET", stopPrice: 63439, price: 0 })
    })

    test("drops malformed rows instead of rendering lies", () => {
        const raw = [
            { orderId: "", symbol: "BTCUSDT", side: "SELL", origQty: "1" },      // no id
            { orderId: "3", symbol: "", side: "BUY", origQty: "1" },             // no symbol
            { orderId: "4", symbol: "BTCUSDT", side: "HOLD", origQty: "1" },     // junk side
            { orderId: "5", symbol: "BTCUSDT", side: "BUY", origQty: "0" },      // zero qty
            null,
        ]
        expect(mapOpenOrders(raw)).toEqual([])
        expect(mapOpenOrders(null)).toEqual([])
        expect(mapOpenOrders("nope")).toEqual([])
    })
})
