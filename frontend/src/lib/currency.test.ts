import { describe, expect, it } from "vitest";
import { formatInr, formatMoney, toInr, DEFAULT_USD_INR } from "./currency";

describe("formatMoney", () => {
    it("renders USD without conversion", () => {
        expect(formatMoney(10798.6, "USD", 96)).toBe("$10,798.60");
    });

    it("renders INR converted at the rate with en-IN grouping", () => {
        // 100 USD @ 90 → ₹9,000.00 (Indian grouping kicks in above 1 lakh)
        expect(formatMoney(100, "INR", 90)).toBe("₹9,000.00");
        expect(formatMoney(10000, "INR", 90)).toBe("₹9,00,000.00"); // 9 lakh
    });

    it("respects the decimals argument", () => {
        expect(formatMoney(64980, "USD", 96, 0)).toBe("$64,980");
    });

    it("returns a dash for missing/invalid values", () => {
        expect(formatMoney(null, "USD", 96)).toBe("—");
        expect(formatMoney(undefined, "INR", 96)).toBe("—");
        expect(formatMoney(NaN, "USD", 96)).toBe("—");
    });

    it("falls back to the default rate when rate is 0", () => {
        expect(formatMoney(1, "INR", 0)).toBe(
            `₹${DEFAULT_USD_INR.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        );
    });
});

describe("formatInr / toInr", () => {
    it("formatInr is INR-mode formatMoney", () => {
        expect(formatInr(100, 90)).toBe(formatMoney(100, "INR", 90));
    });
    it("toInr multiplies by the rate", () => {
        expect(toInr(10, 90)).toBe(900);
    });
});
