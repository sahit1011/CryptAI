import { describe, expect, test } from "vitest";
import { computeTradeStats, closedTrades } from "@/lib/tradeStats";
import type { Trade } from "@/store/useStore";

const mk = (over: Partial<Trade>): Trade => ({
    id: Math.random().toString(36),
    symbol: "BTCUSDT",
    side: "LONG",
    entry: 100,
    current: 110,
    pnl: 10,
    pnlPercent: 1,
    status: "CLOSED",
    exitTime: "2026-07-16T00:00:00Z",
    ...over,
});

describe("computeTradeStats", () => {
    test("returns empty stats for no trades", () => {
        const s = computeTradeStats([]);
        expect(s.closedCount).toBe(0);
        expect(s.realizedPnl).toBe(0);
        expect(s.equityCurve).toEqual([]);
    });

    test("ignores open trades", () => {
        const trades = [mk({ status: "OPEN", exitTime: undefined, pnl: 999 }), mk({ pnl: 5 })];
        expect(closedTrades(trades)).toHaveLength(1);
        expect(computeTradeStats(trades).realizedPnl).toBe(5);
    });

    test("computes realized pnl, win rate, best/worst", () => {
        const trades = [
            mk({ pnl: 100, exitTime: "2026-07-12T00:00:00Z" }),
            mk({ pnl: -40, exitTime: "2026-07-13T00:00:00Z" }),
            mk({ pnl: 60, exitTime: "2026-07-14T00:00:00Z" }),
        ];
        const s = computeTradeStats(trades);
        expect(s.closedCount).toBe(3);
        expect(s.realizedPnl).toBe(120);
        expect(s.wins).toBe(2);
        expect(s.losses).toBe(1);
        expect(s.winRate).toBeCloseTo(66.67, 1);
        expect(s.best).toBe(100);
        expect(s.worst).toBe(-40);
        expect(s.avgWin).toBe(80);
        expect(s.avgLoss).toBe(-40);
        expect(s.profitFactor).toBeCloseTo(4, 5); // 160 / 40
    });

    test("equity curve is cumulative, oldest→newest, starts at 0", () => {
        const trades = [
            mk({ pnl: 60, exitTime: "2026-07-14T00:00:00Z" }),
            mk({ pnl: 100, exitTime: "2026-07-12T00:00:00Z" }),
            mk({ pnl: -40, exitTime: "2026-07-13T00:00:00Z" }),
        ];
        // chronological: +100, -40, +60 → [0, 100, 60, 120]
        expect(computeTradeStats(trades).equityCurve).toEqual([0, 100, 60, 120]);
    });

    test("groups per symbol, sorted by |pnl| desc", () => {
        const trades = [
            mk({ symbol: "BTCUSDT", pnl: 30 }),
            mk({ symbol: "ETHUSDT", pnl: -80 }),
            mk({ symbol: "BTCUSDT", pnl: 20 }),
        ];
        const s = computeTradeStats(trades);
        expect(s.perSymbol[0]).toEqual({ symbol: "ETHUSDT", pnl: -80, trades: 1, wins: 0 });
        expect(s.perSymbol[1]).toEqual({ symbol: "BTCUSDT", pnl: 50, trades: 2, wins: 2 });
    });

    test("profit factor is Infinity with no losses", () => {
        expect(computeTradeStats([mk({ pnl: 10 }), mk({ pnl: 5 })]).profitFactor).toBe(Infinity);
    });
});
