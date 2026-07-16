import { describe, expect, it } from "vitest";
import { payloadToSignal } from "./signals";

const BASE = {
    symbol: "BTCUSDT",
    direction: "LONG",
    entry_price: 64500,
    stop_loss: 63100,
    take_profit_levels: [{ price: 66800, size: 1 }],
    confidence_score: 0.74,
    risk_reward: 2.1,
    market_regime: "TRENDING_BULLISH",
    strategy_type: "SMC",
    reasoning: "Bullish BOS on 15m.",
    recommended_position_size: 0.04,
};

describe("payloadToSignal", () => {
    it("maps a bare payload", () => {
        const s = payloadToSignal(BASE)!;
        expect(s.symbol).toBe("BTCUSDT");
        expect(s.direction).toBe("LONG");
        expect(s.entry).toBe(64500);
        expect(s.stopLoss).toBe(63100);
        expect(s.takeProfits).toEqual([66800]);
        expect(s.confidence).toBe(0.74);
        expect(s.positionSize).toBe(0.04);
    });

    it("unwraps the WS envelope { payload: {...} }", () => {
        const s = payloadToSignal({ type: "trade_setup", payload: BASE })!;
        expect(s.symbol).toBe("BTCUSDT");
    });

    it("accepts bare-number take profits", () => {
        const s = payloadToSignal({ ...BASE, take_profit_levels: [66000, 67000] })!;
        expect(s.takeProfits).toEqual([66000, 67000]);
    });

    it("drops non-finite take profits", () => {
        const s = payloadToSignal({ ...BASE, take_profit_levels: ["x", 66000] })!;
        expect(s.takeProfits).toEqual([66000]);
    });

    it("returns null without a symbol", () => {
        expect(payloadToSignal({ direction: "LONG" })).toBeNull();
        expect(payloadToSignal(null)).toBeNull();
        expect(payloadToSignal(undefined)).toBeNull();
    });

    it("id is content-derived so replays dedupe", () => {
        const a = payloadToSignal(BASE)!;
        const b = payloadToSignal({ ...BASE })!;
        expect(a.id).toBe(b.id);
    });

    it("non-SHORT directions normalize to LONG", () => {
        expect(payloadToSignal({ ...BASE, direction: "SHORT" })!.direction).toBe("SHORT");
        expect(payloadToSignal({ ...BASE, direction: "weird" })!.direction).toBe("LONG");
    });
});
