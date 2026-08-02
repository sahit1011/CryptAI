import { describe, expect, it } from "vitest";

import type { TradingPreferences } from "@/lib/api";
import {
    changedFields,
    fromPercent,
    parseSymbolUniverse,
    symbolUniverseText,
    toPercent,
} from "@/lib/preferences";

const BASE: TradingPreferences = {
    trading_capital: 10_000,
    capital_currency: "USDT",
    risk_appetite: "moderate",
    max_risk_per_trade_pct: 1,
    max_concurrent_positions: 1,
    max_daily_trades: 3,
    max_leverage: 3,
    monthly_pnl_target_pct: null,
    goal_horizon: "swing",
    goal_notes: null,
    symbol_universe: null,
    allowed_strategies: null,
    min_risk_reward: 1.5,
    min_confidence: 0.6,
    avoid_high_funding: true,
};

describe("parseSymbolUniverse", () => {
    it("splits on commas and whitespace, uppercases, de-dupes", () => {
        expect(parseSymbolUniverse("btcusdt, ethusdt  ethusdt")).toEqual(["BTCUSDT", "ETHUSDT"]);
    });
    it("normalizes a bare base to the USDT perp", () => {
        expect(parseSymbolUniverse("btc eth sol")).toEqual(["BTCUSDT", "ETHUSDT", "SOLUSDT"]);
    });
    it("leaves an explicit USDT symbol alone", () => {
        expect(parseSymbolUniverse("BTCUSDT")).toEqual(["BTCUSDT"]);
    });
    it("returns null for empty input (use the platform default)", () => {
        expect(parseSymbolUniverse("   ")).toBeNull();
        expect(parseSymbolUniverse("")).toBeNull();
    });
});

describe("symbolUniverseText", () => {
    it("round-trips a universe and empties a null", () => {
        expect(symbolUniverseText(["BTCUSDT", "ETHUSDT"])).toBe("BTCUSDT, ETHUSDT");
        expect(symbolUniverseText(null)).toBe("");
    });
});

describe("percent conversions", () => {
    it("converts fraction <-> percent", () => {
        expect(toPercent(0.65)).toBe(65);
        expect(fromPercent(65)).toBe(0.65);
        expect(fromPercent(2.5)).toBe(0.025);
    });
});

describe("changedFields", () => {
    it("is empty when nothing changed", () => {
        expect(changedFields(BASE, { risk_appetite: "moderate", goal_horizon: "swing" })).toEqual({});
    });
    it("returns only the fields that differ", () => {
        expect(
            changedFields(BASE, { risk_appetite: "aggressive", goal_horizon: "swing" }),
        ).toEqual({ risk_appetite: "aggressive" });
    });
    it("compares arrays by content, not reference", () => {
        // Same content as null base -> not changed.
        expect(changedFields(BASE, { symbol_universe: null })).toEqual({});
        // New content -> changed.
        expect(changedFields(BASE, { symbol_universe: ["BTCUSDT"] })).toEqual({
            symbol_universe: ["BTCUSDT"],
        });
        // Same array content, different reference -> not changed.
        const withUniverse = { ...BASE, symbol_universe: ["BTCUSDT", "ETHUSDT"] };
        expect(
            changedFields(withUniverse, { symbol_universe: ["BTCUSDT", "ETHUSDT"] }),
        ).toEqual({});
    });
    it("detects a monthly target set from null", () => {
        expect(changedFields(BASE, { monthly_pnl_target_pct: 15 })).toEqual({
            monthly_pnl_target_pct: 15,
        });
    });
});
