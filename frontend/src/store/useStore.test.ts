import { beforeEach, describe, expect, it } from "vitest";
import { useStore, type Signal } from "./useStore";

const sig = (id: string, overrides: Partial<Signal> = {}): Signal => ({
    id,
    symbol: "BTCUSDT",
    direction: "LONG",
    entry: 64000,
    stopLoss: 63000,
    takeProfits: [66000],
    ts: new Date().toISOString(),
    ...overrides,
});

beforeEach(() => {
    useStore.setState({ signals: [], currency: "USD", inrRate: 87.5 });
});

describe("signals slice", () => {
    it("adds newest-first", () => {
        useStore.getState().addSignal(sig("a"));
        useStore.getState().addSignal(sig("b"));
        expect(useStore.getState().signals.map((s) => s.id)).toEqual(["b", "a"]);
    });

    it("dedupes by id (replay-safe)", () => {
        useStore.getState().addSignal(sig("a"));
        useStore.getState().addSignal(sig("a", { entry: 65000 }));
        const signals = useStore.getState().signals;
        expect(signals).toHaveLength(1);
        expect(signals[0].entry).toBe(65000); // newest wins
    });

    it("caps the feed at 30", () => {
        for (let i = 0; i < 40; i++) useStore.getState().addSignal(sig(`s${i}`));
        expect(useStore.getState().signals).toHaveLength(30);
        expect(useStore.getState().signals[0].id).toBe("s39");
    });
});

describe("currency preference", () => {
    it("defaults to USD", () => {
        expect(useStore.getState().currency).toBe("USD");
    });

    it("setCurrency switches to INR and back", () => {
        useStore.getState().setCurrency("INR");
        expect(useStore.getState().currency).toBe("INR");
        useStore.getState().setCurrency("USD");
        expect(useStore.getState().currency).toBe("USD");
    });

    it("setInrRate updates the live rate", () => {
        useStore.getState().setInrRate(96.33);
        expect(useStore.getState().inrRate).toBe(96.33);
    });
});

describe("trades slice", () => {
    it("closeTrade moves an active trade to history", () => {
        useStore.setState({ activeTrades: [], tradeHistory: [] });
        useStore.getState().updateTrade({
            id: "t1", symbol: "BTCUSDT", side: "LONG", entry: 64000, current: 64500,
            pnl: 500, pnlPercent: 0.78, status: "OPEN",
        });
        expect(useStore.getState().activeTrades).toHaveLength(1);
        useStore.getState().closeTrade("t1", 65000, "take_profit");
        expect(useStore.getState().activeTrades).toHaveLength(0);
        expect(useStore.getState().tradeHistory[0]).toMatchObject({
            id: "t1", status: "CLOSED", current: 65000, exitReason: "take_profit",
        });
    });
});
